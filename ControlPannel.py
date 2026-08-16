"""
control_panel.py (v8 -- Telemetry Passthrough Version)
"""

import queue
import threading
import time
import requests
from flask import Flask, jsonify, request

# ============================== CONFIG ====================================
SANDBOX_AGENT_URLS = ["http://192.168.100.56:5001"]
# Pointing to your Mac for the mock webhook test
BACKEND_TEAM_WEBHOOK_URL = "http://192.168.100.73:8080/internal/analysis-result"

AGENT_API_KEY = "7f3c9a1e6d4b8c2f0a5e7b9d3c1f6a8e2d4b0c9f7e5a1d6"       
AGENT_HEALTH_TIMEOUT = 5
AGENT_ANALYZE_TIMEOUT = 120 + 200  
# ============================================================================

app = Flask(__name__)

_jobs = {}
_lock = threading.Lock()
_job_queue = queue.Queue()
_job_counter = 0

_locally_busy_sandboxes = set()
_agent_lock = threading.Lock()


def _get_next_id():
    global _job_counter
    with _lock:
        _job_counter += 1
        return _job_counter


def _update_job(obs_id, **fields):
    with _lock:
        if obs_id in _jobs:
            _jobs[obs_id].update(fields)


def _get_job(obs_id):
    with _lock:
        return dict(_jobs[obs_id]) if obs_id in _jobs else None


def _dispatch_job(obs_id, file_bytes, filename, agent_url, vm_id):
    verdict = "Unknown"
    telemetry = {}
    try:
        resp = requests.post(
            f"{agent_url}/analyze/{vm_id}",
            headers={"X-API-Key": AGENT_API_KEY},
            files={"file": (filename, file_bytes)},
            timeout=AGENT_ANALYZE_TIMEOUT,
        )
        if resp.status_code == 409:
            raise RuntimeError(f"Agent returned 409 Conflict: VM {vm_id} was unexpectedly busy.")
        elif resp.status_code != 200:
            raise RuntimeError(f"Agent returned {resp.status_code}: {resp.text}")

        # Extract the full payload from the sandbox agent
        telemetry = resp.json()
        verdict = telemetry.get("verdict", "Unknown")
        
        _update_job(obs_id, status="Completed", verdict=verdict, features=telemetry)

    except Exception as exc:
        print(f"[!] Job {obs_id} failed: {exc}")
        _update_job(obs_id, status="Failed", features={"error": str(exc)})
        verdict = "Failed"

    finally:
        # === THE WEBHOOK PUSH (Now with Features) ===
        try:
            payload = {
                "observationId": obs_id,
                "verdict": verdict,
                "features": telemetry
            }
            print(f"[+] Pushing result for Job {obs_id} to Webhook...")
            requests.post(BACKEND_TEAM_WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"[!] Warning: Failed to reach webhook: {e}")

        with _agent_lock:
            _locally_busy_sandboxes.discard((agent_url, vm_id))
        _job_queue.task_done()


def _worker():
    while True:
        obs_id, file_bytes, filename = _job_queue.get()
        _update_job(obs_id, status="Running", features={})

        agent_url = None
        target_vm_id = None
        
        while agent_url is None:
            for url in SANDBOX_AGENT_URLS:
                try:
                    health = requests.get(
                        f"{url}/health",
                        headers={"X-API-Key": AGENT_API_KEY},
                        timeout=AGENT_HEALTH_TIMEOUT,
                    )
                    
                    if health.status_code == 200:
                        vms = health.json().get("sandboxes", {})
                        for vid, state in vms.items():
                            with _agent_lock:
                                if (url, vid) in _locally_busy_sandboxes:
                                    continue
                            
                            if not state.get("busy"):
                                agent_url = url
                                target_vm_id = vid
                                with _agent_lock:
                                    _locally_busy_sandboxes.add((url, vid))
                                break 
                except Exception:
                    pass
                if agent_url:
                    break 
            
            if agent_url is None:
                time.sleep(3)
                
        threading.Thread(
            target=_dispatch_job, 
            args=(obs_id, file_bytes, filename, agent_url, target_vm_id), 
            daemon=True
        ).start()


threading.Thread(target=_worker, daemon=True).start()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route("/api/files", methods=["POST"])
def upload_file():
    uploaded = request.files.get("file")
    
    if not uploaded or not uploaded.filename:
        return jsonify({"errors": [{"errorMessage": "File is empty."}]}), 400

    obs_id = _get_next_id()
    file_bytes = uploaded.read()

    with _lock:
        _jobs[obs_id] = {
            "observationId": obs_id,
            "status": "Queued",
            "verdict": "Unknown",
            "features": {}
        }

    _job_queue.put((obs_id, file_bytes, uploaded.filename))
    
    return jsonify({"observationId": obs_id, "status": "Queued"}), 201


@app.route("/api/urls", methods=["POST"])
def upload_url():
    return jsonify({"errors": [{"errorMessage": "URL analysis out of scope."}]}), 501


@app.route("/api/observations/<int:obs_id>", methods=["GET"])
def get_observation(obs_id):
    job = _get_job(obs_id)
    if job is None:
        return jsonify({"error": f"Observation with id '{obs_id}' not found."}), 404
        
    # Now returns the feature vector to whoever queries it
    return jsonify({
        "observationId": job["observationId"],
        "status": job["status"],
        "verdict": job["verdict"],
        "features": job.get("features", {})
    }), 200


if __name__ == "__main__":
    print(f"[+] Sandbox API Server started (Telemetry Passthrough Active).")
    app.run(host="0.0.0.0", port=5005, threaded=True)
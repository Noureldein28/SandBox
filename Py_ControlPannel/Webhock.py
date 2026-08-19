# import json
# from flask import Flask, request

# app = Flask(__name__)

# @app.route("/internal/analysis-result", methods=["POST"])
# def receive_result():
#     data = request.json
#     print("\n" + "=" * 50)
#     print(f"[+] WEBHOOK CAUGHT A RESULT!")
#     print(f"    Observation ID : {data.get('observationId')}")
#     print(f"    Final Verdict  : {data.get('verdict')}")
#     print("-" * 50)
#     print("    RAW TELEMETRY:")
#     print(json.dumps(data.get('features', {}), indent=4))
#     print("=" * 50 + "\n")
    
#     return {"status": "Completed"}, 200

# if __name__ == "__main__":
#     print("[+] Mock Backend Team Server listening on port 8080...")
#     app.run(host="0.0.0.0", port=8080)



import json
from flask import Flask, request

app = Flask(__name__)

# 1. Update the route to match the Control Panel's destination
@app.route("/internal/sandbox-callback", methods=["POST"])
def receive_result():
    data = request.json
    print("\n" + "=" * 50)
    print(f"[+] WEBHOOK CAUGHT A RESULT!")
    
    # 2. Update the key to 'jobId' to match ControlPannel_2.py (v9)
    print(f"    Job ID         : {data.get('jobId')}")
    
    print(f"    Final Verdict  : {data.get('verdict')}")
    print("-" * 50)
    print("    RAW TELEMETRY:")
    print(json.dumps(data.get('features', {}), indent=4))
    print("=" * 50 + "\n")
    
    return {"status": "Completed"}, 200

if __name__ == "__main__":
    print("[+] Mock Backend Team Server listening on port 8080...")
    app.run(host="0.0.0.0", port=8080)
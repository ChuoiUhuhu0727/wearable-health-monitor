"""
Option 4 telemetry receiver — runs on the Jetson, listens for live packets
pushed by the wearable's task_telemetry over WiFi.

THIS IS A CONVENIENCE / LIVE-VIEW LAYER ONLY. It is not the dataset. The
device's onboard flash (retrieved later with log_serial.py) remains the
guaranteed data record regardless of whether this server is even running.
See project_option4_jetson_plan (Claude memory) for the full rationale.

Setup: see setup_ap.md for configuring the Jetson as a WiFi AP first.

Usage:
    pip install -r requirements.txt
    python server.py
"""

import json
import os
from datetime import datetime

from flask import Flask, request, jsonify

app = Flask(__name__)

LOG_DIR = "live_telemetry"
os.makedirs(LOG_DIR, exist_ok=True)

BPM_MIN, BPM_MAX = 40, 180

# One log file per server run — purely for convenience/debugging, not the dataset.
_session_log_path = os.path.join(
    LOG_DIR, f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
)


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Jetson telemetry server is running"})


@app.route("/telemetry", methods=["POST"])
def telemetry():
    try:
        pkt = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"bad JSON: {e}"}), 400

    # Append-only local log — convenience only, never treated as authoritative.
    with open(_session_log_path, "a") as f:
        f.write(json.dumps(pkt) + "\n")

    flags = []
    if not pkt.get("ppgOK", 1):
        flags.append("PPG SENSOR NOT DETECTED")
    bpm = pkt.get("bpm")
    if isinstance(bpm, (int, float)) and not pkt.get("is_transition"):
        if not (BPM_MIN <= bpm <= BPM_MAX):
            flags.append(f"BPM out of range ({bpm})")

    status = " | ".join(flags) if flags else "OK"
    print(
        f"[{pkt.get('elapsed_ms', '?'):>8}] "
        f"{pkt.get('label', '?'):8s} "
        f"trans={pkt.get('is_transition', '?')} "
        f"class={pkt.get('activity_class', '?')} "
        f"bpm={pkt.get('bpm', '?'):>6} "
        f"ppgOK={pkt.get('ppgOK', '?')} "
        f"heap={pkt.get('heap', '?')} "
        f"  {status}"
    )

    return jsonify({"received": True})


if __name__ == "__main__":
    print(f"Logging live telemetry to {_session_log_path}")
    print("Waiting for the device to connect and start pushing telemetry...")
    app.run(host="0.0.0.0", port=8000)

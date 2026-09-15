"""
Option 4 telemetry receiver — UDP variant, currently in use.

Chosen over the HTTP version (server.py) because UDP has no connection
state to lose and no connect() step to hang on. server.py is kept intact
and unused, not deleted, in case we switch back or want to compare.
See project_option4_jetson_plan (Claude memory) for the full reasoning.

THIS IS A CONVENIENCE / LIVE-VIEW LAYER ONLY. It is not the dataset. The
device's onboard flash (retrieved later with log_serial.py) remains the
guaranteed data record regardless of whether this server is even running.

Usage:
    python udp_server.py
"""

import json
import os
import socket
from datetime import datetime

LISTEN_PORT = 8001   # must match JETSON_UDP_PORT in firmware_main/udp_client.h

LOG_DIR = "live_telemetry"
os.makedirs(LOG_DIR, exist_ok=True)

BPM_MIN, BPM_MAX = 40, 180

_session_log_path = os.path.join(
    LOG_DIR, f"live_udp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    print(f"Listening for UDP telemetry on port {LISTEN_PORT}...")
    print(f"Logging live packets to {_session_log_path}")
    print("(Reminder: this is a live-view convenience layer only — the")
    print(" device is recording everything to its own flash regardless.)\n")

    last_elapsed = None

    while True:
        data, addr = sock.recvfrom(2048)

        try:
            pkt = json.loads(data.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            print(f"[WARN] Malformed packet from {addr}: {data!r}")
            continue

        with open(_session_log_path, "a") as f:
            f.write(json.dumps(pkt) + "\n")

        elapsed = pkt.get("elapsed_ms")
        # A big drop in elapsed_ms means the device rebooted (new boot,
        # its own millis() clock restarted) — flag it, since otherwise
        # it silently looks like normal continuous data.
        if isinstance(elapsed, (int, float)) and isinstance(last_elapsed, (int, float)):
            if elapsed < last_elapsed - 1000:
                print(f"  [NOTE] elapsed_ms dropped ({last_elapsed} -> {elapsed}) "
                      f"— device likely rebooted, this is a new boot's timeline.")
        last_elapsed = elapsed

        flags = []
        if not pkt.get("ppgOK", 1):
            flags.append("PPG SENSOR NOT DETECTED")
        bpm = pkt.get("bpm")
        if isinstance(bpm, (int, float)) and not pkt.get("is_transition"):
            if not (BPM_MIN <= bpm <= BPM_MAX):
                flags.append(f"BPM out of range ({bpm})")

        status = " | ".join(flags) if flags else "OK"
        print(
            f"[{elapsed if elapsed is not None else '?':>8}] "
            f"{pkt.get('label', '?'):8s} "
            f"trans={pkt.get('is_transition', '?')} "
            f"class={pkt.get('activity_class', '?')} "
            f"bpm={pkt.get('bpm', '?'):>6} "
            f"ppgOK={pkt.get('ppgOK', '?')} "
            f"heap={pkt.get('heap', '?')} "
            f"  {status}"
        )


if __name__ == "__main__":
    main()

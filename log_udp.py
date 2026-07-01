"""
UDP data logger for WearableMonitor — 5-activity auto session
Requires laptop connected to WiFi network "WearableCollector" (ESP32 hotspot)
Usage: python log_udp.py
Output: experiments/wrist/session_<timestamp>.csv

Session layout (90s total per activity):
  0–15s  → is_transition=True   (body settling, filter out before training)
  15–90s → is_transition=False  (clean data, 75s per activity)
"""

import socket
import csv
import json
import os
from datetime import datetime

UDP_PORT           = 4210
SESSION_SECONDS    = 90    # must match SESSION_MS in firmware (90000 ms)
TRANSITION_SECONDS = 15    # first 15s of each session are transition
OUTPUT_DIR         = "experiments/wrist"
ACTIVITY_LABELS    = ["lying", "sitting", "standing", "walking", "running"]
FIELDNAMES         = ["timestamp", "label", "is_transition",
                      "activity_class", "bpm",
                      "mean_mag", "std_mag", "peak_rel", "peak_max"]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", UDP_PORT))
    sock.settimeout(1.0)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = os.path.join(OUTPUT_DIR,
                            f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    print(f"Listening on UDP port {UDP_PORT}")
    print(f"Make sure your laptop is connected to WiFi: 'WearableCollector'\n")
    print(f"Each session: {TRANSITION_SECONDS}s transition + "
          f"{SESSION_SECONDS - TRANSITION_SECONDS}s clean = {SESSION_SECONDS}s total\n")

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, label in enumerate(ACTIVITY_LABELS):
            print(f"\n{'='*50}")
            print(f"  SESSION {i+1}/{len(ACTIVITY_LABELS)}: {label.upper()}")
            print(f"  {TRANSITION_SECONDS}s transition → {SESSION_SECONDS - TRANSITION_SECONDS}s clean data")
            print(f"  Buzzer signals when done")
            print(f"{'='*50}")

            start      = datetime.now()
            rows_clean = 0
            rows_trans = 0
            in_clean   = False

            while True:
                elapsed = (datetime.now() - start).total_seconds()
                if elapsed >= SESSION_SECONDS:
                    break

                is_transition = elapsed < TRANSITION_SECONDS

                # Print phase change once
                if not is_transition and not in_clean:
                    in_clean = True
                    print(f"  [CLEAN] Recording clean data now...")

                try:
                    data, _ = sock.recvfrom(256)
                    p = json.loads(data.decode())
                    row = {
                        "timestamp":      datetime.now().isoformat(),
                        "label":          label,
                        "is_transition":  is_transition,
                        "activity_class": p.get("a"),
                        "bpm":            p.get("bpm"),
                        "mean_mag":       p.get("mean"),
                        "std_mag":        p.get("std"),
                        "peak_rel":       p.get("pr"),
                        "peak_max":       p.get("pm"),
                    }
                    writer.writerow(row)

                    if is_transition:
                        rows_trans += 1
                        tag = "[TRANS]"
                    else:
                        rows_clean += 1
                        tag = "[DATA] "

                    print(f"  {tag} [{label.upper():8s}]  bpm={row['bpm']:.1f}  "
                          f"std={row['std_mag']:.1f}  t={elapsed:.0f}s")

                except socket.timeout:
                    pass

            print(f"  [OK] {rows_clean} clean rows + {rows_trans} transition rows for '{label}'")

    sock.close()
    print(f"\nAll sessions complete. Saved: {filename}")
    print(f"Tip: filter rows where is_transition==True before training.")


if __name__ == "__main__":
    main()

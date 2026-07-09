"""
Serial retrieval tool for WearableMonitor's onboard flash logging.
Recording happens fully untethered (battery-powered, LittleFS on the ESP32).
This script retrieves whatever session files have piled up since the last dump.

Usage:
    python log_serial.py COM3

Workflow:
    1. Run this script FIRST — it starts listening immediately.
    2. THEN plug in / reset the ESP32 (order matters: the firmware only
       accepts a dump request in a short window after boot, so the script
       needs to already be sending before that window opens).
    3. Each stored participant run is saved as its own timestamped CSV in
       experiments/wrist/, and a quick quality check is printed for each.

Requires: pip install pyserial
"""

import sys
import time
import os
import re
from datetime import datetime

import serial

OUTPUT_DIR       = "experiments/wrist"
BAUD             = 115200
RETRY_SECONDS    = 10     # how long to keep poking for the dump window
RETRY_INTERVAL   = 0.2

BPM_MIN, BPM_MAX = 40, 180      # outside this band (non-transition rows) = flag
MIN_CLEAN_ROWS   = 50           # fewer clean rows than this for a label = flag

FILE_START_RE = re.compile(r"----- FILE: (\S+) -----")
FILE_END_RE   = re.compile(r"----- END: (\S+) -----")


def quality_check(local_path):
    import csv as csvmod

    per_label = {}
    with open(local_path, newline="") as f:
        reader = csvmod.DictReader(f)
        for row in reader:
            label = row["label"]
            per_label.setdefault(label, {"clean": 0, "trans": 0, "bpm_out_of_range": 0})
            is_trans = row["is_transition"] == "1"
            bucket = per_label[label]
            if is_trans:
                bucket["trans"] += 1
            else:
                bucket["clean"] += 1
                try:
                    bpm = float(row["bpm"])
                    if not (BPM_MIN <= bpm <= BPM_MAX):
                        bucket["bpm_out_of_range"] += 1
                except ValueError:
                    pass

    print(f"  Quality check for {os.path.basename(local_path)}:")
    if not per_label:
        print("    [FLAG] File is empty — nothing was recorded.")
        return

    for label, stats in per_label.items():
        flags = []
        if stats["clean"] < MIN_CLEAN_ROWS:
            flags.append(f"only {stats['clean']} clean rows (expected ~187)")
        if stats["bpm_out_of_range"] > 0:
            flags.append(f"{stats['bpm_out_of_range']} BPM readings outside {BPM_MIN}-{BPM_MAX}")

        status = "OK" if not flags else "FLAG: " + "; ".join(flags)
        print(f"    {label:10s} clean={stats['clean']:4d}  trans={stats['trans']:3d}  {status}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python log_serial.py <COM_PORT>")
        print("Example: python log_serial.py COM3")
        sys.exit(1)

    port = sys.argv[1]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Waiting for {port} to appear (plug in the ESP32 now if you haven't)...")
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(port, BAUD, timeout=0.5)
        except serial.SerialException:
            time.sleep(0.5)
    print(f"Opened {port} at {BAUD} baud.")

    print(f"Listening — reset the ESP32 if it hasn't booted yet (retrying send for up to {RETRY_SECONDS}s)...")

    current_file    = None
    current_path    = None
    saved_paths     = []
    dump_started    = False
    deadline        = time.time() + RETRY_SECONDS

    while True:
        # Keep poking until the firmware's dump-request window catches it
        if not dump_started and time.time() < deadline:
            ser.write(b"\n")

        line_bytes = ser.readline()
        if not line_bytes:
            if not dump_started and time.time() >= deadline:
                print("[TIMEOUT] No dump window caught. Reset the board again — script is still listening.")
                deadline = time.time() + RETRY_SECONDS
            continue

        line = line_bytes.decode(errors="replace").rstrip()
        if not line:
            continue

        print(f"  {line}")

        if "SESSION DUMP START" in line:
            dump_started = True
            continue

        if "SESSION DUMP END" in line:
            print(f"\nDone. Retrieved {len(saved_paths)} file(s).\n")
            for p in saved_paths:
                if os.path.basename(p).startswith("session_"):
                    quality_check(p)
                else:
                    print(f"  (skipping quality check for {os.path.basename(p)} — not a session file)")
            break

        m = FILE_START_RE.search(line)
        if m:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(m.group(1))
            current_path = os.path.join(OUTPUT_DIR, f"{name}_{timestamp}{ext}")
            current_file = open(current_path, "w", newline="")
            print(f"  -> saving to {current_path}")
            continue

        m = FILE_END_RE.search(line)
        if m:
            if current_file:
                current_file.close()
                saved_paths.append(current_path)
            current_file = None
            current_path = None
            continue

        if current_file:
            current_file.write(line + "\n")

    ser.close()


if __name__ == "__main__":
    main()

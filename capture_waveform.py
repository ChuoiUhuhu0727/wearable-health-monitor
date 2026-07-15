"""
One-off waveform demo — reads the CSV printed by firmware_capture/main.cpp
(env: waveform_capture) over Serial and plots the raw PPG (IR) and
accelerometer waveforms.

NOT part of the real dataset/training pipeline — the actual dataset
(firmware_ble/) never logs raw waveforms, only reduced features. This is
purely to show what the raw signal looks like (e.g. for the professor).

Usage:
    1. PlatformIO: select env "waveform_capture", Upload.
    2. python capture_waveform.py COM3
    3. Put the sensor on your wrist within the 3s prep window printed by
       the board, then hold still-ish for the ~20s capture.
"""

import csv
import os
import sys
from datetime import datetime

import serial
import matplotlib.pyplot as plt

OUTPUT_DIR = "experiments/waveform_demo"
BAUD = 115200


def main():
    if len(sys.argv) < 2:
        print("Usage: python capture_waveform.py <COM_PORT>")
        sys.exit(1)

    port = sys.argv[1]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"waveform_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    print(f"Waiting for {port} to appear (plug in the ESP32 now if you haven't)...")
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(port, BAUD, timeout=1.0)
        except serial.SerialException:
            pass
    print(f"Opened {port}. Reset the board if it hasn't booted yet.\n")

    rows = []
    header_seen = False
    with open(out_path, "w", newline="") as f:
        while True:
            line_bytes = ser.readline()
            if not line_bytes:
                continue
            line = line_bytes.decode(errors="replace").rstrip()
            if not line:
                continue

            print(f"  {line}")

            if line == "elapsed_ms,ax,ay,az,ir":
                header_seen = True
                f.write(line + "\n")
                continue

            if "CAPTURE DONE" in line:
                break

            if header_seen:
                f.write(line + "\n")
                parts = line.split(",")
                if len(parts) == 5:
                    rows.append(parts)

    ser.close()
    print(f"\nSaved {len(rows)} samples to {out_path}")

    if not rows:
        print("[ERROR] No samples captured — check the sensor was connected and try again.")
        return

    t = [int(r[0]) / 1000.0 for r in rows]
    ax = [int(r[1]) for r in rows]
    ay = [int(r[2]) for r in rows]
    az = [int(r[3]) for r in rows]
    ir = [int(r[4]) for r in rows]

    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    fig.suptitle(os.path.basename(out_path))

    axes[0].plot(t, ir, color="crimson", linewidth=0.8)
    axes[0].set_ylabel("IR (raw)")
    axes[0].set_title("PPG waveform (raw IR)", fontsize=10, loc="left")

    axes[1].plot(t, ax, label="ax", linewidth=0.8)
    axes[1].plot(t, ay, label="ay", linewidth=0.8)
    axes[1].plot(t, az, label="az", linewidth=0.8)
    axes[1].set_ylabel("accel (raw)")
    axes[1].set_title("Acceleration waveform (raw ax/ay/az)", fontsize=10, loc="left")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].set_xlabel("elapsed time (s)")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_png = os.path.splitext(out_path)[0] + "_plot.png"
    fig.savefig(out_png, dpi=130)
    print(f"Saved plot to {out_png}")


if __name__ == "__main__":
    main()

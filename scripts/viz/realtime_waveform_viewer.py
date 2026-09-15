"""
Live raw waveform viewer — same firmware/protocol as capture_waveform.py
(firmware/capture/main.cpp, env "waveform_capture": 100Hz, elapsed_ms,ax,ay,az,ir
over Serial), but plots WHILE the data streams in instead of after capture ends.

That firmware does one fixed ~20s capture per boot, then stops (see its own
comments for why — it's a standalone demo, not the real dataset pipeline).
This script keeps running across multiple boots: after "CAPTURE DONE", it just
waits for the next header line, so you can reset the board repeatedly without
restarting the script.

Usage:
    1. PlatformIO: select env "waveform_capture", Upload.
    2. python scripts/viz/realtime_waveform_viewer.py COM3
    3. Put the sensor on your wrist within the 3s prep window, hold still-ish.
    4. To watch another run: just reset the board — this script keeps listening.
"""

import sys
import collections

import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

BAUD = 115200
WINDOW_S = 10          # seconds of history shown on screen at once
SAMPLE_HZ = 100        # must match firmware/capture/main.cpp's SAMPLE_HZ
MAXLEN = WINDOW_S * SAMPLE_HZ


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/viz/realtime_waveform_viewer.py <COM_PORT>")
        sys.exit(1)
    port = sys.argv[1]

    print(f"Waiting for {port} to appear (plug in the ESP32 now if you haven't)...")
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(port, BAUD, timeout=0)  # non-blocking reads
        except serial.SerialException:
            pass
    print(f"Opened {port}. Reset the board if it hasn't booted yet.\n")

    t_buf = collections.deque(maxlen=MAXLEN)
    ir_buf = collections.deque(maxlen=MAXLEN)
    ax_buf = collections.deque(maxlen=MAXLEN)
    ay_buf = collections.deque(maxlen=MAXLEN)
    az_buf = collections.deque(maxlen=MAXLEN)

    state = {"header_seen": False, "line_buf": b""}

    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    fig.suptitle(f"Live raw waveform — {port}")
    (ir_line,) = axes[0].plot([], [], color="crimson", linewidth=0.8)
    axes[0].set_ylabel("IR (raw)")
    axes[0].set_title("PPG waveform (raw IR)", fontsize=10, loc="left")

    (ax_line,) = axes[1].plot([], [], label="ax", linewidth=0.8)
    (ay_line,) = axes[1].plot([], [], label="ay", linewidth=0.8)
    (az_line,) = axes[1].plot([], [], label="az", linewidth=0.8)
    axes[1].set_ylabel("accel (raw)")
    axes[1].set_title("Acceleration waveform (raw ax/ay/az)", fontsize=10, loc="left")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[1].set_xlabel("elapsed time in current capture (s)")

    def read_available_lines():
        """Non-blocking: drain whatever full lines are sitting in the serial buffer."""
        n = ser.in_waiting
        if n:
            state["line_buf"] += ser.read(n)
        lines = []
        while b"\n" in state["line_buf"]:
            line, state["line_buf"] = state["line_buf"].split(b"\n", 1)
            lines.append(line.decode(errors="replace").strip())
        return lines

    def update(_frame):
        for line in read_available_lines():
            if not line:
                continue
            if line == "elapsed_ms,ax,ay,az,ir":
                state["header_seen"] = True
                t_buf.clear(); ir_buf.clear(); ax_buf.clear(); ay_buf.clear(); az_buf.clear()
                print("[new capture started]")
                continue
            if "CAPTURE DONE" in line:
                state["header_seen"] = False
                print("[capture ended — reset the board for another run]")
                continue
            if not state["header_seen"]:
                print(f"  {line}")  # setup/status messages from the board
                continue

            parts = line.split(",")
            if len(parts) != 5:
                continue
            try:
                t_ms, ax_v, ay_v, az_v, ir_v = (int(p) for p in parts)
            except ValueError:
                continue
            t_buf.append(t_ms / 1000.0)
            ir_buf.append(ir_v)
            ax_buf.append(ax_v)
            ay_buf.append(ay_v)
            az_buf.append(az_v)

        if t_buf:
            ir_line.set_data(t_buf, ir_buf)
            ax_line.set_data(t_buf, ax_buf)
            ay_line.set_data(t_buf, ay_buf)
            az_line.set_data(t_buf, az_buf)
            for ax_ in axes:
                ax_.relim()
                ax_.autoscale_view()
        return ir_line, ax_line, ay_line, az_line

    ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()

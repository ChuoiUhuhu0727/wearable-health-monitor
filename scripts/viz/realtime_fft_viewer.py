"""
Live FFT viewer — same firmware/protocol as realtime_waveform_viewer.py
(firmware/capture/main.cpp, env "waveform_capture": 100Hz, elapsed_ms,ax,ay,az,ir
over Serial). Instead of the time-domain waveform, this shows the live frequency
spectrum of the raw IR (PPG) signal and of accel magnitude — useful for seeing
where the cardiac component sits (~0.7-3 Hz for 42-180 bpm) versus where motion
artifact energy shows up, directly on real hardware.

Same per-boot behavior as the waveform viewer: firmware does one fixed ~20s
capture then stops; this script keeps running across resets.

Usage:
    1. PlatformIO: select env "waveform_capture", Upload.
    2. python scripts/viz/realtime_fft_viewer.py COM3
    3. Put the sensor on your wrist within the 3s prep window, hold still-ish
       (or move on purpose to see motion-artifact frequency content shift).
    4. To watch another run: just reset the board — this script keeps listening.
"""

import sys
import collections

import numpy as np
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

BAUD = 115200
SAMPLE_HZ = 100        # must match firmware/capture/main.cpp's SAMPLE_HZ
FFT_WINDOW_N = 512     # ~5.12s of history per FFT — trade-off: bigger = finer
                       # frequency resolution (100/512 ~= 0.2 Hz/bin) but slower
                       # to react to a changing signal
MAX_FREQ_HZ = 15       # cardiac + most motion-artifact content is well under this;
                       # cropping the x-axis keeps the interesting region readable


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/viz/realtime_fft_viewer.py <COM_PORT>")
        sys.exit(1)
    port = sys.argv[1]

    print(f"Waiting for {port} to appear (plug in the ESP32 now if you haven't)...")
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(port, BAUD, timeout=0)
        except serial.SerialException:
            pass
    print(f"Opened {port}. Reset the board if it hasn't booted yet.\n")

    ir_buf = collections.deque(maxlen=FFT_WINDOW_N)
    accmag_buf = collections.deque(maxlen=FFT_WINDOW_N)
    state = {"header_seen": False, "line_buf": b""}

    freqs = np.fft.rfftfreq(FFT_WINDOW_N, d=1.0 / SAMPLE_HZ)
    freq_mask = freqs <= MAX_FREQ_HZ
    hann = np.hanning(FFT_WINDOW_N)

    fig, axes = plt.subplots(2, 1, figsize=(12, 6))
    fig.suptitle(f"Live FFT — {port}  (window = {FFT_WINDOW_N} samples = {FFT_WINDOW_N/SAMPLE_HZ:.1f}s)")

    (ir_fft_line,) = axes[0].plot([], [], color="crimson", linewidth=1.0)
    axes[0].set_ylabel("|FFT| (IR)")
    axes[0].set_title("PPG (IR) spectrum — cardiac band ~0.7-3 Hz (42-180 bpm)", fontsize=10, loc="left")
    axes[0].axvspan(0.7, 3.0, color="green", alpha=0.08)

    (acc_fft_line,) = axes[1].plot([], [], color="tab:blue", linewidth=1.0)
    axes[1].set_ylabel("|FFT| (accel mag)")
    axes[1].set_title("Acceleration magnitude spectrum — motion artifact energy", fontsize=10, loc="left")
    axes[1].set_xlabel("frequency (Hz)")

    for ax_ in axes:
        ax_.set_xlim(0, MAX_FREQ_HZ)

    def read_available_lines():
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
                ir_buf.clear(); accmag_buf.clear()
                print("[new capture started]")
                continue
            if "CAPTURE DONE" in line:
                state["header_seen"] = False
                print("[capture ended — reset the board for another run]")
                continue
            if not state["header_seen"]:
                print(f"  {line}")
                continue

            parts = line.split(",")
            if len(parts) != 5:
                continue
            try:
                _t_ms, ax_v, ay_v, az_v, ir_v = (int(p) for p in parts)
            except ValueError:
                continue
            ir_buf.append(ir_v)
            accmag_buf.append((ax_v**2 + ay_v**2 + az_v**2) ** 0.5)

        if len(ir_buf) == FFT_WINDOW_N:
            ir_arr = np.array(ir_buf, dtype=float)
            ir_arr -= ir_arr.mean()  # drop DC so the huge DC bin doesn't swamp the plot
            ir_mag = np.abs(np.fft.rfft(ir_arr * hann))[freq_mask]
            ir_fft_line.set_data(freqs[freq_mask], ir_mag)
            axes[0].set_ylim(0, max(ir_mag.max() * 1.2, 1))

            acc_arr = np.array(accmag_buf, dtype=float)
            acc_arr -= acc_arr.mean()
            acc_mag = np.abs(np.fft.rfft(acc_arr * hann))[freq_mask]
            acc_fft_line.set_data(freqs[freq_mask], acc_mag)
            axes[1].set_ylim(0, max(acc_mag.max() * 1.2, 1))

        return ir_fft_line, acc_fft_line

    ani = animation.FuncAnimation(fig, update, interval=150, cache_frame_data=False)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()

"""
Plot the raw PPG (wrist + fingertip) and acceleration waveforms retrieved
from the real firmware_ble/ pipeline (raw_ppg_N.csv / raw_accel_N.csv /
raw_ppg2_N.csv, added 2026-07-15/16 — see FIRMWARE_OVERVIEW.md).

Different from capture_waveform.py: that one reads live Serial output from
the standalone firmware_capture/ demo (~20s, separate schema). This reads
the actual retrieved CSVs for a real participant run from experiments/wrist/.

Usage:
    pip install matplotlib
    python visualize_raw_waveform.py                          # most recent raw_ppg_*.csv, full run
    python visualize_raw_waveform.py path/to/raw_ppg_N.csv
    python visualize_raw_waveform.py --zoom 120 130            # only elapsed_ms 120s-130s — zoomed in
    python visualize_raw_waveform.py path/to/raw_ppg_N.csv --zoom 120 130

    --zoom is for seeing individual heartbeat shape: the full-run plot
    compresses ~450s into one figure, so a single ~0.8s beat is far too
    thin to see. A 5-15s window is usually enough to make individual
    pulses visible.
"""

import argparse
import csv
import glob
import os
import re

import matplotlib.pyplot as plt

OUTPUT_DIR = "experiments/wrist"


def pick_most_recent_raw_ppg():
    candidates = glob.glob(os.path.join(OUTPUT_DIR, "raw_ppg_*.csv"))
    candidates = [p for p in candidates if not os.path.basename(p).startswith("raw_ppg2_")]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def session_number(raw_ppg_path):
    m = re.match(r"raw_ppg_(\d+)_", os.path.basename(raw_ppg_path))
    return m.group(1) if m else None


def find_sibling(kind, n, directory):
    """kind: 'raw_accel' or 'raw_ppg2' — same session number N, any timestamp."""
    matches = glob.glob(os.path.join(directory, f"{kind}_{n}_*.csv"))
    return max(matches, key=os.path.getmtime) if matches else None


def read_two_col(path, value_col):
    t, v = [], []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                t.append(int(row["elapsed_ms"]) / 1000.0)
                v.append(int(row[value_col]))
            except (KeyError, ValueError):
                continue
    return t, v


def read_accel(path):
    t, ax, ay, az = [], [], [], []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                t.append(int(row["elapsed_ms"]) / 1000.0)
                ax.append(int(row["ax"]))
                ay.append(int(row["ay"]))
                az.append(int(row["az"]))
            except (KeyError, ValueError):
                continue
    return t, ax, ay, az


def clip(t, *series_lists, zoom):
    """Keep only points with zoom[0] <= t <= zoom[1] (same index cut across all series)."""
    if zoom is None:
        return (t,) + series_lists
    lo, hi = zoom
    idx = [i for i, ti in enumerate(t) if lo <= ti <= hi]
    t_clipped = [t[i] for i in idx]
    clipped_lists = tuple([[s[i] for i in idx] for s in series_list] for series_list in series_lists)
    return (t_clipped,) + clipped_lists


def plot_raw(raw_ppg_path, zoom=None):
    n = session_number(raw_ppg_path)
    directory = os.path.dirname(raw_ppg_path) or "."
    raw_accel_path = find_sibling("raw_accel", n, directory) if n else None
    raw_ppg2_path = find_sibling("raw_ppg2", n, directory) if n else None

    # Zoomed in tight enough that individual 10ms samples matter — draw
    # markers too, not just a connecting line, so real sample points (vs.
    # interpolation across a gap — see CHANGELOG 2026-07-17 raw-capture
    # gap note) are visible.
    tight = zoom is not None and (zoom[1] - zoom[0]) <= 20
    line_kwargs = dict(linewidth=0.8, marker=".", markersize=3) if tight else dict(linewidth=0.6)

    panels = []

    t_ppg, ir = read_two_col(raw_ppg_path, "ir")
    if not t_ppg:
        print(f"[ERROR] No usable rows in {raw_ppg_path}")
        return
    t_ppg_z, (ir_z,) = clip(t_ppg, [ir], zoom=zoom)
    if zoom is not None and not t_ppg_z:
        print(f"[ERROR] --zoom {zoom[0]} {zoom[1]} has no samples in it — "
              f"file covers {t_ppg[0]:.1f}s to {t_ppg[-1]:.1f}s.")
        return
    panels.append(("PPG waveform — wrist (raw IR)", t_ppg_z, [ir_z], ["crimson"], ["wrist"]))

    if raw_ppg2_path:
        t_ppg2, ir2 = read_two_col(raw_ppg2_path, "ir")
        if t_ppg2:
            t_ppg2_z, (ir2_z,) = clip(t_ppg2, [ir2], zoom=zoom)
            panels.append(("PPG waveform — fingertip (raw IR)", t_ppg2_z, [ir2_z], ["darkorange"], ["fingertip"]))
    else:
        print("[INFO] No matching raw_ppg2_*.csv found — skipping fingertip panel.")

    if raw_accel_path:
        t_acc, ax, ay, az = read_accel(raw_accel_path)
        if t_acc:
            t_acc_z, (ax_z, ay_z, az_z) = clip(t_acc, [ax, ay, az], zoom=zoom)
            panels.append(("Acceleration waveform (raw ax/ay/az)", t_acc_z, [ax_z, ay_z, az_z],
                            ["#4C72B0", "#55A868", "#C44E52"], ["ax", "ay", "az"]))
    else:
        print("[INFO] No matching raw_accel_*.csv found — skipping accel panel.")

    fig, axes = plt.subplots(len(panels), 1, figsize=(14, 3.2 * len(panels)), sharex=True)
    if len(panels) == 1:
        axes = [axes]
    title_suffix = f"  [zoom {zoom[0]}-{zoom[1]}s]" if zoom is not None else ""
    fig.suptitle(f"session {n} — {os.path.basename(raw_ppg_path)}{title_suffix}")

    for ax_plot, (title, t, series_list, colors, labels) in zip(axes, panels):
        for series, color, label in zip(series_list, colors, labels):
            ax_plot.plot(t, series, color=color, label=label, **line_kwargs)
        ax_plot.set_title(title, fontsize=10, loc="left")
        if len(series_list) > 1:
            ax_plot.legend(loc="upper right", fontsize=8)

    axes[-1].set_xlabel("elapsed time (s)")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    suffix = f"_zoom_{zoom[0]}_{zoom[1]}" if zoom is not None else ""
    out_png = os.path.splitext(raw_ppg_path)[0].replace("raw_ppg_", "raw_waveform_") + suffix + "_plot.png"
    fig.savefig(out_png, dpi=130)
    print(f"Saved plot to {out_png}")

    print(f"wrist PPG: {len(t_ppg_z)} samples plotted "
          f"(full file: {len(t_ppg)} samples, {t_ppg[0]:.1f}s-{t_ppg[-1]:.1f}s span)")

    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", help="path to raw_ppg_N.csv (default: most recent in experiments/wrist/)")
    parser.add_argument("--zoom", nargs=2, type=float, metavar=("START_S", "END_S"),
                         help="only plot elapsed_ms between START_S and END_S — for seeing individual beat shape")
    args = parser.parse_args()

    csv_path = args.path
    if csv_path is None:
        csv_path = pick_most_recent_raw_ppg()
        if csv_path is None:
            print(f"No raw_ppg_*.csv files found in {OUTPUT_DIR}/. Pass a path explicitly.")
            raise SystemExit(1)
        print(f"No path given — using most recent file: {csv_path}")

    if not os.path.isfile(csv_path):
        print(f"[ERROR] File not found: {csv_path}")
        raise SystemExit(1)

    zoom = tuple(args.zoom) if args.zoom else None
    if zoom is not None and zoom[0] >= zoom[1]:
        print(f"[ERROR] --zoom start ({zoom[0]}) must be less than end ({zoom[1]}).")
        raise SystemExit(1)

    plot_raw(csv_path, zoom=zoom)

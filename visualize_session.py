"""
Plot the waveform of a collected session CSV so you can eyeball whether the
data actually looks like the 5 activities it claims to be, before trusting
it for training.

Works on either kind of CSV this project produces:
  - session_*.csv   (from log_serial.py — the real flash-backed dataset)
  - ble_live_*.csv  (from log_ble.py — live-view only, may have gaps)
Both now carry ppg_contact (live PPG contact status per row) and bpm_fresh
(whether a beat was actually detected recently, vs. bpm just holding its
last value); ble_live_*.csv has one extra column beyond that (seconds_left),
used here if present but not required.

Usage:
    pip install matplotlib
    python visualize_session.py                      # most recent CSV in experiments/wrist/
    python visualize_session.py path/to/session.csv   # a specific file
"""

import csv
import glob
import os
import sys

import matplotlib.pyplot as plt

OUTPUT_DIR = "experiments/wrist"

# Same order as ACTIVITY_LABELS in firmware_ble/main.cpp and log_ble.py —
# used only to assign a stable, repeatable color per activity.
ACTIVITY_COLORS = {
    "lying":    "#4C72B0",
    "sitting":  "#55A868",
    "standing": "#C44E52",
    "walking":  "#8172B2",
    "running":  "#CCB974",
}


def pick_most_recent_csv():
    candidates = [p for p in glob.glob(os.path.join(OUTPUT_DIR, "*.csv"))]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def read_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                row = {
                    "t_s":           float(r["elapsed_ms"]) / 1000.0,
                    "label":         r["label"],
                    "is_transition": r["is_transition"] == "1",
                    "bpm":           float(r["bpm"]),
                    "mean_mag":      float(r["mean_mag"]),
                    "std_mag":       float(r["std_mag"]),
                }
            except (KeyError, ValueError):
                continue  # skip malformed/partial rows (e.g. a mid-write BLE packet)
            ppg = r.get("ppg_contact")
            row["ppg_ok"] = None if ppg in (None, "") else (ppg == "1")
            fresh = r.get("bpm_fresh")
            row["bpm_fresh"] = None if fresh in (None, "") else (fresh == "1")
            rows.append(row)
    return rows


def build_segments(rows):
    """Contiguous runs of (label, is_transition) -> [(start_s, end_s, label, is_transition), ...]"""
    segments = []
    cur = None
    for row in rows:
        if cur is None or row["label"] != cur[2] or row["is_transition"] != cur[3]:
            if cur is not None:
                segments.append(cur)
            cur = [row["t_s"], row["t_s"], row["label"], row["is_transition"]]
        else:
            cur[1] = row["t_s"]
    if cur is not None:
        segments.append(cur)
    return segments


def shade_segments(ax, segments):
    for start, end, label, is_transition in segments:
        color = ACTIVITY_COLORS.get(label, "#888888")
        ax.axvspan(start, end, color=color, alpha=0.12 if is_transition else 0.28, linewidth=0)


def plot_session(path):
    rows = read_rows(path)
    if not rows:
        print(f"[ERROR] No usable rows in {path} — file empty or all rows malformed.")
        return

    segments = build_segments(rows)
    t       = [r["t_s"] for r in rows]
    bpm     = [r["bpm"] for r in rows]
    mean_m  = [r["mean_mag"] for r in rows]
    std_m   = [r["std_mag"] for r in rows]

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle(os.path.basename(path))

    for ax, series, title, ylabel in [
        (axes[0], bpm,    "Heart rate (BPM)",              "bpm"),
        (axes[1], mean_m, "Motion — mean acceleration mag", "mean_mag"),
        (axes[2], std_m,  "Motion — std of acceleration",   "std_mag"),
    ]:
        shade_segments(ax, segments)
        ax.plot(t, series, color="black", linewidth=0.8)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=10, loc="left")

    # Mark rows where the PPG sensor reported lost contact, if that column exists.
    ppg_bad_points = [(r["t_s"], r["bpm"]) for r in rows if r["ppg_ok"] is False]
    if ppg_bad_points:
        bad_t, bad_bpm = zip(*ppg_bad_points)
        axes[0].scatter(bad_t, bad_bpm, color="red", s=8, zorder=5, label="PPG contact lost")

    # Mark rows where bpm_fresh says no beat was actually detected recently —
    # different from contact loss: sensor contact can be fine while the beat
    # detector still hasn't found a new peak (see CHANGELOG 2026-07-14).
    stale_points = [(r["t_s"], r["bpm"]) for r in rows if r["bpm_fresh"] is False]
    if stale_points:
        stale_t, stale_bpm = zip(*stale_points)
        axes[0].scatter(stale_t, stale_bpm, color="orange", s=8, zorder=4, label="BPM stale")

    if ppg_bad_points or stale_points:
        axes[0].legend(loc="upper right", fontsize=8)

    axes[-1].set_xlabel("elapsed time (s)")

    # Legend for activity colors, built once from segments actually present.
    seen = []
    handles = []
    for _, _, label, _ in segments:
        if label not in seen:
            seen.append(label)
            handles.append(plt.Rectangle((0, 0), 1, 1, color=ACTIVITY_COLORS.get(label, "#888"), alpha=0.4, label=label))
    fig.legend(handles=handles, loc="upper right", ncol=len(handles), fontsize=9)

    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_png = os.path.splitext(path)[0] + "_plot.png"
    fig.savefig(out_png, dpi=130)
    print(f"Saved plot to {out_png}")

    n_bpm_bad = sum(1 for b in bpm if not (40 <= b <= 180))
    n_ppg_bad = sum(1 for r in rows if r["ppg_ok"] is False)
    n_bpm_stale = sum(1 for r in rows if r["bpm_fresh"] is False)
    print(f"Rows: {len(rows)}  |  BPM out of 40-180 range: {n_bpm_bad}  |  "
          f"PPG contact lost: {n_ppg_bad}  |  BPM stale: {n_bpm_stale}")

    plt.show()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = pick_most_recent_csv()
        if csv_path is None:
            print(f"No CSV files found in {OUTPUT_DIR}/. Pass a path explicitly.")
            sys.exit(1)
        print(f"No path given — using most recent file: {csv_path}")

    if not os.path.isfile(csv_path):
        print(f"[ERROR] File not found: {csv_path}")
        sys.exit(1)

    plot_session(csv_path)

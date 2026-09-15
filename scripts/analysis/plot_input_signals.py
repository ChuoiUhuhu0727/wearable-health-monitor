"""
Figures showing the actual input signals of Subsystem B.

WHY THESE ARE NEEDED
    The report's central claim is that the wrist PPG channel rarely contains a
    detectable pulse. Every waveform it currently shows, however, is the FINGERTIP
    channel -- the reference -- not the wrist channel the claim is about. A reader has
    to take the 9.6% figure on trust.

    These figures show the measured signal itself, so the claim can be checked by eye
    the same way the fingertip reference was.

PRODUCES
    paper/figures/input_signals_stack.png
        The same 12 seconds seen by every input the filters use: fingertip reference,
        wrist measurement, accelerometer reference, and the wrist channel after NLMS.
        One panel per signal, so "what goes in" and "what comes out" sit together.

    paper/figures/wrist_waveform_by_activity.png
        The wrist channel across all five activities, each panel marked with whether a
        heart rate could be extracted from it at all.

USAGE
    python scripts/analysis/plot_input_signals.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hr_estimator_v2 import estimate_bpm_window
from lms_denoise_mvp import (BASE, FS, HR_BAND, NLMS_TAPS, PARTICIPANTS, bandpass,
                             build_common_grid, build_lagged, load_raw, nlms_filter,
                             resample)

OUT_DIR = "paper/figures"
DEMO_PID = "P17"
DEMO_ACT = "running"
SHOW_S = 12.0
ACTS = ["lying", "sitting", "standing", "walking", "running"]

C_REF, C_WRIST, C_ACC, C_FILT = "#2E7D45", "#C2643B", "#7A8CA3", "#8E44AD"
C_OK, C_BAD = "#2E7D45", "#B3261E"

plt.rcParams.update({"figure.dpi": 120, "font.size": 10,
                     "axes.titlesize": 11, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def load_all(pid):
    """Every channel resampled onto one common grid, bandpassed, plus NLMS output."""
    f = PARTICIPANTS[pid]
    t_w, ir_w = load_raw(f"{BASE}/{f['wrist']}", "ir")
    t_f, ir_f = load_raw(f"{BASE}/{f['fingertip']}", "ir")
    acc = pd.read_csv(f"{BASE}/{f['accel']}")
    t_a = acc["elapsed_ms"].values.astype(float)

    grid = build_common_grid(t_w, t_f, t_a)
    wrist = bandpass(resample(t_w, ir_w, grid), FS, HR_BAND)
    finger = bandpass(resample(t_f, ir_f, grid), FS, HR_BAND)
    mag = np.sqrt(acc["ax"] ** 2 + acc["ay"] ** 2 + acc["az"] ** 2).values
    ref = bandpass(resample(t_a, mag, grid), FS, HR_BAND)
    filtered = nlms_filter(wrist, build_lagged(ref, NLMS_TAPS))

    sess = pd.read_csv(f"{BASE}/{f['session']}").sort_values("elapsed_ms")
    idx = np.clip(np.searchsorted(sess["elapsed_ms"].values, grid, side="right") - 1,
                  0, len(sess) - 1)
    return dict(grid=grid, finger=finger, wrist=wrist, ref=ref, filtered=filtered,
                label=sess["label"].values[idx],
                is_trans=sess["is_transition"].values[idx])


def window_of(d, activity, seconds=SHOW_S):
    m = (d["label"] == activity) & (d["is_trans"] == 0)
    if not m.any():
        return None
    mid = np.median(d["grid"][m])
    half = seconds * 1000 / 2
    sel = m & (d["grid"] >= mid - half) & (d["grid"] <= mid + half)
    return sel


def verdict(sig):
    """What the v2 estimator makes of this stretch -- a bpm, or nothing readable."""
    n = int(8.0 * FS)
    if len(sig) < n:
        return np.nan
    bpm, _ = estimate_bpm_window(sig[:n], FS)
    return bpm


def fig_input_stack(d):
    sel = window_of(d, DEMO_ACT)
    t = (d["grid"][sel] - d["grid"][sel][0]) / 1000.0

    panels = [
        ("finger", C_REF, "① Tham chiếu — PPG đầu ngón tay", "kênh đối chứng"),
        ("wrist", C_WRIST, "② Đầu vào chính — PPG cổ tay", "kênh cần đo"),
        ("ref", C_ACC, "③ Tham chiếu nhiễu — |gia tốc| 3 trục", "đầu vào cho bộ lọc"),
        ("filtered", C_FILT, "④ Đầu ra — PPG cổ tay sau NLMS", "kết quả khử nhiễu"),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(11, 9.6), sharex=True)
    for ax, (key, colour, title, role) in zip(axes, panels):
        sig = d[key][sel]
        ax.plot(t, sig, color=colour, lw=1.0)
        ax.set_ylabel("biên độ\n(đã lọc dải)")
        if key == "ref":
            note = "(không phải tín hiệu tim — đây là chuyển động)"
            ax.set_title(f"{title}   —   {role}   {note}", loc="left")
        else:
            bpm = verdict(sig)
            ok = not np.isnan(bpm)
            txt = f"đọc được {bpm:.0f} bpm" if ok else "KHÔNG đọc được nhịp nào"
            ax.set_title(f"{title}   —   {role}   →   {txt}", loc="left",
                         color=C_OK if ok else C_BAD)
    axes[-1].set_xlabel("giây")
    fig.suptitle(f"Toàn bộ tín hiệu đầu vào của bộ lọc, cùng một khoảng thời gian "
                 f"({DEMO_PID}, lúc {DEMO_ACT})", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    p = f"{OUT_DIR}/input_signals_stack.png"
    fig.savefig(p); plt.close(fig)
    return p


def fig_wrist_by_activity(d):
    fig, axes = plt.subplots(5, 1, figsize=(10.5, 9.0), sharex=True)
    for ax, act in zip(axes, ACTS):
        sel = window_of(d, act)
        if sel is None or sel.sum() < FS * 4:
            ax.set_visible(False)
            continue
        sig = d["wrist"][sel]
        t = (d["grid"][sel] - d["grid"][sel][0]) / 1000.0
        ax.plot(t, sig, color=C_WRIST, lw=0.9)
        bpm = verdict(sig)
        ok = not np.isnan(bpm)
        ax.set_title(f"{act}   →   "
                     f"{f'đọc được {bpm:.0f} bpm' if ok else 'KHÔNG đọc được nhịp nào'}",
                     loc="left", color=C_OK if ok else C_BAD)
        ax.set_ylabel("biên độ")
    axes[-1].set_xlabel("giây")
    fig.suptitle(f"PPG cổ tay qua cả 5 hoạt động ({DEMO_PID}) — kênh mà báo cáo này "
                 f"kết luận là hầu như không mang nhịp tim",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    p = f"{OUT_DIR}/wrist_waveform_by_activity.png"
    fig.savefig(p); plt.close(fig)
    return p


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = load_all(DEMO_PID)

    print(f"Đọc thử nhịp tim trên từng kênh ({DEMO_PID}, {DEMO_ACT}):")
    sel = window_of(d, DEMO_ACT)
    for key, name in [("finger", "đầu ngón tay"), ("wrist", "cổ tay"),
                      ("filtered", "cổ tay + NLMS")]:
        b = verdict(d[key][sel])
        print(f"  {name:<16}: {'%.1f bpm' % b if not np.isnan(b) else 'không đọc được'}")

    print(f"\nPPG cổ tay theo hoạt động ({DEMO_PID}):")
    for act in ACTS:
        s = window_of(d, act)
        b = verdict(d["wrist"][s]) if s is not None else np.nan
        print(f"  {act:<10}: {'%.1f bpm' % b if not np.isnan(b) else 'không đọc được'}")

    paths = [fig_input_stack(d), fig_wrist_by_activity(d)]
    print("\nĐã lưu:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()

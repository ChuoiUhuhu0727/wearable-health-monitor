"""
Is the fingertip PPG actually a trustworthy heart-rate reference?

WHY THIS SCRIPT EXISTS
    The whole adaptive-filter comparison (lms_denoise_mvp.py) measures every filter
    as "error in bpm against the fingertip channel". That makes the fingertip the
    ruler. The project proposal assumed it was a clean ruler -- "transmissive PPG,
    minimal motion artifact" -- and that assumption was never tested.

    This script tests it, using the cheapest check available: a human heart beats
    faster when running than when lying down. Any reference that does not show that
    is not measuring heart rate, whatever number it prints.

WHAT IT PRODUCES
    paper/figures/gt_sanity_by_activity.png
        Reference heart rate per activity, per participant. The check is simply
        whether the running bar sits above the lying bar.

    paper/figures/gt_waveform_<PID>.png
        The raw fingertip waveform itself, lying vs running, with detected beats
        marked. This is the "look at the actual signal" step: count the peaks by
        eye and compare against what the algorithm reported for the same seconds.

    Two participants are plotted deliberately: one where the reference behaves
    physiologically (positive control) and one where it does not. If the failure
    were a bug in the estimator it would show up in both.

USAGE
    python scripts/analysis/check_ground_truth_sanity.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from lms_denoise_mvp import (BASE, FS, HR_BAND, PARTICIPANTS, bandpass, build_common_grid,
                             load_raw, resample, run_pipeline)

OUT_DIR = "paper/figures"
SLICE_S = 12.0           # seconds of waveform to show per panel
MIN_BEAT_GAP_S = 0.33    # 0.33s => at most 180 bpm, keeps find_peaks from double-counting
ACTS = ["lying", "sitting", "standing", "walking", "running"]

C_CALM, C_HARD, C_BAD, C_OK = "#2E6F95", "#C2643B", "#B3261E", "#2E7D45"

plt.rcParams.update({"figure.dpi": 120, "font.size": 10,
                     "axes.titlesize": 11.5, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def fingertip_slice(pid, files, activity):
    """Return (seconds, bandpassed fingertip) for a mid-segment slice of one activity."""
    sess = pd.read_csv(f"{BASE}/{files['session']}")
    seg = sess[(sess["label"] == activity) & (sess["is_transition"] == 0)]
    if seg.empty:
        return None, None
    mid = seg["elapsed_ms"].median()

    t_f, v_f = load_raw(f"{BASE}/{files['fingertip']}", "ir")
    grid = build_common_grid(t_f)
    sig = bandpass(resample(t_f, v_f, grid), FS, HR_BAND)

    half = SLICE_S * 1000 / 2
    m = (grid >= mid - half) & (grid <= mid + half)
    if m.sum() < FS * 4:
        return None, None
    return (grid[m] - grid[m][0]) / 1000.0, sig[m]


def count_beats(sig):
    """Peaks in the bandpassed slice -> bpm, the number a human gets by eye."""
    peaks, _ = find_peaks(sig, distance=int(MIN_BEAT_GAP_S * FS),
                          prominence=np.std(sig) * 0.5)
    if len(peaks) < 2:
        return peaks, np.nan
    return peaks, 60.0 / np.mean(np.diff(peaks) / FS)


def beat_diagnostics(sig, peaks):
    """Distinguish 'these are all real beats' from 'every second peak is a dicrotic
    notch, so the count is doubled'.

    A dicrotic notch sits on the falling edge of its own beat, so notch-to-next-beat
    is much longer than beat-to-notch: the intervals ALTERNATE. Real beats at a
    steady rate are evenly spaced. Comparing odd-numbered against even-numbered gaps
    separates the two cases without needing to judge the shape of the waveform by eye.

    A large odd/even AMPLITUDE ratio with a near-1.0 odd/even INTERVAL ratio means
    beat-to-beat amplitude alternation. That pattern repeats every two beats, which
    puts a strong component at half the true rate into the spectrum -- exactly the
    subharmonic an FFT-based estimator can lock onto.
    """
    iv = np.diff(peaks) / FS
    amp = sig[peaks]
    odd_iv, even_iv = iv[0::2], iv[1::2]
    odd_a, even_a = amp[0::2], amp[1::2]
    ratio = lambda a, b: max(a, b) / min(a, b) if min(a, b) > 0 else np.inf
    d = {
        "n_peaks": len(peaks),
        "interval_mean_s": iv.mean(),
        "interval_cv": iv.std() / iv.mean(),
        "interval_odd_even_ratio": ratio(odd_iv.mean(), even_iv.mean()),
        "amp_odd_even_ratio": ratio(odd_a.mean(), even_a.mean()),
    }
    if d["interval_odd_even_ratio"] > 1.35:
        d["verdict"] = "đỉnh xen kẽ dicrotic notch → số đếm bị nhân đôi"
    elif d["interval_cv"] > 0.15:
        d["verdict"] = "nhịp không đều → tín hiệu nhiễu chuyển động thật sự"
    elif d["amp_odd_even_ratio"] > 1.5:
        d["verdict"] = "nhịp đều, biên độ xen kẽ → sinh hài phụ ở đúng 1/2 nhịp thật"
    else:
        d["verdict"] = "nhịp đều, biên độ đều → số đếm đáng tin"
    return d


def figure_by_activity(gt):
    piv = gt.pivot_table(index="participant_id", columns="label",
                         values="gt_bpm", aggfunc="median")[ACTS]
    pids = list(piv.index)
    x = np.arange(len(pids))
    w = 0.16

    fig, ax = plt.subplots(figsize=(11, 4.6))
    shades = ["#BFD3E6", "#9EBCDA", "#7FA5CC", C_CALM, C_HARD]
    for i, (a, c) in enumerate(zip(ACTS, shades)):
        ax.bar(x + (i - 2) * w, piv[a], w, label=a, color=c)

    # Two conditions, both required. Running must be clearly above rest, AND running
    # must be the highest of the five -- a reference that puts standing above running
    # is broken even if it happens to clear the first test.
    for j, pid in enumerate(pids):
        row = piv.loc[pid]
        ok = (row["running"] > row["lying"] + 20) and (row.idxmax() == "running")
        ax.text(j, row.max() + 6, "hợp lý" if ok else "BẤT THƯỜNG",
                ha="center", fontsize=9, fontweight="bold", color=C_OK if ok else C_BAD)

    ax.set_xticks(x); ax.set_xticklabels(pids)
    ax.set_ylabel("nhịp tim tham chiếu (bpm, trung vị)")
    ax.set_title("Kiểm tra sinh lý: nhịp tim khi chạy có cao hơn khi nằm không?")
    ax.legend(ncol=5, frameon=False, fontsize=9, loc="upper left")
    ax.set_ylim(0, max(piv.max()) * 1.28)
    fig.tight_layout()
    p = f"{OUT_DIR}/gt_sanity_by_activity.png"
    fig.savefig(p); plt.close(fig)
    return p


def figure_waveform(pid, files, reported):
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.4), sharey=True)
    saved = []
    for ax, act, colour in zip(axes, ["lying", "running"], [C_CALM, C_HARD]):
        t, sig = fingertip_slice(pid, files, act)
        if t is None:
            ax.set_visible(False)
            continue
        peaks, bpm_eye = count_beats(sig)
        diag = beat_diagnostics(sig, peaks)
        ax.plot(t, sig, color=colour, lw=1.0)
        ax.plot(t[peaks], sig[peaks], "v", color="black", ms=5,
                label=f"{len(peaks)} đỉnh · {diag['verdict']}")
        bpm_alg = reported.get((pid, act), np.nan)
        agree = abs(bpm_eye - bpm_alg) < 15
        ax.set_title(f"{pid} — {act}:  đếm đỉnh ≈ {bpm_eye:.0f} bpm   |   "
                     f"thuật toán báo {bpm_alg:.0f} bpm   "
                     f"{'✓ khớp' if agree else '✗ LỆCH'}",
                     color=C_OK if agree else C_BAD)
        ax.legend(frameon=False, fontsize=8.5, loc="upper right")
        ax.set_ylabel("PPG đầu ngón tay\n(đã lọc dải)")
        print(f"  {pid} {act:>8s}: đếm {bpm_eye:6.1f} bpm | thuật toán {bpm_alg:6.1f} bpm"
              f" | CV={diag['interval_cv']:.2f}"
              f" | tỉ lệ khoảng lẻ/chẵn={diag['interval_odd_even_ratio']:.2f}"
              f" | tỉ lệ biên độ={diag['amp_odd_even_ratio']:.2f}"
              f" | {diag['verdict']}")
        saved.append(act)
    axes[-1].set_xlabel("giây")
    fig.tight_layout()
    p = f"{OUT_DIR}/gt_waveform_{pid}.png"
    fig.savefig(p); plt.close(fig)
    return p


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    gt = pd.concat([run_pipeline(pid, files, "magnitude")
                    for pid, files in PARTICIPANTS.items()], ignore_index=True)
    gt = gt.dropna(subset=["gt_bpm"])

    print("\n=== Nhịp tim tham chiếu theo hoạt động (trung vị, bpm) ===")
    piv = gt.pivot_table(index="participant_id", columns="label",
                         values="gt_bpm", aggfunc="median")[ACTS]
    piv["chạy − nằm"] = piv["running"] - piv["lying"]
    print(piv.to_string(float_format=lambda v: f"{v:.1f}"))

    suspect = [p for p in piv.index
               if piv.loc[p, "chạy − nằm"] < 20
               or piv.loc[p, ACTS].idxmax() != "running"]
    print(f"\nTham chiếu KHÔNG vượt qua kiểm tra sinh lý: {suspect or 'không có ai'}")
    print(f"Tham chiếu hợp lý: {[p for p in piv.index if p not in suspect]}")

    paths = [figure_by_activity(gt)]

    # One failing participant and one passing one, so the comparison is controlled.
    reported = {(r.participant_id, r.label): v for r, v in
                zip(gt.itertuples(), gt["gt_bpm"])}
    med = gt.groupby(["participant_id", "label"])["gt_bpm"].median().to_dict()
    worst = piv["chạy − nằm"].idxmin()
    best = piv["chạy − nằm"].idxmax()
    print(f"\nVẽ dạng sóng: {worst} (bất thường nhất) và {best} (đối chứng dương)")
    for pid in (worst, best):
        paths.append(figure_waveform(pid, PARTICIPANTS[pid], med))

    print("\nĐã lưu:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()

"""
Figures for the Subsystem B report.

The headline of that report is not an error figure -- it is how often a heart rate can
be read out of each signal at all. These two charts carry that argument:

    paper/figures/hr_coverage_by_signal.png
        Share of windows yielding a readable pulse, fingertip vs wrist vs each filter.

    paper/figures/hr_coverage_vs_threshold.png
        The same comparison swept across the strictness threshold, to show the gap is a
        property of the signals and not of one arbitrary cut-off.

USAGE
    python scripts/analysis/plot_filter_results_v2.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import hr_estimator_v2 as v2
from lms_denoise_mvp import PARTICIPANTS
from lms_denoise_v2 import run_participant

OUT_DIR = "paper/figures"
THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.40]
C_REF, C_WRIST, C_FILT, C_BAD = "#2E7D45", "#C2643B", "#7A8CA3", "#B3261E"

plt.rcParams.update({"figure.dpi": 120, "font.size": 10,
                     "axes.titlesize": 12, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def coverage_at(threshold):
    v2.MAX_INTERVAL_CV = threshold
    df = pd.concat([run_participant(p, f) for p, f in PARTICIPANTS.items()],
                   ignore_index=True)
    return df


def figure_coverage(df):
    cols = [("gt_bpm", "Đầu ngón tay\n(tham chiếu)", C_REF),
            ("base_bpm", "Cổ tay\nkhông lọc", C_WRIST),
            ("lms_bpm", "Cổ tay\n+ NLMS", C_FILT),
            ("rls_bpm", "Cổ tay\n+ RLS", C_FILT),
            ("wiener_bpm", "Cổ tay\n+ Wiener", C_FILT)]
    vals = [100 * df[c].notna().mean() for c, _, _ in cols]

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    bars = ax.bar([n for _, n, _ in cols], vals, color=[c for _, _, c in cols], width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.1, f"{v:.1f}%",
                ha="center", fontweight="bold", fontsize=10.5)

    ax.axhline(vals[0], color=C_REF, ls="--", lw=1.2, alpha=0.7)
    ax.set_ylabel("% cửa sổ đọc được nhịp tim")
    ax.set_ylim(0, max(vals) * 1.32)
    ax.set_title("Bao nhiêu phần trăm thời gian tín hiệu thực sự chứa nhịp đập?")
    ax.annotate("mất gần 3/4 số cửa sổ\nkhi chuyển từ ngón tay sang cổ tay",
                xy=(1, vals[1] + 1), xytext=(1.75, vals[0] * 0.82),
                fontsize=9.5, color=C_BAD,
                arrowprops=dict(arrowstyle="->", color=C_BAD, lw=1.3))
    fig.tight_layout()
    p = f"{OUT_DIR}/hr_coverage_by_signal.png"
    fig.savefig(p); plt.close(fig)
    return p


def figure_threshold_sweep(rows):
    thr = [r[0] for r in rows]
    ref = [r[1] for r in rows]
    wrist = [r[2] for r in rows]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.3),
                                  gridspec_kw={"width_ratios": [1.25, 1]})
    ax.plot(thr, ref, "o-", color=C_REF, lw=2, ms=6, label="Đầu ngón tay")
    ax.plot(thr, wrist, "o-", color=C_WRIST, lw=2, ms=6, label="Cổ tay (không lọc)")
    ax.fill_between(thr, wrist, ref, color=C_WRIST, alpha=0.10)
    ax.invert_xaxis()
    ax.set_xlabel("ngưỡng chấp nhận  ←  càng sang phải càng khắt khe")
    ax.set_ylabel("% cửa sổ đọc được")
    ax.set_title("Siết chuẩn thì cổ tay biến mất trước")
    ax.legend(frameon=False)

    ratio = [r / w if w > 0 else np.nan for r, w in zip(ref, wrist)]
    ax2.plot(thr, ratio, "o-", color=C_BAD, lw=2, ms=6)
    ax2.invert_xaxis()
    ax2.set_xlabel("ngưỡng chấp nhận")
    ax2.set_ylabel("ngón tay / cổ tay (lần)")
    ax2.set_title("Khoảng cách giữa hai kênh")
    for x, y in zip(thr, ratio):
        ax2.annotate(f"{y:.1f}×", (x, y), textcoords="offset points",
                     xytext=(0, 8), ha="center", fontsize=9)
    ax2.set_ylim(0, max(ratio) * 1.28)

    fig.tight_layout()
    p = f"{OUT_DIR}/hr_coverage_vs_threshold.png"
    fig.savefig(p); plt.close(fig)
    return p


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    rows = []
    df_default = None
    for t in THRESHOLDS:
        df = coverage_at(t)
        ref = 100 * df["gt_bpm"].notna().mean()
        wrist = 100 * df["base_bpm"].notna().mean()
        rows.append((t, ref, wrist))
        print(f"ngưỡng CV {t:.2f}: ngón tay {ref:5.1f}% | cổ tay {wrist:5.1f}% "
              f"| {ref/wrist:.1f}x")
        if t == 0.25:
            df_default = df

    paths = [figure_coverage(df_default), figure_threshold_sweep(rows)]
    print("\nĐã lưu:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()

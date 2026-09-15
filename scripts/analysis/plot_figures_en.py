"""
English-labelled versions of every figure used in the report.

WHY THIS EXISTS
    The Vietnamese report and the English report share the same underlying analysis, so
    they must share the same numbers. Rather than maintaining two copies of the plotting
    logic, this script imports the data-preparation functions from the original scripts
    and only re-renders the labels. If the analysis changes, both language versions change
    together.

OUTPUT
    paper/figures_en/ -- eleven PNG files matching paper/figures/ one for one.

USAGE
    python scripts/analysis/plot_figures_en.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.tree import plot_tree

import hr_estimator_v2 as v2
from check_ground_truth_sanity import beat_diagnostics, count_beats, fingertip_slice
from lms_denoise_mvp import PARTICIPANTS, run_pipeline
from lms_denoise_v2 import run_participant
from plot_input_signals import load_all, verdict, window_of
from plot_waveform_to_features import (STRIDE_SIZE, WINDOW_SIZE, IMU_HZ, features,
                                       load_magnitude, slice_of)

OUT = "paper/figures_en"
ACTS = ["lying", "sitting", "standing", "walking", "running"]
STATIC = ACTS[:3]
C_STATIC, C_DYNAMIC, C_ACCENT = "#C2643B", "#2E6F95", "#1F3B63"
C_REF, C_ACC, C_FILT = "#2E7D45", "#7A8CA3", "#8E44AD"
C_OK, C_BAD = "#2E7D45", "#B3261E"
COLOR = {a: (C_STATIC if a in STATIC else C_DYNAMIC) for a in ACTS}

plt.rcParams.update({"figure.dpi": 120, "font.size": 10,
                     "axes.titlesize": 11.5, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


# ----------------------------------------------------------------- Chapter 3
def fig_waveform_to_features(df):
    sl = slice_of(df, "walking", seconds=6)
    w, t = sl["mag"].values[:WINDOW_SIZE], sl["s"].values[:WINDOW_SIZE]
    f = features(w)

    fig, ax = plt.subplots(figsize=(10.5, 4.9))
    ax.plot(t, w, color=C_DYNAMIC, lw=1.5, zorder=3, label="|acceleration| in one window")
    ax.axhline(f["mean_mag"], color=C_ACCENT, lw=1.6, zorder=2)
    ax.fill_between(t, f["mean_mag"] - f["std_mag"], f["mean_mag"] + f["std_mag"],
                    color=C_ACCENT, alpha=0.13, zorder=1)
    i_pk = int(np.argmax(w))
    ax.plot(t[i_pk], f["peak_max"], "v", color=C_BAD, ms=11, zorder=4)

    span = w.max() - w.min()
    ax.annotate(f"(1) mean_mag = {f['mean_mag']:.0f}\n     average magnitude",
                xy=(t[3], f["mean_mag"]), xytext=(t[2], f["mean_mag"] - span * 0.42),
                fontsize=9.5, color=C_ACCENT,
                arrowprops=dict(arrowstyle="->", color=C_ACCENT, lw=1.2))
    ax.annotate(f"(2) std_mag = {f['std_mag']:.0f}\n     band width: how much it shakes",
                xy=(t[len(t) // 2], f["mean_mag"] + f["std_mag"]),
                xytext=(t[len(t) // 2] - 0.5, f["mean_mag"] + span * 0.45),
                fontsize=9.5, color=C_ACCENT,
                arrowprops=dict(arrowstyle="->", color=C_ACCENT, lw=1.2))
    ax.annotate(f"(3) peak_max = {f['peak_max']:.0f}\n     highest point",
                xy=(t[i_pk], f["peak_max"]),
                xytext=(t[i_pk] + 0.25, f["peak_max"] - span * 0.1),
                fontsize=9.5, color=C_BAD,
                arrowprops=dict(arrowstyle="->", color=C_BAD, lw=1.2))
    ax.text(0.995, 0.04,
            f"(4) peak_rel = peak_max / mean_mag = {f['peak_max']:.0f} / "
            f"{f['mean_mag']:.0f} = {f['peak_rel']:.2f}\n"
            f"     how far the peak rises above the average - how spiky the signal is",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9.5, color="#5B2333",
            bbox=dict(boxstyle="round,pad=0.45", fc="#FBF3F5", ec="#D8B7C2"))

    ax.set_xlabel(f"seconds  (one window = {WINDOW_SIZE} samples at {IMU_HZ} Hz = "
                  f"{WINDOW_SIZE/IMU_HZ:.1f} s, sliding every {STRIDE_SIZE/IMU_HZ:.1f} s)")
    ax.set_ylabel("|acceleration|")
    ax.set_title("From one window of raw signal to the four numbers the model sees (walking)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(f"{OUT}/waveform_to_features.png"); plt.close(fig)


def fig_waveform_all(df):
    fig, axes = plt.subplots(5, 1, figsize=(10.5, 9.2), sharex=True, sharey=True)
    slices = {a: slice_of(df, a) for a in ACTS}
    ymax = max(s["mag"].max() for s in slices.values() if s is not None)
    for ax, a in zip(axes, ACTS):
        sl = slices[a]
        ax.plot(sl["s"], sl["mag"], color=COLOR[a], lw=0.9)
        f = features(sl["mag"].values[:WINDOW_SIZE])
        ax.set_ylabel("|acceleration|")
        ax.set_title(f"{a}   -   mean_mag {f['mean_mag']:.0f} · std_mag {f['std_mag']:.0f}"
                     f" · peak_max {f['peak_max']:.0f} · peak_rel {f['peak_rel']:.2f}",
                     loc="left")
    axes[-1].set_xlabel("seconds")
    axes[0].set_ylim(0, ymax * 1.05)
    fig.suptitle("Raw acceleration of all five activities (P16, same vertical scale)",
                 fontsize=13, fontweight="bold", y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(f"{OUT}/waveform_by_activity.png"); plt.close(fig)


def fig_static_zoom(df):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4))
    for ax, a in zip(axes, STATIC):
        sl = slice_of(df, a)
        ax.plot(sl["s"], sl["mag"], color=C_STATIC, lw=0.9)
        f = features(sl["mag"].values[:WINDOW_SIZE])
        ax.set_title(f"{a}\nstd_mag {f['std_mag']:.1f} · peak_rel {f['peak_rel']:.2f}")
        ax.set_xlabel("seconds")
    axes[0].set_ylabel("|acceleration|")
    fig.suptitle("The three static postures, each on its own scale - still not separable",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(f"{OUT}/waveform_static_zoom.png"); plt.close(fig)


def fig_features_by_activity():
    rows = []
    for pid in PARTICIPANTS:
        d = load_magnitude(pid)
        for a in ACTS:
            seg = d[(d["label"] == a) & (d["is_transition"] == 0)]["mag"].values
            for st in range(0, len(seg) - WINDOW_SIZE + 1, STRIDE_SIZE):
                rows.append({"label": a, **features(seg[st:st + WINDOW_SIZE])})
    feat = pd.DataFrame(rows)

    names = [("mean_mag", "(1) mean_mag"), ("std_mag", "(2) std_mag"),
             ("peak_max", "(3) peak_max"), ("peak_rel", "(4) peak_rel")]
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.9))
    for ax, (col, title) in zip(axes, names):
        data = [feat.loc[feat["label"] == a, col].values for a in ACTS]
        bp = ax.boxplot(data, tick_labels=ACTS, patch_artist=True, showfliers=False,
                        widths=0.6, medianprops=dict(color="black", lw=1.4))
        for patch, a in zip(bp["boxes"], ACTS):
            patch.set_facecolor(COLOR[a]); patch.set_alpha(0.78)
        if col != "peak_rel":
            ax.set_yscale("log")
        ax.set_title(title); ax.tick_params(axis="x", rotation=45)
    fig.suptitle(f"Distribution of the four features across activities "
                 f"({len(PARTICIPANTS)} participants with raw capture, {len(feat)} windows)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    fig.savefig(f"{OUT}/features_by_activity.png"); plt.close(fig)


# ----------------------------------------------------------------- Chapter 4
def fig_input_stack(d):
    sel = window_of(d, "running")
    t = (d["grid"][sel] - d["grid"][sel][0]) / 1000.0
    panels = [("finger", C_REF, "(1) Reference - fingertip PPG", "control channel"),
              ("wrist", C_STATIC, "(2) Main input - wrist PPG", "the channel under study"),
              ("ref", C_ACC, "(3) Noise reference - |acceleration|", "input to the filter"),
              ("filtered", C_FILT, "(4) Output - wrist PPG after NLMS", "filtering result")]
    fig, axes = plt.subplots(4, 1, figsize=(11, 9.6), sharex=True)
    for ax, (key, colour, title, role) in zip(axes, panels):
        sig = d[key][sel]
        ax.plot(t, sig, color=colour, lw=1.0)
        ax.set_ylabel("amplitude\n(band-passed)")
        if key == "ref":
            ax.set_title(f"{title}   -   {role}   (not a cardiac signal - this is motion)",
                         loc="left")
        else:
            bpm = verdict(sig)
            ok = not np.isnan(bpm)
            txt = f"{bpm:.0f} bpm readable" if ok else "NO heart rate readable"
            ax.set_title(f"{title}   -   {role}   ->   {txt}", loc="left",
                         color=C_OK if ok else C_BAD)
    axes[-1].set_xlabel("seconds")
    fig.suptitle("Every input signal the filter uses, over the same time window "
                 "(P17, running)", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    fig.savefig(f"{OUT}/input_signals_stack.png"); plt.close(fig)


def fig_gt_sanity(gt):
    piv = gt.pivot_table(index="participant_id", columns="label",
                         values="gt_bpm", aggfunc="median")[ACTS]
    pids = list(piv.index)
    x, w = np.arange(len(pids)), 0.16
    fig, ax = plt.subplots(figsize=(11, 4.6))
    shades = ["#BFD3E6", "#9EBCDA", "#7FA5CC", C_DYNAMIC, C_STATIC]
    for i, (a, c) in enumerate(zip(ACTS, shades)):
        ax.bar(x + (i - 2) * w, piv[a], w, label=a, color=c)
    for j, pid in enumerate(pids):
        row = piv.loc[pid]
        ok = (row["running"] > row["lying"] + 20) and (row.idxmax() == "running")
        ax.text(j, row.max() + 6, "plausible" if ok else "IMPLAUSIBLE", ha="center",
                fontsize=9, fontweight="bold", color=C_OK if ok else C_BAD)
    ax.set_xticks(x); ax.set_xticklabels(pids)
    ax.set_ylabel("reference heart rate (bpm, median)")
    ax.set_title("Physiological check: is heart rate higher when running than lying down?")
    ax.legend(ncol=5, frameon=False, fontsize=9, loc="upper left")
    ax.set_ylim(0, piv.max().max() * 1.28)
    fig.tight_layout(); fig.savefig(f"{OUT}/gt_sanity_by_activity.png"); plt.close(fig)


def fig_gt_waveform(pid, med):
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.4), sharey=True)
    for ax, act, colour in zip(axes, ["lying", "running"], [C_DYNAMIC, C_STATIC]):
        t, sig = fingertip_slice(pid, PARTICIPANTS[pid], act)
        peaks, bpm_eye = count_beats(sig)
        diag = beat_diagnostics(sig, peaks)
        note = {"đỉnh xen kẽ dicrotic notch → số đếm bị nhân đôi":
                "alternating dicrotic notches - count is doubled",
                "nhịp không đều → tín hiệu nhiễu chuyển động thật sự":
                "irregular beats - genuine motion noise",
                "nhịp đều, biên độ xen kẽ → sinh hài phụ ở đúng 1/2 nhịp thật":
                "even spacing, alternating amplitude - creates a half-rate component",
                "nhịp đều, biên độ đều → số đếm đáng tin":
                "even spacing and amplitude - count is reliable"}[diag["verdict"]]
        ax.plot(t, sig, color=colour, lw=1.0)
        ax.plot(t[peaks], sig[peaks], "v", color="black", ms=5,
                label=f"{len(peaks)} peaks · {note}")
        bpm_alg = med.get((pid, act), np.nan)
        agree = abs(bpm_eye - bpm_alg) < 15
        ax.set_title(f"{pid} - {act}:  counted by eye ~{bpm_eye:.0f} bpm   |   "
                     f"algorithm reports {bpm_alg:.0f} bpm   "
                     f"{'MATCH' if agree else 'MISMATCH'}",
                     color=C_OK if agree else C_BAD)
        ax.legend(frameon=False, fontsize=8.5, loc="upper right")
        ax.set_ylabel("fingertip PPG\n(band-passed)")
    axes[-1].set_xlabel("seconds")
    fig.tight_layout(); fig.savefig(f"{OUT}/gt_waveform_{pid}.png"); plt.close(fig)


def fig_coverage(df):
    cols = [("gt_bpm", "Fingertip\n(reference)", C_REF),
            ("base_bpm", "Wrist\nunfiltered", C_STATIC),
            ("lms_bpm", "Wrist\n+ NLMS", "#7A8CA3"),
            ("rls_bpm", "Wrist\n+ RLS", "#7A8CA3"),
            ("wiener_bpm", "Wrist\n+ Wiener", "#7A8CA3")]
    vals = [100 * df[c].notna().mean() for c, _, _ in cols]
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    bars = ax.bar([n for _, n, _ in cols], vals, color=[c for _, _, c in cols], width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.1, f"{v:.1f}%",
                ha="center", fontweight="bold", fontsize=10.5)
    ax.axhline(vals[0], color=C_REF, ls="--", lw=1.2, alpha=0.7)
    ax.set_ylabel("% of windows with a readable heart rate")
    ax.set_ylim(0, max(vals) * 1.32)
    ax.set_title("How often does the signal actually contain a heartbeat?")
    ax.annotate("almost three quarters of the windows\nare lost moving from finger to wrist",
                xy=(1, vals[1] + 1), xytext=(1.75, vals[0] * 0.82), fontsize=9.5,
                color=C_BAD, arrowprops=dict(arrowstyle="->", color=C_BAD, lw=1.3))
    fig.tight_layout(); fig.savefig(f"{OUT}/hr_coverage_by_signal.png"); plt.close(fig)


def fig_wrist_by_activity(d):
    fig, axes = plt.subplots(5, 1, figsize=(10.5, 9.0), sharex=True)
    for ax, act in zip(axes, ACTS):
        sel = window_of(d, act)
        sig = d["wrist"][sel]
        t = (d["grid"][sel] - d["grid"][sel][0]) / 1000.0
        ax.plot(t, sig, color=C_STATIC, lw=0.9)
        bpm = verdict(sig)
        ok = not np.isnan(bpm)
        ax.set_title(f"{act}   ->   "
                     f"{f'{bpm:.0f} bpm readable' if ok else 'NO heart rate readable'}",
                     loc="left", color=C_OK if ok else C_BAD)
        ax.set_ylabel("amplitude")
    axes[-1].set_xlabel("seconds")
    fig.suptitle("Wrist PPG across all five activities (P17) - the channel this report "
                 "concludes carries almost no heartbeat", fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    fig.savefig(f"{OUT}/wrist_waveform_by_activity.png"); plt.close(fig)


def fig_threshold_sweep(rows):
    thr = [r[0] for r in rows]
    ref, wrist = [r[1] for r in rows], [r[2] for r in rows]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.3),
                                  gridspec_kw={"width_ratios": [1.25, 1]})
    ax.plot(thr, ref, "o-", color=C_REF, lw=2, ms=6, label="Fingertip")
    ax.plot(thr, wrist, "o-", color=C_STATIC, lw=2, ms=6, label="Wrist (unfiltered)")
    ax.fill_between(thr, wrist, ref, color=C_STATIC, alpha=0.10)
    ax.invert_xaxis()
    ax.set_xlabel("acceptance threshold  <-  stricter towards the right")
    ax.set_ylabel("% of windows readable")
    ax.set_title("Tighten the standard and the wrist disappears first")
    ax.legend(frameon=False)

    ratio = [r / w if w > 0 else np.nan for r, w in zip(ref, wrist)]
    ax2.plot(thr, ratio, "o-", color=C_BAD, lw=2, ms=6)
    ax2.invert_xaxis()
    ax2.set_xlabel("acceptance threshold")
    ax2.set_ylabel("finger / wrist (times)")
    ax2.set_title("Gap between the two channels")
    for x, y in zip(thr, ratio):
        ax2.annotate(f"{y:.1f}x", (x, y), textcoords="offset points", xytext=(0, 8),
                     ha="center", fontsize=9)
    ax2.set_ylim(0, max(ratio) * 1.28)
    fig.tight_layout(); fig.savefig(f"{OUT}/hr_coverage_vs_threshold.png"); plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)

    print("Chapter 3 figures...")
    d16 = load_magnitude("P16")
    fig_waveform_to_features(d16)
    fig_waveform_all(d16)
    fig_static_zoom(d16)
    fig_features_by_activity()

    print("Chapter 4 figures...")
    gt = pd.concat([run_pipeline(p, f, "magnitude") for p, f in PARTICIPANTS.items()],
                   ignore_index=True).dropna(subset=["gt_bpm"])
    med = gt.groupby(["participant_id", "label"])["gt_bpm"].median().to_dict()
    fig_gt_sanity(gt)
    for pid in ("P17", "P16"):
        fig_gt_waveform(pid, med)

    d17 = load_all("P17")
    fig_input_stack(d17)
    fig_wrist_by_activity(d17)

    rows = []
    for t in [0.15, 0.20, 0.25, 0.30, 0.40]:
        v2.MAX_INTERVAL_CV = t
        df = pd.concat([run_participant(p, f) for p, f in PARTICIPANTS.items()],
                       ignore_index=True)
        rows.append((t, 100 * df["gt_bpm"].notna().mean(),
                     100 * df["base_bpm"].notna().mean()))
        if t == 0.25:
            fig_coverage(df)
    fig_threshold_sweep(rows)

    print(f"\nDone. {len(os.listdir(OUT))} figures written to {OUT}/")


if __name__ == "__main__":
    main()

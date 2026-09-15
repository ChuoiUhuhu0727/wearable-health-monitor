"""
Figures for the Subsystem A report: what the raw signal looks like, and how the four
features are derived from it.

WHY
    The report argues that the four features cannot separate lying/sitting/standing
    because all four are functions of accelerometer MAGNITUDE, which is invariant to
    rotation. That argument is made in words and in summary statistics. These figures
    let a reader see the raw waveform the device actually receives and follow, step by
    step, how a 2.4-second slice of it becomes four numbers.

PRODUCES
    paper/figures/waveform_by_activity.png
        Raw accelerometer magnitude for all five activities on one shared y-axis.

    paper/figures/waveform_static_zoom.png
        The three static postures again, each on its own scale, to show they stay
        indistinguishable even when the amplitude difference is removed.

    paper/figures/waveform_to_features.png
        One window annotated with the geometric meaning of each of the four features.

    paper/figures/features_by_activity.png
        Distribution of each feature across the five activities, pooled over every
        participant that has raw capture -- which of the four separates what.

NOTE ON FEATURE COUNT
    The deployed classifier uses FOUR features (mean_mag, std_mag, peak_rel, peak_max),
    not five. All four are computed on-device; see firmware/ble/main.cpp:738-750.

USAGE
    python scripts/analysis/plot_waveform_to_features.py
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lms_denoise_mvp import BASE, PARTICIPANTS

OUT_DIR = "paper/figures"
IMU_HZ = 25
WINDOW_SIZE = 60          # samples -> 2.4 s, matching the firmware
STRIDE_SIZE = 10          # samples -> 0.4 s
SHOW_S = 10.0             # seconds of waveform per panel
DEMO_PID = "P16"          # participant used for the single-session waveform panels

ACTS = ["lying", "sitting", "standing", "walking", "running"]
STATIC = ACTS[:3]
C_STATIC, C_DYNAMIC = "#C2643B", "#2E6F95"
COLOR = {a: (C_STATIC if a in STATIC else C_DYNAMIC) for a in ACTS}

plt.rcParams.update({"figure.dpi": 120, "font.size": 10,
                     "axes.titlesize": 11, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})


def load_magnitude(pid):
    """Raw accel magnitude on its native timebase, with the protocol label per sample."""
    files = PARTICIPANTS[pid]
    acc = pd.read_csv(f"{BASE}/{files['accel']}")
    mag = np.sqrt(acc["ax"].astype(float) ** 2 + acc["ay"].astype(float) ** 2
                  + acc["az"].astype(float) ** 2)
    t = acc["elapsed_ms"].values.astype(float)

    sess = pd.read_csv(f"{BASE}/{files['session']}").sort_values("elapsed_ms")
    idx = np.searchsorted(sess["elapsed_ms"].values, t, side="right") - 1
    idx = np.clip(idx, 0, len(sess) - 1)
    return pd.DataFrame({"t_ms": t, "mag": mag.values,
                         "label": sess["label"].values[idx],
                         "is_transition": sess["is_transition"].values[idx]})


def slice_of(df, activity, seconds=SHOW_S):
    seg = df[(df["label"] == activity) & (df["is_transition"] == 0)]
    if seg.empty:
        return None
    mid = seg["t_ms"].median()
    half = seconds * 1000 / 2
    s = seg[(seg["t_ms"] >= mid - half) & (seg["t_ms"] <= mid + half)]
    return pd.DataFrame({"s": (s["t_ms"].values - s["t_ms"].values[0]) / 1000.0,
                         "mag": s["mag"].values})


def features(window):
    """The exact four the firmware computes -- see firmware/ble/main.cpp:738-750."""
    mean_mag = window.mean()
    std_mag = window.std()
    peak_max = window.max()
    peak_rel = peak_max / mean_mag if mean_mag > 0 else 0.0
    return dict(mean_mag=mean_mag, std_mag=std_mag,
                peak_rel=peak_rel, peak_max=peak_max)


def fig_waveform_all(df):
    fig, axes = plt.subplots(5, 1, figsize=(10.5, 9.2), sharex=True, sharey=True)
    ymax = 0
    slices = {}
    for a in ACTS:
        sl = slice_of(df, a)
        slices[a] = sl
        if sl is not None:
            ymax = max(ymax, sl["mag"].max())

    for ax, a in zip(axes, ACTS):
        sl = slices[a]
        if sl is None:
            ax.set_visible(False)
            continue
        ax.plot(sl["s"], sl["mag"], color=COLOR[a], lw=0.9)
        f = features(sl["mag"].values[:WINDOW_SIZE])
        ax.set_ylabel("|gia tốc|")
        ax.set_title(f"{a}   —   mean_mag {f['mean_mag']:.0f} · std_mag {f['std_mag']:.0f}"
                     f" · peak_max {f['peak_max']:.0f} · peak_rel {f['peak_rel']:.2f}",
                     loc="left")
    axes[-1].set_xlabel("giây")
    axes[0].set_ylim(0, ymax * 1.05)
    fig.suptitle(f"Dạng sóng gia tốc thô của 5 hoạt động ({DEMO_PID}, cùng thang đo)",
                 fontsize=13, fontweight="bold", y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    p = f"{OUT_DIR}/waveform_by_activity.png"
    fig.savefig(p); plt.close(fig)
    return p


def fig_static_zoom(df):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4))
    for ax, a in zip(axes, STATIC):
        sl = slice_of(df, a)
        if sl is None:
            ax.set_visible(False)
            continue
        ax.plot(sl["s"], sl["mag"], color=C_STATIC, lw=0.9)
        f = features(sl["mag"].values[:WINDOW_SIZE])
        ax.set_title(f"{a}\nstd_mag {f['std_mag']:.1f} · peak_rel {f['peak_rel']:.2f}")
        ax.set_xlabel("giây")
    axes[0].set_ylabel("|gia tốc|")
    fig.suptitle("Ba tư thế tĩnh, mỗi hình một thang đo riêng — vẫn không phân biệt được",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    p = f"{OUT_DIR}/waveform_static_zoom.png"
    fig.savefig(p); plt.close(fig)
    return p


def fig_waveform_to_features(df):
    sl = slice_of(df, "walking", seconds=6)
    w = sl["mag"].values[:WINDOW_SIZE]
    t = sl["s"].values[:WINDOW_SIZE]
    f = features(w)

    fig, ax = plt.subplots(figsize=(10.5, 4.9))
    ax.plot(t, w, color=C_DYNAMIC, lw=1.5, zorder=3, label="|gia tốc| trong 1 cửa sổ")

    ax.axhline(f["mean_mag"], color="#1F3B63", ls="-", lw=1.6, zorder=2)
    ax.fill_between(t, f["mean_mag"] - f["std_mag"], f["mean_mag"] + f["std_mag"],
                    color="#1F3B63", alpha=0.13, zorder=1)

    i_pk = int(np.argmax(w))
    ax.plot(t[i_pk], f["peak_max"], "v", color="#B3261E", ms=11, zorder=4)

    span = w.max() - w.min()
    ax.annotate(f"① mean_mag = {f['mean_mag']:.0f}\n   (độ lớn trung bình)",
                xy=(t[3], f["mean_mag"]), xytext=(t[2], f["mean_mag"] - span * 0.42),
                fontsize=9.5, color="#1F3B63",
                arrowprops=dict(arrowstyle="->", color="#1F3B63", lw=1.2))
    ax.annotate(f"② std_mag = {f['std_mag']:.0f}\n   (bề dày dải — mức dao động)",
                xy=(t[len(t) // 2], f["mean_mag"] + f["std_mag"]),
                xytext=(t[len(t) // 2] - 0.5, f["mean_mag"] + span * 0.45),
                fontsize=9.5, color="#1F3B63",
                arrowprops=dict(arrowstyle="->", color="#1F3B63", lw=1.2))
    ax.annotate(f"③ peak_max = {f['peak_max']:.0f}\n   (đỉnh cao nhất)",
                xy=(t[i_pk], f["peak_max"]),
                xytext=(t[i_pk] + 0.25, f["peak_max"] - span * 0.1),
                fontsize=9.5, color="#B3261E",
                arrowprops=dict(arrowstyle="->", color="#B3261E", lw=1.2))
    ax.text(0.995, 0.04,
            f"④ peak_rel = peak_max / mean_mag = {f['peak_max']:.0f} / "
            f"{f['mean_mag']:.0f} = {f['peak_rel']:.2f}\n"
            f"   (đỉnh vượt trung bình bao nhiêu lần — độ 'gai góc')",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9.5,
            color="#5B2333",
            bbox=dict(boxstyle="round,pad=0.45", fc="#FBF3F5", ec="#D8B7C2"))

    ax.set_xlabel(f"giây  (1 cửa sổ = {WINDOW_SIZE} mẫu @ {IMU_HZ} Hz = "
                  f"{WINDOW_SIZE/IMU_HZ:.1f} s, trượt mỗi {STRIDE_SIZE/IMU_HZ:.1f} s)")
    ax.set_ylabel("|gia tốc|")
    ax.set_title("Từ một cửa sổ dạng sóng đến 4 con số đưa vào model  (walking)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    p = f"{OUT_DIR}/waveform_to_features.png"
    fig.savefig(p); plt.close(fig)
    return p


def fig_features_by_activity():
    """Windowed features over every participant with raw capture, not just the demo one."""
    rows = []
    for pid in PARTICIPANTS:
        df = load_magnitude(pid)
        for a in ACTS:
            seg = df[(df["label"] == a) & (df["is_transition"] == 0)]["mag"].values
            for st in range(0, len(seg) - WINDOW_SIZE + 1, STRIDE_SIZE):
                rows.append({"participant_id": pid, "label": a,
                             **features(seg[st:st + WINDOW_SIZE])})
    feat = pd.DataFrame(rows)

    names = [("mean_mag", "① mean_mag"), ("std_mag", "② std_mag"),
             ("peak_max", "③ peak_max"), ("peak_rel", "④ peak_rel")]
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.9))
    for ax, (col, title) in zip(axes, names):
        data = [feat.loc[feat["label"] == a, col].values for a in ACTS]
        bp = ax.boxplot(data, tick_labels=ACTS, patch_artist=True, showfliers=False,
                        widths=0.6, medianprops=dict(color="black", lw=1.4))
        for patch, a in zip(bp["boxes"], ACTS):
            patch.set_facecolor(COLOR[a]); patch.set_alpha(0.78)
        if col != "peak_rel":
            ax.set_yscale("log")
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=45)
    fig.suptitle(f"Giá trị 4 đặc trưng theo hoạt động "
                 f"({len(PARTICIPANTS)} participant có raw capture, {len(feat)} cửa sổ)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    p = f"{OUT_DIR}/features_by_activity.png"
    fig.savefig(p); plt.close(fig)

    print("\nTrung vị đặc trưng theo hoạt động (gộp mọi participant):")
    print(feat.groupby("label")[[c for c, _ in names]].median()
          .reindex(ACTS).to_string(float_format=lambda v: f"{v:10.2f}"))
    return p


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_magnitude(DEMO_PID)
    paths = [fig_waveform_all(df), fig_static_zoom(df), fig_waveform_to_features(df),
             fig_features_by_activity()]
    print("\nĐã lưu:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()

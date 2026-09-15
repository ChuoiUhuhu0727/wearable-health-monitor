"""
Adaptive-filter comparison, re-run against the corrected heart-rate estimator.

WHAT CHANGED FROM lms_denoise_mvp.py
    Nothing about the filters. Same NLMS, same RLS, same Wiener, same 8-tap lagged
    accelerometer-magnitude reference, same participants, same windows.

    The only change is how a heart rate is read out of a waveform. The original used
    spectral_bpm() -- dominant FFT peak plus a hard cross-window continuity limit --
    which check_ground_truth_sanity.py showed can settle on exactly half the true rate
    and then refuse to correct itself. This version uses estimate_bpm_window() from
    hr_estimator_v2.py: median beat interval in the time domain, with the window
    discarded entirely when the beats are too irregular to trust.

WHY THIS MATTERS
    Every MAE in the original comparison was an error against a ruler that was itself
    wrong on 3 of 5 participants. Those numbers could not answer the research question
    either way. This re-run is the first time the three filters are actually measured.

READING THE OUTPUT
    Coverage is now part of the result, not a footnote. The v2 estimator returns nothing
    when a window holds no regular pulse, so "how often could a heart rate be read at
    all" is itself an answer about signal quality. A filter that scores a good MAE on 5%
    of windows has not solved the problem.

USAGE
    python scripts/analysis/lms_denoise_v2.py
"""
import numpy as np
import pandas as pd

from hr_estimator_v2 import estimate_bpm_window, label_at, ACTS
from lms_denoise_mvp import (BASE, FS, HR_BAND, NLMS_TAPS, PARTICIPANTS, WINDOW_S,
                             WINDOW_STRIDE_S, bandpass, build_common_grid, build_lagged,
                             load_raw, nlms_filter, resample, rls_filter, wiener_filter)

CHANNELS = ["base", "lms", "rls", "wiener"]
NAMES = {"base": "Baseline (không lọc)", "lms": "NLMS", "rls": "RLS", "wiener": "Wiener"}


def bpm_series_v2(sig):
    n_win, n_str = int(WINDOW_S * FS), int(WINDOW_STRIDE_S * FS)
    t, bpm = [], []
    for start in range(0, len(sig) - n_win + 1, n_str):
        v, _ = estimate_bpm_window(sig[start:start + n_win], FS)
        t.append((start + n_win / 2) / FS * 1000.0)
        bpm.append(v)
    return np.array(t), np.array(bpm)


def run_participant(pid, files):
    t_wrist, ir_wrist = load_raw(f"{BASE}/{files['wrist']}", "ir")
    t_finger, ir_finger = load_raw(f"{BASE}/{files['fingertip']}", "ir")
    accel = pd.read_csv(f"{BASE}/{files['accel']}")
    t_accel = accel["elapsed_ms"].values.astype(float)

    grid = build_common_grid(t_wrist, t_finger, t_accel)
    wrist_bp = bandpass(resample(t_wrist, ir_wrist, grid), FS, HR_BAND)
    finger_bp = bandpass(resample(t_finger, ir_finger, grid), FS, HR_BAND)

    mag = np.sqrt(accel["ax"] ** 2 + accel["ay"] ** 2 + accel["az"] ** 2).values
    ref = bandpass(resample(t_accel, mag, grid), FS, HR_BAND)
    XL = build_lagged(ref, NLMS_TAPS)

    residuals = {
        "base": wrist_bp,
        "lms": nlms_filter(wrist_bp, XL),
        "rls": rls_filter(wrist_bp, XL),
        "wiener": wiener_filter(wrist_bp, XL),
    }

    t_rel, gt = bpm_series_v2(finger_bp)
    df = pd.DataFrame({"participant_id": pid, "t_ms": grid[0] + t_rel, "gt_bpm": gt})
    for ch, sig in residuals.items():
        _, est = bpm_series_v2(sig)
        df[f"{ch}_bpm"] = est
        df[f"{ch}_err"] = np.abs(est - gt)

    sess = pd.read_csv(f"{BASE}/{files['session']}")
    df["label"], is_trans = label_at(sess, df["t_ms"].values)
    return df[is_trans == 0]


def main():
    print("Chạy lại 5 participant với estimator v2...")
    df = pd.concat([run_participant(p, f) for p, f in PARTICIPANTS.items()],
                   ignore_index=True)

    n = len(df)
    gt_ok = df["gt_bpm"].notna()
    print("\n" + "=" * 72)
    print("SO SÁNH BỘ LỌC — ĐO BẰNG THƯỚC ĐÃ SỬA")
    print("=" * 72)
    print(f"\nCửa sổ (đã bỏ transition): {n}")
    print(f"Ground truth đọc được    : {gt_ok.sum()} ({100*gt_ok.mean():.1f}%)")

    print("\n=== Tỉ lệ đọc được nhịp tim từ mỗi tín hiệu ===")
    print(f"{'Tín hiệu':<24}{'đọc được':>10}{'tỉ lệ':>9}")
    print("-" * 45)
    print(f"{'Đầu ngón tay (chuẩn)':<24}{gt_ok.sum():>10}{100*gt_ok.mean():>8.1f}%")
    for ch in CHANNELS:
        ok = df[f"{ch}_bpm"].notna()
        print(f"{NAMES[ch]:<24}{ok.sum():>10}{100*ok.mean():>8.1f}%")

    print("\n=== MAE, chỉ trên cửa sổ mà CẢ HAI bên đọc được ===")
    print(f"{'Bộ lọc':<24}{'n':>7}{'phủ':>8}{'MAE (bpm)':>12}")
    print("-" * 51)
    rows = []
    for ch in CHANNELS:
        m = gt_ok & df[f"{ch}_bpm"].notna()
        mae = df.loc[m, f"{ch}_err"].mean() if m.any() else np.nan
        rows.append((ch, m.sum(), 100 * m.mean(), mae))
        print(f"{NAMES[ch]:<24}{m.sum():>7}{100*m.mean():>7.1f}%{mae:>12.2f}")

    valid = [r for r in rows if r[1] > 0 and not np.isnan(r[3])]
    if valid:
        best = min(valid, key=lambda r: r[3])
        print(f"\nThấp nhất: {NAMES[best[0]]} ({best[3]:.2f} bpm trên {best[1]} cửa sổ)")

    print("\n=== Theo từng participant (MAE bpm / số cửa sổ so được) ===")
    out = []
    for pid, g in df.groupby("participant_id"):
        row = {"participant_id": pid}
        for ch in CHANNELS:
            m = g["gt_bpm"].notna() & g[f"{ch}_bpm"].notna()
            row[NAMES[ch]] = f"{g.loc[m, f'{ch}_err'].mean():.1f}/{m.sum()}" if m.any() else "—/0"
        out.append(row)
    print(pd.DataFrame(out).set_index("participant_id").to_string())

    print("\n=== Theo từng hoạt động ===")
    out = []
    for act in ACTS:
        g = df[df["label"] == act]
        row = {"hoạt động": act}
        for ch in CHANNELS:
            m = g["gt_bpm"].notna() & g[f"{ch}_bpm"].notna()
            row[NAMES[ch]] = f"{g.loc[m, f'{ch}_err'].mean():.1f}/{m.sum()}" if m.any() else "—/0"
        out.append(row)
    print(pd.DataFrame(out).set_index("hoạt động").to_string())

    df.to_csv("data/processed/filter_comparison_v2.csv", index=False)
    print("\nĐã lưu: data/processed/filter_comparison_v2.csv")


if __name__ == "__main__":
    main()

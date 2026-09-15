"""
Replacement heart-rate estimator for the fingertip reference channel.

WHY A REPLACEMENT IS NEEDED
    check_ground_truth_sanity.py showed the existing estimator (spectral_bpm() in
    lms_denoise_mvp.py) is not trustworthy. On P17 during running it reported 77 bpm
    while the raw waveform plainly shows beats 0.386 s apart -- 156 bpm, almost exactly
    double. Because every filter in the comparison is scored against this reference,
    the reference has to be fixed before any of those scores mean anything.

THE FAILURE IT FIXES
    P17's beats alternate in amplitude (strong, weak, strong, weak -- ratio 2.2x) while
    staying evenly spaced (odd/even interval ratio 1.03). A waveform like that repeats
    itself every TWO beats, so its spectrum carries a strong component at half the true
    rate. An estimator that takes the dominant spectral peak can settle on that half-rate
    component. This is the same "octave error" that pitch trackers hit on musical signals.

    The old estimator then made it permanent: a hard continuity limit (MAX_JUMP_BPM = 25)
    rejected any later window that tried to correct upward, so one early mistake held for
    the rest of the session.

APPROACH
    Work in the time domain, where the alternation is harmless.

    1. Detect beats and take the MEDIAN interval between them. Median, not mean, so a
       few missed or doubled detections cannot drag the estimate.
    2. Judge the window's own reliability from the spread of those intervals
       (coefficient of variation). A real pulse is regular; motion noise is not.
    3. Return NaN when the spread is too large, instead of emitting a confident wrong
       number. The old estimator always produced a value, which is exactly how bad
       estimates spread through the comparison unnoticed.
    4. Apply no cross-window continuity constraint at all. Rejecting implausible jumps
       belongs to a tracking layer; it must never be able to override the measurement,
       which is the mistake that hid this bug.

USAGE
    python scripts/analysis/hr_estimator_v2.py        # validate against the physiological sanity check
"""
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from lms_denoise_mvp import (BASE, FS, HR_BAND, PARTICIPANTS, bandpass, build_common_grid,
                             load_raw, resample)

MIN_BPM, MAX_BPM = 40.0, 200.0
MAX_INTERVAL_CV = 0.25   # above this the beats are too irregular to trust the window
MIN_BEATS = 4            # fewer than this in a window is not enough to take a median of
ACTS = ["lying", "sitting", "standing", "walking", "running"]


def estimate_bpm_window(sig, fs=FS):
    """Heart rate for one window, or (nan, reason) when the window is not trustworthy."""
    min_gap = int((60.0 / MAX_BPM) * fs)
    peaks, _ = find_peaks(sig, distance=min_gap, prominence=np.std(sig) * 0.5)
    if len(peaks) < MIN_BEATS:
        return np.nan, np.nan

    iv = np.diff(peaks) / fs
    cv = iv.std() / iv.mean()
    bpm = 60.0 / np.median(iv)

    if cv > MAX_INTERVAL_CV or not (MIN_BPM <= bpm <= MAX_BPM):
        return np.nan, cv
    return bpm, cv


def estimate_bpm_series(sig, fs, window_s, stride_s):
    """Slide estimate_bpm_window over the signal. No continuity constraint by design."""
    n_win, n_str = int(window_s * fs), int(stride_s * fs)
    out_t, out_bpm, out_cv = [], [], []
    for start in range(0, len(sig) - n_win + 1, n_str):
        bpm, cv = estimate_bpm_window(sig[start:start + n_win], fs)
        out_t.append((start + n_win / 2) / fs * 1000.0)
        out_bpm.append(bpm)
        out_cv.append(cv)
    return np.array(out_t), np.array(out_bpm), np.array(out_cv)


def label_at(session_df, t_ms_array):
    lab = session_df.sort_values("elapsed_ms")
    idx = np.searchsorted(lab["elapsed_ms"].values, t_ms_array, side="right") - 1
    idx = np.clip(idx, 0, len(lab) - 1)
    return lab["label"].values[idx], lab["is_transition"].values[idx]


def fingertip_bpm_v2(pid, files, window_s=8.0, stride_s=2.0):
    t_f, v_f = load_raw(f"{BASE}/{files['fingertip']}", "ir")
    grid = build_common_grid(t_f)
    sig = bandpass(resample(t_f, v_f, grid), FS, HR_BAND)

    rel_t, bpm, cv = estimate_bpm_series(sig, FS, window_s, stride_s)
    abs_t = grid[0] + rel_t

    sess = pd.read_csv(f"{BASE}/{files['session']}")
    labels, is_trans = label_at(sess, abs_t)
    return pd.DataFrame({"participant_id": pid, "t_ms": abs_t, "label": labels,
                         "is_transition": is_trans, "bpm_v2": bpm, "interval_cv": cv})


def main():
    frames = [fingertip_bpm_v2(pid, files) for pid, files in PARTICIPANTS.items()]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["is_transition"] == 0]

    n_total = len(df)
    n_ok = df["bpm_v2"].notna().sum()
    print("=" * 70)
    print("GROUND-TRUTH ESTIMATOR v2 — kiểm tra lại bằng physiological sanity check")
    print("=" * 70)
    print(f"\nCửa sổ: {n_total} | ước lượng được: {n_ok} ({100*n_ok/n_total:.1f}%)")
    print(f"Bị loại vì nhịp quá không đều (CV > {MAX_INTERVAL_CV}): {n_total - n_ok}")

    piv = df.pivot_table(index="participant_id", columns="label",
                         values="bpm_v2", aggfunc="median").reindex(columns=ACTS)
    piv["chạy − nằm"] = piv["running"] - piv["lying"]
    print("\n=== v2: nhịp tim tham chiếu theo hoạt động (trung vị, bpm) ===")
    print(piv.to_string(float_format=lambda v: f"{v:.1f}"))

    ok = [p for p in piv.index
          if piv.loc[p, "chạy − nằm"] > 20 and piv.loc[p, ACTS].idxmax() == "running"]
    print(f"\nv2 vượt qua sanity check: {ok}")
    print(f"v2 KHÔNG vượt qua        : {[p for p in piv.index if p not in ok]}")
    print("\n(v1 chỉ có P03 và P16 vượt qua — xem check_ground_truth_sanity.py)")

    print("\n=== Tỉ lệ cửa sổ dùng được, theo hoạt động ===")
    cov = df.groupby("label")["bpm_v2"].agg(n="size", ok=lambda s: s.notna().sum())
    cov["tỉ lệ"] = (100 * cov["ok"] / cov["n"]).round(1)
    print(cov.reindex(ACTS).to_string())

    df.to_csv("data/processed/fingertip_bpm_v2.csv", index=False)
    print("\nĐã lưu: data/processed/fingertip_bpm_v2.csv")


if __name__ == "__main__":
    main()

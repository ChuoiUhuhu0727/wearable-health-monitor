"""
LMS/RLS/Wiener research track -- full comparison, all 5 dual-PPG participants.

Research question (README.md, Research Track section): does an accel-referenced
adaptive filter reduce wrist-PPG BPM error (vs fingertip ground truth), and if so
which of LMS/RLS/Wiener does it best? See paper/adaptive_filter_comparison_2026-07-28.md
for the full write-up; short version: no, not consistently, at N=5 (baseline and
NLMS pooled MAE ~27bpm, RLS/Wiener ~30bpm, no filter wins for every participant).

Pipeline (run_pipeline(), once per participant x reference_mode):
  1. Load raw wrist PPG, raw fingertip PPG, raw accel (keyed by elapsed_ms, uneven
     native sample rates), resample onto one common 100Hz grid.
  2. Bandpass both PPG channels to the plausible heart-rate band (0.7-3.5Hz / 42-210bpm).
  3. Ground truth: spectral (FFT) BPM of the fingertip channel, per sliding window
     (spectral_bpm() -- see its docstring for why this isn't simple peak-counting).
  4. Baseline: spectral BPM of the RAW wrist channel (no filtering), same windows.
  5. Build a lagged reference design matrix (build_lagged()) from bandpassed accel --
     either 1-channel magnitude (reference_mode="magnitude", the default/best-performing)
     or 3-channel per-axis (reference_mode="triaxial", tested and found WORSE -- see
     the paper write-up). Run all 3 filters (nlms_filter/rls_filter/wiener_filter)
     against the wrist PPG using that reference, spectral-BPM each residual.
  6. Attach the activity label at each window's center (from session_1_*.csv, the
     ground-truth protocol label -- not model output, so this does NOT touch the
     bug-1/activity-classifier rabbit hole), report MAE vs fingertip per participant
     and per activity.

Method notes (see CHANGELOG.md 2026-07-28 for the full trace of how each of these
was found and fixed):
  - Ground-truth BPM extraction went through 3 iterations before this version was
    trustworthy: naive peak-counting produced physiologically implausible BPM swings
    -> replaced with per-window FFT dominant-frequency -> found to sometimes lock onto
    the PPG signal's own 2nd harmonic -> added continuity tracking across windows
    (MAX_JUMP_BPM) with a median-seeded burn-in (BURN_IN_WINDOWS) to fix that.
  - RLS diverged numerically on first implementation (residual std exploded ~7e3->2e7
    over one session) from unbounded covariance growth during low-motion stretches --
    fixed with a covariance-reset safeguard (RLS_TRACE_RESET).

Usage:
    python scripts/analysis/lms_denoise_mvp.py
"""
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks

BASE = "experiments/wrist/valid_sessions"

# The 5 participants with complete dual-PPG (fingertip channel non-empty) --
# P01's fingertip is empty, excluded (see project memory / README Progress Log).
PARTICIPANTS = {
    "P02": dict(session="session_1_20260718_203817.csv", wrist="raw_ppg_1_20260718_203821.csv",
                fingertip="raw_ppg2_1_20260718_203906.csv", accel="raw_accel_1_20260718_203851.csv"),
    "P03": dict(session="session_1_20260718_210037.csv", wrist="raw_ppg_1_20260718_210038.csv",
                fingertip="raw_ppg2_1_20260718_210100.csv", accel="raw_accel_1_20260718_210052.csv"),
    "P04": dict(session="session_1_20260720_184050.csv", wrist="raw_ppg_1_20260720_184052.csv",
                fingertip="raw_ppg2_1_20260720_184113.csv", accel="raw_accel_1_20260720_184106.csv"),
    "P16": dict(session="session_1_20260728_183801.csv", wrist="raw_ppg_1_20260728_183805.csv",
                fingertip="raw_ppg2_1_20260728_183850.csv", accel="raw_accel_1_20260728_183835.csv"),
    "P17": dict(session="session_1_20260728_185304.csv", wrist="raw_ppg_1_20260728_185308.csv",
                fingertip="raw_ppg2_1_20260728_185353.csv", accel="raw_accel_1_20260728_185338.csv"),
}

FS = 100.0  # target common grid rate (Hz) -- native rates are close to this but uneven
HR_BAND = (0.7, 3.5)  # Hz == 42-210 bpm, generous headroom around plausible human HR
WINDOW_S = 8.0  # longer than the old 5s: FFT frequency resolution = FS/N, needs enough samples
WINDOW_STRIDE_S = 2.0
NLMS_TAPS = 8  # small tap count: accel->PPG-artifact coupling is a short-lag effect
NLMS_MU = 0.5


def load_raw(path, value_col):
    df = pd.read_csv(path)
    return df["elapsed_ms"].values.astype(float), df[value_col].values.astype(float)


def build_common_grid(*t_arrays):
    lo = max(t[0] for t in t_arrays)
    hi = min(t[-1] for t in t_arrays)
    n = int((hi - lo) / 1000.0 * FS)
    return lo + np.arange(n) * (1000.0 / FS)


def resample(t_src, v_src, t_grid):
    return np.interp(t_grid, t_src, v_src)


def bandpass(signal, fs, band):
    b, a = butter(3, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
    return filtfilt(b, a, signal)


MAX_JUMP_BPM = 25.0  # max plausible BPM change between consecutive windows (2s stride)
BURN_IN_WINDOWS = 5  # windows used to seed the initial track (see docstring)


def spectral_bpm(signal, fs, band, window_s, stride_s):
    """Per-window dominant-frequency BPM with continuity tracking across windows.

    Naive version (global argmax in-band, independent per window) was tried first
    and found to jump onto the PPG signal's own 2nd harmonic in some windows (e.g.
    75bpm truth -> 151bpm reading) -- PPG pulse waveforms are non-sinusoidal, so
    the 2nd harmonic can outweigh the fundamental in a single 8s window's spectrum.
    Fix v1: at each window, look at ALL local spectral peaks in-band (not just the
    global max); among those within MAX_JUMP_BPM of the previous window's estimate,
    pick the strongest -- heart rate can't jump 25+ bpm in a 2s stride, so this
    naturally locks onto the fundamental once acquired instead of hopping to a
    harmonic. Then parabolic-interpolate the 3 bins around the chosen peak for
    sub-bin resolution.

    Fix v2 (this version): v1 seeded the track from window 1's raw global max --
    on the noisy raw wrist baseline this let 1 bad window lock the whole session
    onto a wrong frequency, because in a noisy spectrum there's almost always SOME
    local peak within MAX_JUMP_BPM of whatever the (wrong) previous value was, so
    "track lost -> reacquire" rarely actually triggered. Instead, seed prev_freq
    from the MEDIAN of BURN_IN_WINDOWS independent (untracked) window estimates --
    median tolerates 1-2 of those being wrong, unlike trusting window 1 alone.

    Returns (window_center_ms, bpm)."""
    n = int(window_s * fs)
    hop = int(stride_s * fs)
    window_fn = np.hanning(n)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    bin_width = freqs[1] - freqs[0]
    band_mask = (freqs >= band[0]) & (freqs <= band[1])
    band_idx = np.where(band_mask)[0]
    max_jump_hz = MAX_JUMP_BPM / 60.0

    starts = list(range(0, len(signal) - n + 1, hop))
    windows = []  # (candidates_idx, mag) per window, computed once and reused
    for start in starts:
        seg = signal[start:start + n] * window_fn
        mag = np.abs(np.fft.rfft(seg))
        band_mag = mag[band_idx]
        local_rel, _ = find_peaks(band_mag)
        candidates = band_idx[local_rel] if len(local_rel) else np.array([band_idx[np.argmax(band_mag)]])
        windows.append((candidates, mag))

    burn_freqs = [freqs[c[np.argmax(m[c])]] for c, m in windows[:BURN_IN_WINDOWS]]
    prev_freq = float(np.median(burn_freqs)) if burn_freqs else None

    centers_ms, bpms = [], []
    for start, (candidates, mag) in zip(starts, windows):
        if prev_freq is not None:
            within = np.abs(freqs[candidates] - prev_freq) <= max_jump_hz
            if within.any():
                candidates = candidates[within]
        k = candidates[np.argmax(mag[candidates])]

        if 0 < k < len(mag) - 1:
            a, b, c = mag[k - 1], mag[k], mag[k + 1]
            denom = (a - 2 * b + c)
            delta = 0.5 * (a - c) / denom if denom != 0 else 0.0
        else:
            delta = 0.0
        peak_freq = freqs[k] + delta * bin_width
        prev_freq = peak_freq

        centers_ms.append((start + n / 2) / fs * 1000.0)
        bpms.append(peak_freq * 60.0)
    return np.array(centers_ms), np.array(bpms)


def build_lagged(X, n_taps):
    """X: (n,) single channel or (n, n_channels) multi-channel reference. Returns
    (n, n_taps*n_channels) design matrix -- row i is the causal window [x[i], x[i-1],
    ..., x[i-n_taps+1]] per channel, concatenated across channels. Used to give all 3
    filters (nlms/rls/wiener) an identical regressor shape regardless of whether the
    reference is 1D (accel magnitude) or multi-channel (e.g. ax/ay/az separately) --
    a 3-channel reference lets the filter learn a different coupling per axis instead
    of collapsing direction info into a scalar magnitude before the filter ever sees it."""
    if X.ndim == 1:
        X = X[:, None]
    n, n_channels = X.shape
    cols = []
    for c in range(n_channels):
        x = X[:, c]
        x_padded = np.concatenate([np.zeros(n_taps - 1), x])
        for tap in range(n_taps):
            cols.append(x_padded[n_taps - 1 - tap: n_taps - 1 - tap + n])
    return np.column_stack(cols)


def nlms_filter(d, XL, mu=NLMS_MU, eps=1e-3):
    """Normalized LMS adaptive noise canceller: XL (lagged reference, see
    build_lagged) estimates the component of d (wrist PPG) that's linearly,
    causally predictable from recent reference samples; e = d - that estimate
    is the denoised residual. Normalized by regressor energy (not plain LMS) so
    mu doesn't need retuning per-participant when reference amplitude varies."""
    n, m = XL.shape
    w = np.zeros(m)
    e = np.zeros(n)
    for i in range(n):
        xrow = XL[i]
        y = np.dot(w, xrow)
        e[i] = d[i] - y
        norm = np.dot(xrow, xrow) + eps
        w += (mu / norm) * e[i] * xrow
    return e


RLS_LAMBDA = 0.99  # forgetting factor -- standard default, close to 1 (long memory)
RLS_DELTA = 0.01  # initial inverse-correlation scaling -- larger = more regularized start


RLS_TRACE_RESET = 1e4  # covariance reset threshold -- see docstring for why this is needed


def rls_filter(d, XL, lam=RLS_LAMBDA, delta=RLS_DELTA):
    """Recursive Least Squares noise canceller -- same transversal-filter/adaptive-
    noise-cancellation setup as nlms_filter (XL=lagged reference predicts the
    reference-correlated component of d=wrist PPG, e=d-prediction is the denoised
    residual), but updates weights via the matrix inversion lemma (tracks the exact
    least-squares solution each step) instead of gradient descent. Converges faster
    and adapts quicker to changing correlation than NLMS, at O(m^2) cost per sample
    instead of O(m) where m = XL.shape[1] -- fine at m up to a few dozen.

    Covariance reset (2026-07-28): first version blew up numerically (residual std
    went from ~7e3 to ~2e7 over a single 450s recording) during the long low-motion
    stretches we already measured in check_accel_variance_by_activity.py (lying/
    sitting/standing) -- with lam=0.99 and little new excitation to shrink it, P
    grows by ~1/lam each step (~148x over a 5s static stretch), a well-known RLS
    "windup" failure mode for intermittently-exciting inputs. Standard fix: reset
    P to its initial (regularized) value whenever its trace exceeds RLS_TRACE_RESET,
    instead of letting it grow unbounded."""
    n, m = XL.shape
    w = np.zeros(m)
    P0 = np.eye(m) / delta
    P = P0.copy()
    e = np.zeros(n)
    for i in range(n):
        xrow = XL[i]
        Px = P @ xrow
        gain = Px / (lam + xrow @ Px)
        y = np.dot(w, xrow)
        e[i] = d[i] - y
        w += gain * e[i]
        P = (P - np.outer(gain, Px)) / lam
        P = (P + P.T) / 2.0  # re-symmetrize -- guards against asymmetric float drift
        if np.trace(P) > RLS_TRACE_RESET:
            P = P0.copy()
    return e


WIENER_REG = 1e-6  # small ridge regularization -- same low-excitation-stretch risk as RLS windup,
                    # here it shows up as a near-singular autocorrelation matrix instead


def wiener_filter(d, XL, reg=WIENER_REG):
    """Wiener noise canceller -- NOT adaptive/online like nlms_filter/rls_filter. Instead
    computes the single optimal FIR filter (Wiener-Hopf solution) using the WHOLE
    recording's statistics at once, then applies that one fixed filter everywhere. This
    is the classic "best possible linear time-invariant filter given full knowledge of
    the signal statistics" -- a ceiling LMS/RLS can't exceed in principle since they only
    see causal, online data, but it also can't adapt if the true reference->artifact
    coupling changes partway through a session (e.g. sitting -> walking).

    Solves the normal equations R w = p for w, where R = XL^T XL (autocorrelation) and
    p = XL^T d (cross-correlation). reg regularizes R -- same underlying risk as the RLS
    windup bug (low-excitation stretches make R poorly conditioned), just showing up as
    a near-singular solve here instead of an unbounded recursive update."""
    n, m = XL.shape
    R = XL.T @ XL / n
    p = XL.T @ d / n
    w = np.linalg.solve(R + reg * np.eye(m), p)
    return d - XL @ w


def label_at(session_df, t_ms_array):
    lut = session_df[["elapsed_ms", "label"]].sort_values("elapsed_ms")
    lut["elapsed_ms"] = lut["elapsed_ms"].astype(float)
    q = pd.DataFrame({"elapsed_ms": t_ms_array}).sort_values("elapsed_ms")
    merged = pd.merge_asof(q, lut, on="elapsed_ms", direction="backward")
    return merged["label"].values


def run_pipeline(participant_id, files, reference_mode="magnitude"):
    """Run the full pipeline for one participant, return a windowed DataFrame with
    columns: participant_id, reference_mode, t_ms, label, gt_bpm, base_bpm, lms_bpm,
    rls_bpm, wiener_bpm, base_err, lms_err, rls_err, wiener_err.

    reference_mode: "magnitude" (default, best-performing) collapses ax/ay/az into a
    single scalar before the filter ever sees it -- discarding which direction the
    motion was in. "triaxial" instead gives the filter 3 separate lagged channels
    (ax, ay, az), so it can learn a different coupling coefficient per axis instead
    of one shared scalar coupling -- tested and found WORSE (more parameters overfit
    the ~45k noisy samples available per session), kept here for reproducibility of
    that negative result, not because it's recommended. Only changes the reference
    construction; ground truth/baseline/spectral BPM/labels are identical either way."""
    t_wrist, ir_wrist = load_raw(f"{BASE}/{files['wrist']}", "ir")
    t_finger, ir_finger = load_raw(f"{BASE}/{files['fingertip']}", "ir")
    accel_df = pd.read_csv(f"{BASE}/{files['accel']}")
    t_accel = accel_df["elapsed_ms"].values.astype(float)

    t_grid = build_common_grid(t_wrist, t_finger, t_accel)

    wrist_g = resample(t_wrist, ir_wrist, t_grid)
    finger_g = resample(t_finger, ir_finger, t_grid)

    wrist_bp = bandpass(wrist_g, FS, HR_BAND)
    finger_bp = bandpass(finger_g, FS, HR_BAND)

    if reference_mode == "magnitude":
        accel_mag = np.sqrt(accel_df["ax"] ** 2 + accel_df["ay"] ** 2 + accel_df["az"] ** 2).values
        accel_g = resample(t_accel, accel_mag, t_grid)
        ref = bandpass(accel_g, FS, HR_BAND)
    elif reference_mode == "triaxial":
        axes = []
        for col in ("ax", "ay", "az"):
            axis_g = resample(t_accel, accel_df[col].values.astype(float), t_grid)
            axes.append(bandpass(axis_g, FS, HR_BAND))
        ref = np.column_stack(axes)
    else:
        raise ValueError(f"unknown reference_mode: {reference_mode}")

    n_taps = NLMS_TAPS  # shared tap count across all 3 filters and both reference modes
    XL = build_lagged(ref, n_taps)

    lms_residual = nlms_filter(wrist_bp, XL)
    rls_residual = rls_filter(wrist_bp, XL)
    wiener_residual = wiener_filter(wrist_bp, XL)

    t_start = t_grid[0]
    gt_mid, gt_w = spectral_bpm(finger_bp, FS, HR_BAND, WINDOW_S, WINDOW_STRIDE_S)
    base_mid, base_w = spectral_bpm(wrist_bp, FS, HR_BAND, WINDOW_S, WINDOW_STRIDE_S)
    lms_mid, lms_w = spectral_bpm(lms_residual, FS, HR_BAND, WINDOW_S, WINDOW_STRIDE_S)
    rls_mid, rls_w = spectral_bpm(rls_residual, FS, HR_BAND, WINDOW_S, WINDOW_STRIDE_S)
    wiener_mid, wiener_w = spectral_bpm(wiener_residual, FS, HR_BAND, WINDOW_S, WINDOW_STRIDE_S)
    gt_t, base_t, lms_t, rls_t, wiener_t = (gt_mid + t_start, base_mid + t_start, lms_mid + t_start,
                                             rls_mid + t_start, wiener_mid + t_start)

    session_df = pd.read_csv(f"{BASE}/{files['session']}")
    labels = label_at(session_df, gt_t)

    df = pd.DataFrame({"t_ms": gt_t, "label": labels, "gt_bpm": gt_w})
    df = df.merge(pd.DataFrame({"t_ms": base_t, "base_bpm": base_w}), on="t_ms", how="left")
    df = df.merge(pd.DataFrame({"t_ms": lms_t, "lms_bpm": lms_w}), on="t_ms", how="left")
    df = df.merge(pd.DataFrame({"t_ms": rls_t, "rls_bpm": rls_w}), on="t_ms", how="left")
    df = df.merge(pd.DataFrame({"t_ms": wiener_t, "wiener_bpm": wiener_w}), on="t_ms", how="left")
    df["base_err"] = (df["base_bpm"] - df["gt_bpm"]).abs()
    df["lms_err"] = (df["lms_bpm"] - df["gt_bpm"]).abs()
    df["rls_err"] = (df["rls_bpm"] - df["gt_bpm"]).abs()
    df["wiener_err"] = (df["wiener_bpm"] - df["gt_bpm"]).abs()
    df.insert(0, "reference_mode", reference_mode)
    df.insert(0, "participant_id", participant_id)
    print(f"  {participant_id} ({reference_mode}): {len(t_grid)} samples "
          f"({(t_grid[-1]-t_grid[0])/1000:.1f}s), {len(df)} windows")
    return df


def main():
    print(f"Running pipeline for {len(PARTICIPANTS)} participants, both reference modes...")
    all_df = pd.concat(
        [run_pipeline(pid, files, mode) for mode in ("magnitude", "triaxial") for pid, files in PARTICIPANTS.items()],
        ignore_index=True,
    )

    for mode, mode_df in all_df.groupby("reference_mode"):
        print(f"\n########## reference_mode = {mode} ##########")

        print("\n=== Per-participant overall MAE (bpm) ===")
        per_p = mode_df.groupby("participant_id").agg(
            n=("gt_bpm", "size"),
            baseline_mae=("base_err", "mean"),
            lms_mae=("lms_err", "mean"),
            rls_mae=("rls_err", "mean"),
            wiener_mae=("wiener_err", "mean"),
        )
        per_p["best"] = per_p[["baseline_mae", "lms_mae", "rls_mae", "wiener_mae"]].idxmin(axis=1)
        print(per_p.to_string(float_format=lambda x: f"{x:.2f}"))

        overall = mode_df[["base_err", "lms_err", "rls_err", "wiener_err"]].mean()
        print(f"\nPooled overall baseline MAE: {overall['base_err']:.2f} bpm")
        print(f"Pooled overall LMS MAE:      {overall['lms_err']:.2f} bpm")
        print(f"Pooled overall RLS MAE:      {overall['rls_err']:.2f} bpm")
        print(f"Pooled overall Wiener MAE:   {overall['wiener_err']:.2f} bpm")


if __name__ == "__main__":
    main()

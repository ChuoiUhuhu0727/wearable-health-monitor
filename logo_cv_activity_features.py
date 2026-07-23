"""
LOGO-CV check: does adding mean_ax/mean_ay/mean_az fix the lying/sitting/standing
overlap in mean_mag/std_mag (bug 1)?

Only usable on the 4 sessions that have raw_accel_N.csv (P01-P04) — the other 11 valid
sessions never had per-axis accel logged on-device, so this feature can't be reconstructed
for them. N=4 participants is very small for LOGO-CV; treat results as a directional signal,
not a confident generalization claim.

mean_ax/ay/az are reconstructed by TIME window (elapsed_ms in (t-2400, t]), not by counting
60 raw rows — raw_imu_queue is best-effort and drops samples under load (~2-3% of intervals
show a gap in these files), so counting rows would silently misalign with the window the
firmware actually used for mean_mag/std_mag (which is sample-count-based and effectively
gap-free on the higher-priority imu_queue path). This is an approximation, not an exact
reconstruction of the firmware's window.
"""
import csv
import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import accuracy_score, confusion_matrix

WINDOW_MS = 2400  # WINDOW_SIZE=60 samples * 40ms (25Hz) — see firmware_ble/main.cpp

SESSIONS = [
    ("valid_sessions/session_1_20260717_183249.csv", "valid_sessions/raw_accel_1_20260717_183314.csv", "P01"),
    ("valid_sessions/session_1_20260718_203817.csv", "valid_sessions/raw_accel_1_20260718_203851.csv", "P02"),
    ("valid_sessions/session_1_20260718_210037.csv", "valid_sessions/raw_accel_1_20260718_210052.csv", "P03"),
    ("valid_sessions/session_1_20260720_184050.csv", "valid_sessions/raw_accel_1_20260720_184106.csv", "P04"),
]

ACTS = ["lying", "sitting", "standing", "walking", "running"]


def build_dataset(base_dir="experiments/wrist"):
    rows = []
    for sess_f, accel_f, pid in SESSIONS:
        with open(f"{base_dir}/{sess_f}", newline="") as fh:
            sess = list(csv.DictReader(fh))
        with open(f"{base_dir}/{accel_f}", newline="") as fh:
            accel = list(csv.DictReader(fh))
        accel_t = np.array([float(r["elapsed_ms"]) for r in accel])
        accel_ax = np.array([float(r["ax"]) for r in accel])
        accel_ay = np.array([float(r["ay"]) for r in accel])
        accel_az = np.array([float(r["az"]) for r in accel])

        for r in sess:
            if r["is_transition"] != "0":
                continue
            t = float(r["elapsed_ms"])
            mask = (accel_t > t - WINDOW_MS) & (accel_t <= t)
            n = mask.sum()
            if n < 40:  # window too sparse (heavy drop) to trust — skip, don't fake it
                continue
            rows.append({
                "participant": pid,
                "label": r["label"],
                "mean_mag": float(r["mean_mag"]),
                "std_mag": float(r["std_mag"]),
                "peak_rel": float(r["peak_rel"]),
                "peak_max": float(r["peak_max"]),
                "mean_ax": accel_ax[mask].mean(),
                "mean_ay": accel_ay[mask].mean(),
                "mean_az": accel_az[mask].mean(),
                "window_n": n,
            })
    return pd.DataFrame(rows)


def run_logocv(df, features, label="model"):
    X = df[features].values
    y = df["label"].values
    groups = df["participant"].values
    logo = LeaveOneGroupOut()

    fold_acc = []
    all_true, all_pred = [], []
    for train_idx, test_idx in logo.split(X, y, groups):
        clf = DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=0)
        clf.fit(X[train_idx], y[train_idx])
        pred = clf.predict(X[test_idx])
        held_out = groups[test_idx][0]
        acc = accuracy_score(y[test_idx], pred)
        fold_acc.append((held_out, acc))
        all_true.extend(y[test_idx])
        all_pred.extend(pred)

    print(f"\n=== {label} (features: {features}) ===")
    for pid, acc in fold_acc:
        print(f"  held-out {pid}: accuracy = {acc:.3f}")
    print(f"  mean across 4 folds: {np.mean([a for _, a in fold_acc]):.3f}")

    cm = confusion_matrix(all_true, all_pred, labels=ACTS)
    print("  pooled confusion matrix (rows=true, cols=pred):")
    print("  " + " ".join(f"{a[:4]:>6s}" for a in ACTS))
    for i, a in enumerate(ACTS):
        print(f"  {a[:4]:>4s} " + " ".join(f"{cm[i][j]:6d}" for j in range(len(ACTS))))
    return fold_acc, cm


if __name__ == "__main__":
    df = build_dataset()
    print(f"Total clean rows: {len(df)}  |  per participant: {df.groupby('participant').size().to_dict()}")
    print(f"Per-label counts: {df.groupby('label').size().to_dict()}")

    baseline_feats = ["mean_mag", "std_mag", "peak_rel", "peak_max"]
    enhanced_feats = baseline_feats + ["mean_ax", "mean_ay", "mean_az"]

    run_logocv(df, baseline_feats, "BASELINE (no orientation feature)")
    run_logocv(df, enhanced_feats, "ENHANCED (+ mean_ax/ay/az, raw device-frame)")

    # Per-participant calibration: subtract each participant's own lying-baseline
    # from their ax/ay/az before pooling — tests whether the P03 mismatch is a
    # wearing-orientation shift that a per-user baseline removes.
    lying_base = df[df.label == "lying"].groupby("participant")[["mean_ax", "mean_ay", "mean_az"]].mean()
    df2 = df.copy()
    for axis in ["mean_ax", "mean_ay", "mean_az"]:
        df2[f"{axis}_rel"] = df2.apply(lambda r: r[axis] - lying_base.loc[r["participant"], axis], axis=1)
    rel_feats = baseline_feats + ["mean_ax_rel", "mean_ay_rel", "mean_az_rel"]
    run_logocv(df2, rel_feats, "ENHANCED-RELATIVE (axis mean minus participant's own lying baseline)")

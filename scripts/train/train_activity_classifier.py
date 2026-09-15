"""
Main evidence script for the activity-classifier report (Sections 1, 3 and 4).

WHAT IT DOES
    Evaluates the same decision-tree model on the same data twice, changing
    exactly one thing: how the activity labels are grouped.
        (1) 5-class : lying / sitting / standing / walking / running  -> 0.548
        (2) 3-class : stationary / walking / running                  -> 0.853
    Then trains the final 5-class model on all participants and exports it for
    deployment to the wearable's firmware.

    Because the model, hyperparameters, features, dataset and evaluation
    procedure are held identical between (1) and (2), the difference between the
    two accuracies is attributable to the label grouping alone. That is the
    controlled comparison the report's "Solution (C)" section rests on.

EVALUATION: LOGO-CV (leave-one-participant-out)
    Each of the 18 participants is held out in turn: the model trains on the
    other 17 and is tested on the held-out person, and the reported accuracy is
    the mean over all 18 folds. This is stricter than a random train/test split,
    which would put windows from the same person in both sets and let the model
    score well by memorising individuals. The numbers here therefore estimate
    performance on a NEW user the model has never seen.

MODEL
    DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=0).
    Depth is capped deliberately: with only 4 features and 18 participants, an
    unconstrained tree overfits individuals, which is precisely what LOGO-CV is
    designed to expose. random_state=0 makes every run reproducible.

FEATURES (all four derived from accelerometer magnitude)
    mean_mag, std_mag, peak_rel, peak_max -- computed on-device over a 2.4 s
    sliding window (60 samples at 25 Hz, stride 0.4 s); see
    firmware/ble/main.cpp:738-750 for the on-device implementation.

INPUT / OUTPUT
    in : data/processed/master_dataset.csv  (built by build_processed_dataset.py)
    out: models/activity_classifier.pkl     (5-class model, all 18 participants)

ROW SELECTION
    Transition rows (is_transition == 1) are excluded -- these are the ~15 s
    while a participant changes posture, where the recorded label does not yet
    describe what the body is doing. Left in, they would inject mislabelled data
    into both training and testing.

USAGE
    python scripts/train/train_activity_classifier.py

READING THE OUTPUT
    Per-class recall matters more than the mean accuracy: the 5-class model is
    not uniformly mediocre, it fails on specific classes. `lying` at 0.284 is
    barely above chance (0.20) while `running` reaches 0.782, and the pooled
    confusion matrix shows the errors concentrated among the three static
    postures. Section 2 of the report explains why -- magnitude is invariant to
    rotation, and those three postures differ only by orientation.
"""
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import accuracy_score, confusion_matrix
import joblib
import os

IN_PATH = "data/processed/master_dataset.csv"
OUT_PATH = "models/activity_classifier.pkl"
FEATURES = ["mean_mag", "std_mag", "peak_rel", "peak_max"]
ACTS_5CLASS = ["lying", "sitting", "standing", "walking", "running"]
ACTS_3CLASS = ["stationary", "walking", "running"]


def make_model():
    return DecisionTreeClassifier(max_depth=5, min_samples_leaf=5, random_state=0)


def run_logocv(X, y, groups, class_labels, title):
    """Shared LOGO-CV runner -- same model/procedure regardless of which column
    (label vs activity_group) is used as the target, so the two accuracy numbers
    are a fair apples-to-apples comparison, not different methodologies."""
    logo = LeaveOneGroupOut()
    fold_acc = []
    all_true, all_pred = [], []
    for train_idx, test_idx in logo.split(X, y, groups):
        clf = make_model()
        clf.fit(X[train_idx], y[train_idx])
        pred = clf.predict(X[test_idx])
        held_out = groups[test_idx][0]
        fold_acc.append((held_out, accuracy_score(y[test_idx], pred)))
        all_true.extend(y[test_idx])
        all_pred.extend(pred)

    print(f"\n=== LOGO-CV: {title} ===")
    for pid, acc in sorted(fold_acc):
        print(f"  held-out {pid}: accuracy = {acc:.3f}")
    mean_acc = np.mean([a for _, a in fold_acc])
    print(f"  mean across {len(fold_acc)} folds: {mean_acc:.3f}")

    cm = confusion_matrix(all_true, all_pred, labels=class_labels)
    print("\n  pooled confusion matrix (rows=true, cols=pred):")
    print("  " + " ".join(f"{a[:4]:>6s}" for a in class_labels))
    for i, a in enumerate(class_labels):
        print(f"  {a[:4]:>4s} " + " ".join(f"{cm[i][j]:6d}" for j in range(len(class_labels))))

    print("\n  per-class recall:")
    for i, a in enumerate(class_labels):
        recall = cm[i][i] / cm[i].sum() if cm[i].sum() > 0 else float("nan")
        print(f"    {a:>10s}: {recall:.3f}")

    return mean_acc


def main():
    df = pd.read_csv(IN_PATH)
    df = df[df["is_transition"] == 0].copy()

    X = df[FEATURES].values
    groups = df["participant_id"].values

    print(f"Clean rows: {len(df)} | participants: {df['participant_id'].nunique()}")
    print(f"Features: {FEATURES}")

    acc_5class = run_logocv(X, df["label"].values, groups, ACTS_5CLASS,
                             "5-class (lying/sitting/standing/walking/running)")
    acc_3class = run_logocv(X, df["activity_group"].values, groups, ACTS_3CLASS,
                             "3-class (stationary/walking/running, same features/model/data)")

    print(f"\n=== Summary: same model+features+data, two scopes ===")
    print(f"  5-class mean accuracy: {acc_5class:.3f}")
    print(f"  3-class mean accuracy: {acc_3class:.3f}")

    # Final export model: 5-class, trained on ALL participants (LOGO-CV above is for
    # honest accuracy reporting only, not the deployed model). 5-class is what's
    # deployed to firmware/ble (see activity_classifier_5class.h) -- the 3-class
    # number above is reported for context/comparison, not a second deployed model.
    y = df["label"].values
    final_model = make_model()
    final_model.fit(X, y)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    joblib.dump({"model": final_model, "features": FEATURES, "classes": list(final_model.classes_)}, OUT_PATH)
    print(f"\nFinal model (trained on all {df['participant_id'].nunique()} participants) saved to {OUT_PATH}")


if __name__ == "__main__":
    main()

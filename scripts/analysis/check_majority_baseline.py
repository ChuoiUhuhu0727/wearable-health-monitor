"""
Trivial-baseline reference for the activity-classifier report, Section 4.

QUESTION THIS ANSWERS
    An accuracy number alone ("0.548", "0.853") means nothing until you know what
    the dumbest possible model would score on the same data. This script computes
    that floor: a "majority-class" model that ignores the sensor entirely and
    always predicts whichever class is most common.

WHY IT MATTERS HERE
    The 5-class and 3-class problems do NOT have the same floor. Grouping
    lying/sitting/standing into one `stationary` class creates a class holding
    3/5 of the data, so always guessing "stationary" is right ~60% of the time
    before any learning happens. Comparing 0.548 to 0.853 directly therefore
    overstates the improvement; the fair comparison is each model's margin over
    its own floor.

INPUT
    data/processed/master_dataset.csv   (built by build_processed_dataset.py)

ROW SELECTION
    Transition rows (is_transition == 1) are excluded, matching exactly what
    train_activity_classifier.py trains and evaluates on. The baseline must be
    computed on the same rows as the accuracy it is compared against, otherwise
    the two numbers describe different datasets.

USAGE
    python scripts/analysis/check_majority_baseline.py

EXPECTED OUTPUT (18 participants, 16,880 clean rows)
    5-class majority baseline: 0.201  -> reported accuracy 0.548, margin +0.347
    3-class majority baseline: 0.599  -> reported accuracy 0.853, margin +0.254
"""
import pandas as pd

IN_PATH = "data/processed/master_dataset.csv"

# Accuracies to compare against, from train_activity_classifier.py. Kept as
# constants so this script prints the margin directly instead of leaving the
# reader to subtract by hand.
REPORTED_ACC = {"label": 0.548, "activity_group": 0.853}

SCOPES = [
    ("label", "5-class (lying/sitting/standing/walking/running)", 5),
    ("activity_group", "3-class (stationary/walking/running)", 3),
]


def report_scope(df, column, title, n_classes):
    counts = df[column].value_counts()
    majority_class = counts.idxmax()
    baseline = counts.max() / len(df)
    reported = REPORTED_ACC[column]

    print(f"\n=== {title} ===")
    print(counts.to_string())
    print(f"\n  majority class            : {majority_class}")
    print(f"  majority-class baseline   : {baseline:.4f}")
    print(f"  random-guess baseline 1/{n_classes} : {1 / n_classes:.4f}")
    print(f"  reported LOGO-CV accuracy : {reported:.4f}")
    print(f"  margin over baseline      : {reported - baseline:+.4f}")


def main():
    df = pd.read_csv(IN_PATH)
    total = len(df)
    df = df[df["is_transition"] == 0]

    print(f"Total rows: {total}")
    print(f"Clean rows (transitions excluded): {len(df)} "
          f"| participants: {df['participant_id'].nunique()}")

    for column, title, n_classes in SCOPES:
        report_scope(df, column, title, n_classes)

    print("\n=== Conclusion ===")
    print("  The 3-class problem starts from a much higher floor (0.599 vs 0.201),")
    print("  so the raw 0.548 -> 0.853 gap (+0.305) overstates the real improvement.")
    print("  Judged against each problem's own baseline, the 5-class model actually")
    print("  clears its floor by more (+0.347) than the 3-class model does (+0.254).")


if __name__ == "__main__":
    main()

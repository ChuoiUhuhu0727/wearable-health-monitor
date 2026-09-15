"""
Supporting evidence for the activity-classifier report, Section 2 (root cause).

QUESTION THIS ANSWERS
    How much motion energy does each activity actually produce, as measured by
    std_mag (the windowed standard deviation of accelerometer magnitude)? This
    is the quantity the classifier's features are built on, so it shows directly
    which activities the feature set CAN separate and which it cannot.

WHAT THE OUTPUT SHOWS
    Static postures cluster tightly together (median std_mag ~17-32) while the
    dynamic activities sit an order of magnitude higher (walking ~269, running
    ~1410) -- a dynamic/static ratio of roughly 15x. That gap is why
    walking and running are classified reliably. Inside the static group there
    is no comparable gap, which is the measured counterpart to the mathematical
    argument in the report: magnitude is invariant to rotation, and
    lying/sitting/standing differ from each other only by orientation.

    The per-participant table is included because a pooled median can hide an
    individual whose "static" recordings were not actually still. Every
    participant shows the same static-vs-dynamic separation, so the effect is a
    property of the measurement, not an artefact of a few sessions.

    The final breakdown shows the three static postures do differ slightly in
    median (sitting 17.6 < standing 25.3 < lying 31.9), but their spreads
    (std 64-95) overlap far too heavily for that ordering to separate them.

INPUT
    data/processed/master_dataset.csv  (built by build_processed_dataset.py)
    Transition rows are excluded, matching train_activity_classifier.py.

SECOND USE
    The same numbers answer a question for the PPG adaptive-filtering track:
    whether the accelerometer signal during static postures is too flat to serve
    as a motion-noise reference. That is a separate investigation and is not
    part of this report.

USAGE
    python scripts/analysis/check_accel_variance_by_activity.py
"""
import pandas as pd

IN_PATH = "data/processed/master_dataset.csv"
ACTS = ["lying", "sitting", "standing", "walking", "running"]
STATIC = {"lying", "sitting", "standing"}


def main():
    df = pd.read_csv(IN_PATH)
    df = df[df["is_transition"] == 0].copy()

    print(f"Clean rows: {len(df)} | participants: {df['participant_id'].nunique()}")

    print("\n=== std_mag by activity (pooled across all participants) ===")
    summary = df.groupby("label")["std_mag"].agg(["median", "mean", "std", "count"]).reindex(ACTS)
    print(summary.to_string(float_format=lambda x: f"{x:.3f}"))

    static_median = df[df["label"].isin(STATIC)]["std_mag"].median()
    dynamic_median = df[~df["label"].isin(STATIC)]["std_mag"].median()
    print(f"\nstatic median std_mag:  {static_median:.3f}")
    print(f"dynamic median std_mag: {dynamic_median:.3f}")
    print(f"ratio dynamic/static:   {dynamic_median / static_median:.2f}x")

    # Pooled averages can hide a participant where static isn't actually flat --
    # an LMS filter runs per-session, not pooled across the dataset, so this is
    # the number that actually matters for case (b).
    print("\n=== per-participant median std_mag: static vs dynamic ===")
    rows = []
    for pid, g in df.groupby("participant_id"):
        s = g[g["label"].isin(STATIC)]["std_mag"].median()
        d = g[~g["label"].isin(STATIC)]["std_mag"].median()
        rows.append((pid, s, d, d / s if s > 0 else float("inf")))
    per_p = pd.DataFrame(rows, columns=["participant_id", "static_median", "dynamic_median", "ratio"])
    print(per_p.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n=== static activities broken out (lying/sitting/standing aren't necessarily equally flat) ===")
    for act in ["lying", "sitting", "standing"]:
        vals = df[df["label"] == act]["std_mag"]
        print(f"  {act:>8s}: median={vals.median():.3f}  mean={vals.mean():.3f}  n={len(vals)}")


if __name__ == "__main__":
    main()

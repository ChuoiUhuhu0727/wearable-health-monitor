"""
Data provenance for the activity-classifier report: builds the training dataset.

WHAT IT DOES
    Reads the raw per-session recordings in experiments/wrist/valid_sessions/
    (one CSV per participant, written by the device itself) and merges them into
    the single table every analysis script reads:
        data/processed/master_dataset.csv   (20,258 rows, 16,880 after excluding
                                             transitions; 18 participants)

WHY THIS SCRIPT EXISTS
    It makes the raw -> processed step reproducible and auditable. The raw
    session files are never edited by hand and the output is never edited by
    hand: to change how the dataset is built, you change this script and re-run
    it. Anyone can therefore regenerate the exact training data from the
    original device recordings.

    It also adds no measurements of its own -- the four features were computed
    on-device during recording (see firmware/ble/main.cpp:738-750). This script
    only joins, labels and flags.

WHAT IT ADDS TO EACH ROW
    participant_id      from experiments/wrist/participant_log.csv
    activity_group      lying/sitting/standing -> "stationary", others unchanged;
                        lets the 5-class and 3-class models be trained from the
                        same file without rebuilding it
    is_outlier_spike    flag only, never a filter (see below)

Cleaning decisions applied here, as documented in CHANGELOG.md (2026-07-22):
  - Dry-run/no-motion sessions are already excluded structurally (this script only
    reads valid_sessions/, never firmware_test_fixtures/).
  - Transition buffer (15s) is kept as-is, no change — preserved as the existing
    is_transition column, not filtered out here. Whether to drop transition rows
    is a training-time decision, not a data-engineering one.
  - Natural motion-spike "outliers" are KEPT (robust real-world goal, not lab-clean)
    — flagged via is_outlier_spike (median + 3*1.4826*MAD per session x activity,
    computed on clean rows only) so a later step CAN filter on it, but this script
    never drops rows for being an outlier.
  - Adds activity_group (lying/sitting/standing -> "stationary", else unchanged) —
    the model-scope question (3-class vs 5-class) is still an open decision (see
    README.md Progress Log); this column lets either be trained without re-running
    this script.
  - Joins participant_id + protocol_version from participant_log.csv.

Usage:
    python scripts/dataset/build_processed_dataset.py
"""
import csv
import statistics as stats
from collections import defaultdict

BASE = "experiments/wrist"
OUT_PATH = "data/processed/master_dataset.csv"

ACTIVITY_GROUP = {
    "lying": "stationary",
    "sitting": "stationary",
    "standing": "stationary",
    "walking": "walking",
    "running": "running",
}

OUTLIER_K = 3.0  # median + K*1.4826*MAD — see CHANGELOG.md 2026-07-22 for why K=3


def load_participant_log():
    with open(f"{BASE}/participant_log.csv", newline="") as fh:
        return {r["session_file"]: r for r in csv.DictReader(fh)}


def flag_outliers(rows):
    """rows: list of dicts for ONE session, mutated in place to add is_outlier_spike."""
    by_label = defaultdict(list)
    for r in rows:
        if r["is_transition"] == "0":
            by_label[r["label"]].append(r)

    for label, seg in by_label.items():
        vals = [float(r["mean_mag"]) for r in seg]
        med = stats.median(vals)
        mad = stats.median([abs(v - med) for v in vals])
        thresh = med + OUTLIER_K * 1.4826 * mad
        for r, v in zip(seg, vals):
            r["is_outlier_spike"] = "1" if v > thresh else "0"

    for r in rows:
        r.setdefault("is_outlier_spike", "")  # transition rows: not evaluated


def main():
    plog = load_participant_log()
    out_rows = []
    skipped = []

    for sess_file, meta in plog.items():
        path = f"{BASE}/valid_sessions/{sess_file}"
        try:
            with open(path, newline="") as fh:
                rows = list(csv.DictReader(fh))
        except FileNotFoundError:
            skipped.append(sess_file)
            continue

        flag_outliers(rows)
        for r in rows:
            out_rows.append({
                "participant_id": meta["participant_id"],
                "protocol_version": meta["protocol_version"],
                "session_file": sess_file,
                "elapsed_ms": r["elapsed_ms"],
                "label": r["label"],
                "activity_group": ACTIVITY_GROUP[r["label"]],
                "is_transition": r["is_transition"],
                "is_outlier_spike": r["is_outlier_spike"],
                "activity_class": r["activity_class"],
                "bpm": r["bpm"],
                "mean_mag": r["mean_mag"],
                "std_mag": r["std_mag"],
                "peak_rel": r["peak_rel"],
                "peak_max": r["peak_max"],
                # ppg_contact added 2026-07-14, bpm_fresh added 2026-07-15 (see
                # CHANGELOG.md) — the 3 sessions from 07-07/07-10 have neither
                # column, and the 07-14 sessions have ppg_contact but not
                # bpm_fresh. Missing = genuinely not recorded, not a bug here.
                "ppg_contact": r.get("ppg_contact", ""),
                "bpm_fresh": r.get("bpm_fresh", ""),
            })

    if skipped:
        print(f"[WARN] {len(skipped)} session(s) in participant_log.csv not found in valid_sessions/: {skipped}")

    fieldnames = list(out_rows[0].keys())
    with open(OUT_PATH, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    participants = sorted(set(r["participant_id"] for r in out_rows))
    clean = [r for r in out_rows if r["is_transition"] == "0"]
    n_spike = sum(1 for r in clean if r["is_outlier_spike"] == "1")

    print(f"Wrote {len(out_rows)} rows ({len(clean)} clean) to {OUT_PATH}")
    print(f"Participants: {len(participants)} -> {participants}")
    print(f"Clean rows per label: {dict((l, sum(1 for r in clean if r['label']==l)) for l in ACTIVITY_GROUP)}")
    print(f"Clean rows per activity_group: {dict((g, sum(1 for r in clean if r['activity_group']==g)) for g in set(ACTIVITY_GROUP.values()))}")
    print(f"Outlier-spike rate among clean rows: {n_spike}/{len(clean)} ({100*n_spike/len(clean):.2f}%)")


if __name__ == "__main__":
    main()

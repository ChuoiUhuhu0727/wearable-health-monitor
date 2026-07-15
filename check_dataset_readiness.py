"""
Dataset readiness check — scans session_*.csv files (the flash-backed
dataset, from log_serial.py) and reports whether each participant's
recording is complete and clean enough to use as training data.

Checks per activity within each file:
  - all 5 activities present (nothing truncated/aborted mid-run)
  - enough clean (non-transition) rows (~187 expected for a full 90s activity)
  - BPM within a physiologically plausible range
  - PPG contact lost (ppg_contact column, if present)
  - BPM "frozen" for an unusually long run of consecutive rows — this is
    the motion-artifact-during-beat-detection issue found by hand on
    2026-07-14 (see CHANGELOG): ppg_contact can read 1 (electrical contact
    fine) while the peak-detector still isn't finding new beats, so BPM
    holds its last value. A long frozen run is a different failure mode
    than contact loss and isn't caught by ppg_contact at all.

Usage:
    python check_dataset_readiness.py            # today's session_*.csv only
    python check_dataset_readiness.py --all       # every session_*.csv ever retrieved
    python check_dataset_readiness.py a.csv b.csv # specific files
"""

import csv
import glob
import os
import sys
from datetime import date

OUTPUT_DIR = "experiments/wrist"
ACTIVITY_LABELS = ["lying", "sitting", "standing", "walking", "running"]

BPM_MIN, BPM_MAX = 40, 180
MIN_CLEAN_ROWS = 150           # full activity is ~187 clean rows; below this = truncated
STALE_BPM_RUN_THRESHOLD = 85    # consecutive identical BPM readings ~= beat detector stalled.
# Calibrated 2026-07-14 against today's actual data (n=62 activity-blocks):
# median longest-run=32, p90=64, p95=76 — freezing for dozens of rows is
# normal behavior for this firmware's simple peak-detector, not a defect.
# Set just above p95 so only genuine tail outliers (97, 133 rows seen today)
# get flagged, instead of nearly every block in the dataset.


def find_todays_files():
    pattern = os.path.join(OUTPUT_DIR, "session_*.csv")
    today_str = date.today().strftime("%Y%m%d")
    return sorted(p for p in glob.glob(pattern) if today_str in os.path.basename(p))


def longest_identical_run(values):
    if not values:
        return 0
    best = cur = 1
    for i in range(1, len(values)):
        if values[i] == values[i - 1]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def check_file(path):
    per_label = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        has_ppg_contact_col = "ppg_contact" in fieldnames
        has_bpm_fresh_col   = "bpm_fresh" in fieldnames
        for row in reader:
            label = row["label"]
            bucket = per_label.setdefault(label, {
                "clean": 0, "trans": 0, "bpm_out_of_range": 0,
                "ppg_bad": 0, "bpm_stale": 0, "bpms": [],
            })
            is_trans = row.get("is_transition") == "1"
            if has_ppg_contact_col and row.get("ppg_contact") == "0":
                bucket["ppg_bad"] += 1
            if has_bpm_fresh_col and row.get("bpm_fresh") == "0":
                bucket["bpm_stale"] += 1
            if is_trans:
                bucket["trans"] += 1
                continue
            bucket["clean"] += 1
            try:
                bpm = float(row["bpm"])
                bucket["bpms"].append(bpm)
                if not (BPM_MIN <= bpm <= BPM_MAX):
                    bucket["bpm_out_of_range"] += 1
            except (ValueError, KeyError):
                pass

    file_flags = []
    missing_labels = [l for l in ACTIVITY_LABELS if l not in per_label]
    if missing_labels:
        file_flags.append(f"missing activities: {', '.join(missing_labels)} (truncated/aborted run)")
    if not has_ppg_contact_col:
        file_flags.append("no ppg_contact column (recorded before the 2026-07-14 validity fix)")
    if not has_bpm_fresh_col:
        file_flags.append("no bpm_fresh column (recorded before the adaptive-threshold fix — "
                           "frozen-BPM stretches can't be confirmed, only guessed via row heuristics)")

    per_label_report = {}
    for label, stats in per_label.items():
        label_flags = []
        if stats["clean"] < MIN_CLEAN_ROWS:
            label_flags.append(f"only {stats['clean']} clean rows (expected ~187)")
        if stats["bpm_out_of_range"] > 0:
            label_flags.append(f"{stats['bpm_out_of_range']} BPM out of {BPM_MIN}-{BPM_MAX}")
        if stats["ppg_bad"] > 0:
            label_flags.append(f"{stats['ppg_bad']} rows PPG contact lost")
        if has_bpm_fresh_col:
            # Real signal from firmware — trust it over the heuristic below.
            if stats["bpm_stale"] > 0:
                label_flags.append(f"{stats['bpm_stale']} rows with stale BPM (no beat detected recently)")
        else:
            # Older file, no bpm_fresh column — fall back to the statistical
            # heuristic (longest run of identical BPM values) calibrated
            # 2026-07-14 against that day's actual data distribution.
            run = longest_identical_run(stats["bpms"])
            if run >= STALE_BPM_RUN_THRESHOLD:
                label_flags.append(f"BPM frozen for {run} consecutive rows (heuristic guess — "
                                    f"no bpm_fresh column to confirm)")
        per_label_report[label] = {"clean": stats["clean"], "trans": stats["trans"], "flags": label_flags}

    any_label_flags = any(r["flags"] for r in per_label_report.values())
    ready = not file_flags and not any_label_flags
    return {"path": path, "file_flags": file_flags, "per_label": per_label_report, "ready": ready}


def main():
    args = sys.argv[1:]
    if args and args[0] == "--all":
        files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "session_*.csv")))
    elif args:
        files = args
    else:
        files = find_todays_files()

    if not files:
        print(f"No session_*.csv files found for today in {OUTPUT_DIR}/. "
              f"Pass --all for every file ever retrieved, or list paths explicitly.")
        return

    print(f"Checking {len(files)} file(s)...\n")
    results = [check_file(p) for p in files]

    ready_count = 0
    for r in results:
        status = "READY" if r["ready"] else "NEEDS REVIEW"
        if r["ready"]:
            ready_count += 1
        print(f"{os.path.basename(r['path']):45s} [{status}]")
        for flag in r["file_flags"]:
            print(f"    [FILE] {flag}")
        for label in ACTIVITY_LABELS:
            if label not in r["per_label"]:
                continue
            info = r["per_label"][label]
            flag_str = "; ".join(info["flags"]) if info["flags"] else "OK"
            print(f"    {label:10s} clean={info['clean']:4d} trans={info['trans']:3d}  {flag_str}")
        print()

    print(f"Summary: {ready_count}/{len(results)} participant(s) ready for training as-is, "
          f"{len(results) - ready_count} need review.")


if __name__ == "__main__":
    main()

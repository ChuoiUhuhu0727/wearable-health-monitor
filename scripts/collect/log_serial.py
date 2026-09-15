"""
Serial retrieval tool for WearableMonitor's onboard flash logging.
Recording happens fully untethered (battery-powered, LittleFS on the ESP32).
This script retrieves whatever session files have piled up since the last dump.

Usage:
    python scripts/collect/log_serial.py COM3

Workflow:
    1. Run this script FIRST — it starts listening immediately.
    2. THEN plug in / reset the ESP32 (order matters: the firmware only
       accepts a dump request in a short window after boot, so the script
       needs to already be sending before that window opens).
    3. Each stored participant run is saved as its own timestamped CSV in
       experiments/wrist/, and a quick quality check is printed for each.

Requires: pip install pyserial
"""

import sys
import time
import os
import re
import csv
import shutil
import statistics as stats
from collections import defaultdict
from datetime import datetime

import serial

OUTPUT_DIR         = "experiments/wrist"
VALID_DIR          = os.path.join(OUTPUT_DIR, "valid_sessions")
FIXTURE_DIR        = os.path.join(OUTPUT_DIR, "firmware_test_fixtures")
PARTICIPANT_LOG    = os.path.join(OUTPUT_DIR, "participant_log.csv")
BAUD               = 115200
RETRY_SECONDS      = 10   # how long to keep poking for the dump window
RETRY_INTERVAL     = 0.2

BPM_MIN, BPM_MAX = 40, 180      # outside this band (non-transition rows) = flag
MIN_CLEAN_ROWS   = 50           # fewer clean rows than this for a label = flag
EXPECTED_LABELS  = {"lying", "sitting", "standing", "walking", "running"}

# median(std_mag|running) / median(std_mag|lying) below this = suspect no real
# motion happened (device idle, not worn) -- see CHANGELOG.md 2026-07-22, found
# after 6/21 "complete" sessions turned out to be dry-runs that this would have
# caught immediately instead of weeks later during a full dataset audit.
DRYRUN_MIN_RUNNING_RATIO = 3.0

FILE_START_RE = re.compile(r"----- FILE: (\S+) -----")
FILE_END_RE   = re.compile(r"----- END: (\S+) -----")
FILE_KIND_RE  = re.compile(r"^(session|raw_accel|raw_ppg2|raw_ppg)_(\d+)$")


def dry_run_check(local_path):
    """Flags sessions where 'running' isn't meaningfully more energetic than
    'lying' -- a real person running always shows a huge jump; if it doesn't,
    the device most likely sat idle while the session timer auto-advanced
    through labels (confirmed cause for 6/21 sessions in the 2026-07-22 audit,
    see CHANGELOG.md). Returns a warning string, or None if it looks fine."""
    import csv as csvmod

    by_label = defaultdict(list)
    with open(local_path, newline="") as f:
        for row in csvmod.DictReader(f):
            if row["is_transition"] == "0":
                try:
                    by_label[row["label"]].append(float(row["std_mag"]))
                except (KeyError, ValueError):
                    return None  # older schema or malformed row -- skip, don't guess

    if "running" not in by_label or "lying" not in by_label:
        return None  # incomplete session -- MIN_CLEAN_ROWS check already flags this

    lying_med = stats.median(by_label["lying"])
    running_med = stats.median(by_label["running"])
    if lying_med <= 0:
        return None
    ratio = running_med / lying_med
    if ratio < DRYRUN_MIN_RUNNING_RATIO:
        return (f"running/lying std_mag ratio = {ratio:.2f} (< {DRYRUN_MIN_RUNNING_RATIO}) "
                f"-- looks like NO REAL MOTION during running. Possible dry-run/idle device, "
                f"not a real participant recording -- verify before trusting this session.")
    return None


def classify_filename(name):
    """name is the ORIGINAL filename from the firmware, before this script's own
    timestamp got appended -- e.g. 'session_3', 'raw_ppg2_3', 'diag'."""
    m = FILE_KIND_RE.match(name)
    if m:
        return m.group(1), m.group(2)  # e.g. ("raw_ppg2", "3")
    if name.startswith("diag"):
        return "diag", None
    return None, None


def final_cross_checks(session_files, diag_paths):
    """Checks that need to see MULTIPLE files from the same dump together --
    can't run per-file like quality_check(). Prints warnings, doesn't raise."""
    any_warning = False
    for num, files in sorted(session_files.items()):
        if "raw_ppg" in files and "raw_ppg2" not in files:
            print(f"  [WARN] session {num}: has raw_ppg (wrist) but no raw_ppg2 (fingertip) -- "
                  f"dual-PPG ground truth not captured this run.")
            any_warning = True
        elif "raw_ppg2" in files:
            with open(files["raw_ppg2"], newline="") as f:
                n_rows = sum(1 for _ in f) - 1  # minus header
            if n_rows <= 0:
                print(f"  [WARN] session {num}: raw_ppg2 (fingertip) has 0 data rows -- sensor likely "
                      f"failed/disconnected this run (this happened before, see session_1_20260717_183249 "
                      f"in valid_sessions/ -- that session is otherwise fine, just missing this one channel).")
                any_warning = True

    for dp in diag_paths:
        with open(dp, errors="replace") as f:
            content = f.read()
        if "BROWNOUT" in content:
            print(f"  [WARN] {os.path.basename(dp)} contains a BROWNOUT reset -- check battery charge; "
                  f"some session(s) in this dump may have been cut short mid-recording.")
            any_warning = True

    if not any_warning:
        print("  Cross-file checks: no issues found.")


def next_suggested_participant_id():
    """Guess the next participant_id as max(existing P-numbers) + 1. This is a
    GUESS assuming a new participant, not a fact — WHO wore the device is
    information this script can never know, only the human collecting data
    knows that. If today's session is actually a repeat visit from someone
    already in the log, this guess will be wrong; that's expected, fix it by
    hand (or ask Claude to fix it) after the fact, don't block on it now."""
    if not os.path.exists(PARTICIPANT_LOG):
        return "P01"
    with open(PARTICIPANT_LOG, newline="") as fh:
        nums = [int(m.group(1)) for r in csv.DictReader(fh)
                if (m := re.match(r"^P(\d+)$", r.get("participant_id", "")))]
    return f"P{(max(nums) + 1) if nums else 1:02d}"


def append_participant_log_stub(session_filename, has_raw):
    """Append 1 row to participant_log.csv for a newly-validated session.
    participant_id is pre-filled with a best-guess next sequential ID (assumes
    a new participant) so build_processed_dataset.py can run immediately without
    a manual edit in between — see next_suggested_participant_id() for why this
    is a guess, not a fact. date/time parsed from the filename's own retrieval
    timestamp (same convention every existing row already uses)."""
    m = re.match(r"^session_(\d+)_(\d{8})_(\d{6})\.csv$", session_filename)
    if m:
        _, d, t = m.groups()
        date_s, time_s = f"{d[0:4]}-{d[4:6]}-{d[6:8]}", f"{t[0:2]}:{t[2:4]}:{t[4:6]}"
    else:
        date_s, time_s = "", ""

    suggested_id = next_suggested_participant_id()
    file_exists = os.path.exists(PARTICIPANT_LOG)
    with open(PARTICIPANT_LOG, "a", newline="") as fh:
        w = csv.writer(fh)
        if not file_exists:
            w.writerow(["session_file", "date", "time", "protocol_version",
                        "participant_id", "has_raw_accel_ppg", "notes"])
        w.writerow([session_filename, date_s, time_s, "v1_fixed_order", suggested_id, has_raw,
                    f"auto-suggested {suggested_id} as a NEW participant -- if this was actually "
                    f"a repeat visitor, replace with their existing ID"])
    return suggested_id


def categorize_and_file(session_files, session_verdicts):
    """Auto-file each retrieved session based on its quality_check() verdict:
      - dryrun=True             -> firmware_test_fixtures/ (no real motion --
        not a real participant, safe to auto-categorize, see CHANGELOG.md 2026-07-22)
      - dryrun=False, complete  -> valid_sessions/, + append a participant_log.csv
        row with a best-guess next participant_id (see next_suggested_participant_id)
        so build_processed_dataset.py can run right away -- verify/correct it after
      - incomplete, not dryrun  -> left in place in experiments/wrist/, NOT
        auto-filed -- could be a real brownout-cut session worth salvaging
        (see the 2026-07-22 brownout-salvage discussion), needs a human decision,
        not an automatic bucket.
    Prints what it did; returns nothing.
    """
    os.makedirs(VALID_DIR, exist_ok=True)
    os.makedirs(FIXTURE_DIR, exist_ok=True)

    for num, verdict in sorted(session_verdicts.items()):
        files = session_files.get(num, {})
        if "session" not in files:
            continue
        session_basename = os.path.basename(files["session"])

        if verdict["dryrun"]:
            dest_dir, dest_label = FIXTURE_DIR, "firmware_test_fixtures/"
        elif not verdict["incomplete"]:
            dest_dir, dest_label = VALID_DIR, "valid_sessions/"
        else:
            print(f"  [MANUAL REVIEW] session {num}: incomplete but not a dry-run -- "
                  f"left as-is in {OUTPUT_DIR}/ (decide: salvage the clean part, or discard).")
            continue

        has_raw = "yes" if ("raw_accel" in files or "raw_ppg" in files) else "no"
        for kind, path in list(files.items()):
            shutil.move(path, os.path.join(dest_dir, os.path.basename(path)))
        print(f"  [AUTO-FILED] session {num} -> {dest_label} ({', '.join(files.keys())})")

        if dest_dir == VALID_DIR:
            suggested_id = append_participant_log_stub(session_basename, has_raw)
            print(f"  [AUTO-FILED] added row to {PARTICIPANT_LOG} for {session_basename}: "
                  f"participant_id guessed as {suggested_id} (assumes NEW participant) -- "
                  f"verify/correct after, don't block on it now.")


def quality_check(local_path):
    import csv as csvmod

    per_label = {}
    with open(local_path, newline="") as f:
        reader = csvmod.DictReader(f)
        for row in reader:
            label = row["label"]
            per_label.setdefault(label, {"clean": 0, "trans": 0, "bpm_out_of_range": 0, "ppg_bad": 0, "bpm_stale": 0})
            is_trans = row["is_transition"] == "1"
            bucket = per_label[label]
            if row.get("ppg_contact") == "0":
                bucket["ppg_bad"] += 1
            if row.get("bpm_fresh") == "0":
                bucket["bpm_stale"] += 1
            if is_trans:
                bucket["trans"] += 1
            else:
                bucket["clean"] += 1
                try:
                    bpm = float(row["bpm"])
                    if not (BPM_MIN <= bpm <= BPM_MAX):
                        bucket["bpm_out_of_range"] += 1
                except ValueError:
                    pass

    print(f"  Quality check for {os.path.basename(local_path)}:")
    if not per_label:
        print("    [FLAG] File is empty — nothing was recorded.")
        return {"incomplete": True, "dryrun": False}

    # incomplete = missing a whole activity label, or any label with too few
    # clean rows — either way this session can't be auto-filed as "valid" or
    # "dry-run fixture" (see categorize_and_file): a human needs to decide
    # whether to salvage the clean part or discard it, per the 2026-07-22
    # brownout-salvage discussion (not the same case as a dry-run).
    incomplete = EXPECTED_LABELS - set(per_label.keys()) != set()

    for label, stats in per_label.items():
        flags = []
        if stats["clean"] < MIN_CLEAN_ROWS:
            flags.append(f"only {stats['clean']} clean rows (expected ~187)")
            incomplete = True
        if stats["bpm_out_of_range"] > 0:
            flags.append(f"{stats['bpm_out_of_range']} BPM readings outside {BPM_MIN}-{BPM_MAX}")
        if stats["ppg_bad"] > 0:
            flags.append(f"{stats['ppg_bad']} rows with PPG contact lost")
        if stats["bpm_stale"] > 0:
            flags.append(f"{stats['bpm_stale']} rows with stale BPM (no beat detected recently)")

        status = "OK" if not flags else "FLAG: " + "; ".join(flags)
        print(f"    {label:10s} clean={stats['clean']:4d}  trans={stats['trans']:3d}  {status}")

    dryrun_warning = dry_run_check(local_path)
    if dryrun_warning:
        print(f"    [DRY-RUN?] {dryrun_warning}")

    return {"incomplete": incomplete, "dryrun": bool(dryrun_warning)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/collect/log_serial.py <COM_PORT>")
        print("Example: python scripts/collect/log_serial.py COM3")
        sys.exit(1)

    port = sys.argv[1]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Waiting for {port} to appear (plug in the ESP32 now if you haven't)...")
    ser = None
    while ser is None:
        try:
            ser = serial.Serial(port, BAUD, timeout=0.5)
        except serial.SerialException:
            time.sleep(0.5)
    print(f"Opened {port} at {BAUD} baud.")

    # No reset needed at all anymore (firmware now accepts a dump request
    # any time after this run's 5 activities finish, not just in the 3s
    # boot window — see checkSerialDumpRequest() in main.cpp). If the board
    # already finished its protocol, the very next "\n" below gets caught
    # immediately. If it's mid-recording (or hasn't booted this session
    # yet), the pokes are harmless — either ignored (mid-recording, firmware
    # replies "[BUSY]") or caught at boot like before.
    print(f"Listening (retrying send for up to {RETRY_SECONDS}s per cycle)... "
          f"works with no reset if the board already finished its 5 activities.")

    current_file     = None
    current_path     = None
    current_name     = None
    saved_paths      = []
    session_files    = defaultdict(dict)   # session number -> {kind: path}
    session_verdicts = {}                  # session number -> quality_check() verdict
    diag_paths       = []
    dump_started     = False
    deadline         = time.time() + RETRY_SECONDS

    while True:
        # Keep poking until the firmware's dump-request window catches it
        if not dump_started and time.time() < deadline:
            ser.write(b"\n")

        line_bytes = ser.readline()
        if not line_bytes:
            if not dump_started and time.time() >= deadline:
                print("[TIMEOUT] Still no response after retrying — still listening. If the board "
                      "hasn't finished its 5 activities yet, that's expected (it replies [BUSY]); "
                      "otherwise check it's actually powered on / connected.")
                deadline = time.time() + RETRY_SECONDS
            continue

        line = line_bytes.decode(errors="replace").rstrip()
        if not line:
            continue

        if "SESSION DUMP START" in line:
            dump_started = True
            print(f"  {line}")
            continue

        if "SESSION DUMP END" in line:
            print(f"\nRetrieved {len(saved_paths)} file(s). Running cross-file checks...")
            final_cross_checks(session_files, diag_paths)
            print("\nAuto-filing sessions...")
            categorize_and_file(session_files, session_verdicts)
            print(f"\n  [REMINDER] participant_id in {PARTICIPANT_LOG} was auto-guessed (assumes each")
            print(f"  new session = a new participant) -- go verify it's right whenever convenient,")
            print(f"  especially if today's participant has been here before.")
            print()
            break

        m = FILE_START_RE.search(line)
        if m:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(m.group(1))
            current_name = name
            current_path = os.path.join(OUTPUT_DIR, f"{name}_{timestamp}{ext}")
            current_file = open(current_path, "w", newline="")
            print(f"  -> saving to {current_path}")
            continue

        m = FILE_END_RE.search(line)
        if m:
            if current_file:
                current_file.close()
                saved_paths.append(current_path)
                # Immediate feedback per file, instead of waiting for the whole
                # dump to finish — this is the "was it saved OK + how many
                # clean rows" summary, without echoing every raw data row above.
                verdict = None
                if os.path.basename(current_path).startswith("session_"):
                    verdict = quality_check(current_path)
                else:
                    print(f"  (skipping quality check for {os.path.basename(current_path)} — not a session file)")

                kind, num = classify_filename(current_name)
                if kind == "diag":
                    diag_paths.append(current_path)
                elif kind and num:
                    session_files[num][kind] = current_path
                    if kind == "session" and verdict is not None:
                        session_verdicts[num] = verdict
            current_file = None
            current_path = None
            current_name = None
            continue

        if current_file:
            # Data row — write silently, don't echo (this is what was making
            # the terminal feel slow: printing every single CSV row).
            current_file.write(line + "\n")
            continue

        print(f"  {line}")

    ser.close()


if __name__ == "__main__":
    main()

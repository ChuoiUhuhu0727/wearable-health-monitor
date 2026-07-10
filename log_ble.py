"""
BLE live-view logger for WearableMonitor (firmware_ble/ branch).

IMPORTANT: this is a convenience/live-view layer, NOT the dataset. The
device writes every row to its own onboard flash first, independent of
BLE entirely — that flash copy (retrieved afterward with log_serial.py)
is the guaranteed record. If BLE drops (expected — range is short, roughly
a meter), you have NOT lost data, just the live view of it. Retrieve the
real dataset from flash afterward regardless of how BLE behaved.

Unlike the original version of this script, the device now embeds the
full row (elapsed_ms, label, is_transition, activity_class, bpm, and the
motion features) directly in each BLE notification — this script no
longer tracks its own clock or activity label. That removes a real risk
the old version had: the laptop's timer and the device's internal timer
drifting apart and mislabeling data (the exact bug class that caused
real problems earlier in this project with a manual phone-timer
workaround). Now the device is the single source of truth for labeling,
both on flash and over BLE.

Usage:
    pip install bleak
    python log_ble.py

Auto-reconnects on disconnect (expected given BLE's short range) and
keeps appending to the same session file rather than starting over.
Stops after MAX_RUNTIME_S or on Ctrl+C, whichever comes first.
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime

from bleak import BleakScanner, BleakClient

DEVICE_NAME      = "WearableMonitor"
CHAR_UUID        = "AA10D002-0000-0000-0000-000000000001"
OUTPUT_DIR       = "experiments/wrist"

NUM_SESSIONS     = 5
SESSION_S        = 90            # must match SESSION_MS in firmware_ble/main.cpp
MAX_RUNTIME_S    = NUM_SESSIONS * SESSION_S + 60   # small buffer past the expected total

BPM_MIN, BPM_MAX = 40, 180
MIN_CLEAN_ROWS   = 50
WARNING_COOLDOWN_S = 3    # min seconds between repeats of the same live warning

# Order matches ACTIVITY_LABELS in firmware_ble/main.cpp — the device is the
# single source of truth for *which* label a row has; this list is only used
# here to say what comes *next*, for the "get ready to switch" reminder.
ACTIVITY_LABELS = ["lying", "sitting", "standing", "walking", "running"]

FIELDNAMES = ["elapsed_ms", "label", "is_transition", "activity_class",
              "bpm", "mean_mag", "std_mag", "peak_rel", "peak_max",
              "ppgOK", "seconds_left"]


def next_label(label):
    try:
        idx = ACTIVITY_LABELS.index(label)
    except ValueError:
        return None
    return ACTIVITY_LABELS[idx + 1] if idx + 1 < len(ACTIVITY_LABELS) else None


def quality_check(local_path):
    per_label = {}
    with open(local_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row["label"]
            per_label.setdefault(label, {"clean": 0, "trans": 0, "bpm_out_of_range": 0, "ppg_bad": 0})
            is_trans = row["is_transition"] == "1"
            bucket = per_label[label]
            if row.get("ppgOK") == "0":
                bucket["ppg_bad"] += 1
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

    print(f"\n  BLE live-view quality check for {os.path.basename(local_path)}:")
    print("  (this reflects only what BLE happened to receive — the flash copy is the real dataset)")
    if not per_label:
        print("    [FLAG] Nothing received over BLE at all — check flash via log_serial.py instead.")
        return

    for label, stats in per_label.items():
        flags = []
        if stats["clean"] < MIN_CLEAN_ROWS:
            flags.append(f"only {stats['clean']} clean rows received over BLE (expected ~187 — "
                          f"low count here likely just means BLE dropped out, not that data is missing)")
        if stats["bpm_out_of_range"] > 0:
            flags.append(f"{stats['bpm_out_of_range']} BPM readings outside {BPM_MIN}-{BPM_MAX}")
        if stats["ppg_bad"] > 0:
            flags.append(f"{stats['ppg_bad']} rows with PPG sensor contact lost")

        status = "OK" if not flags else "NOTE: " + "; ".join(flags)
        print(f"    {label:10s} clean={stats['clean']:4d}  trans={stats['trans']:3d}  {status}")


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"ble_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    print(f"Scanning for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    if device is None:
        print("Device not found. Is it powered on and advertising?")
        return

    print(f"Found {device.address}.")
    print(f"Logging live view to {out_path}")
    print("(Reminder: flash on the device is the real dataset — retrieve it afterward with "
          "log_serial.py regardless of how this goes.)\n")

    f = open(out_path, "w", newline="")
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    f.flush()

    row_count = [0]
    start_time = asyncio.get_event_loop().time()

    # Mutable state carried between notification callbacks — this is *live
    # display* state only (countdown, which warning fired last, etc). It is
    # never written to the CSV or used to compute a label; the device's own
    # fields (label / is_transition / seconds_left) remain the only source
    # of truth for that, same reasoning as the payload redesign above.
    live = {
        "last_label": None,
        "last_countdown_second": None,
        "last_ppg_warn": -999.0,
        "last_bpm_warn": -999.0,
    }

    def handle_notification(sender, data):
        try:
            pkt = json.loads(data.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as e:
            print(f"[WARN] bad packet: {e}")
            return

        row = {k: pkt.get(k) for k in FIELDNAMES}
        writer.writerow(row)
        f.flush()
        row_count[0] += 1

        label        = row["label"]
        seconds_left = row["seconds_left"]
        ppg_ok       = row["ppgOK"]
        now          = asyncio.get_event_loop().time()

        # Device switched activity — this is the single source of truth
        # (currentSessionIndex on the firmware), not a locally-guessed timer.
        if label != live["last_label"]:
            nxt = next_label(label)
            settling = " (first 15s settling — not clean data yet)" if row["is_transition"] else ""
            print(f"\n=== NOW RECORDING: {label.upper()}{settling} ===")
            print(f"    Next up after this: {nxt}" if nxt else
                  "    This is the last activity — session ends after this.")
            live["last_label"] = label
            live["last_countdown_second"] = None

        # Countdown in the final 5s before the device switches activity.
        if seconds_left is not None and 0 < seconds_left <= 5 \
                and seconds_left != live["last_countdown_second"]:
            nxt = next_label(label)
            if nxt:
                print(f"  [!] Switching to '{nxt}' in {seconds_left}s — get ready")
            live["last_countdown_second"] = seconds_left

        # Sensor displacement warning — rate-limited so it doesn't spam at
        # ~2-3 rows/sec while the condition persists.
        if ppg_ok == 0 and now - live["last_ppg_warn"] > WARNING_COOLDOWN_S:
            print("  [WARNING] PPG sensor lost contact — check it's snug against your wrist")
            live["last_ppg_warn"] = now

        # BPM sanity warning, same rate-limiting.
        try:
            bpm = float(row["bpm"])
            if not (BPM_MIN <= bpm <= BPM_MAX) and now - live["last_bpm_warn"] > WARNING_COOLDOWN_S:
                print(f"  [WARNING] BPM reading {bpm:.0f} out of range — possible bad contact or motion artifact")
                live["last_bpm_warn"] = now
        except (TypeError, ValueError):
            pass

        print(f"  [{row['elapsed_ms']:>8}] {label:8s} trans={row['is_transition']} "
              f"bpm={row['bpm']:>6} std={row['std_mag']} ppgOK={ppg_ok} left={seconds_left}s")

    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= MAX_RUNTIME_S:
                print(f"\n[DONE] Reached max runtime ({MAX_RUNTIME_S}s). Stopping.")
                break

            # Re-scan fresh before every (re)connection attempt, rather than
            # reusing the BLEDevice object captured at the top of the script.
            # A stale reference can fail to reconnect (silently timing out,
            # no error message) after the peripheral fully resets — e.g. the
            # device power-cycling — even though the name/address are the
            # same, because the OS-level BLE stack tied the old handle to a
            # connection session that no longer exists.
            device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=5.0)
            if device is None:
                print("[WARN] Device not found in scan — retrying in 2s...")
                await asyncio.sleep(2)
                continue

            try:
                async with BleakClient(device) as client:
                    print("[BLE] Connected.")
                    await client.start_notify(CHAR_UUID, handle_notification)

                    # Poll connection state rather than blocking indefinitely —
                    # lets us notice a drop and move straight to reconnecting.
                    while client.is_connected:
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed >= MAX_RUNTIME_S:
                            break
                        await asyncio.sleep(1)

            except Exception as e:
                print(f"[WARN] BLE connection problem: {e!r}")

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= MAX_RUNTIME_S:
                break

            print("[WARN] BLE disconnected — likely moved out of range. "
                  "Data up to this point is safe (both here and on the device's flash). "
                  "Retrying connection in 2s...")
            await asyncio.sleep(2)

    except KeyboardInterrupt:
        print("\n[STOPPED] Interrupted by user.")
    finally:
        f.close()

    print(f"\nSaved {row_count[0]} rows (live-view only) to {out_path}")
    quality_check(out_path)


if __name__ == "__main__":
    asyncio.run(main())

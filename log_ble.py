"""
BLE live-view logger for WearableMonitor (firmware_ble/ branch).

IMPORTANT: this is a convenience/live-view layer, NOT the dataset. The
device writes every row to its own onboard flash first, independent of
BLE entirely — that flash copy (retrieved afterward with log_serial.py)
is the guaranteed record. If BLE drops (expected — range is short, roughly
a meter), you have NOT lost data, just the live view of it. Retrieve the
real dataset from flash afterward regardless of how BLE behaved.

The device embeds the full row (elapsed_ms, label, is_transition,
activity_class, bpm, and the motion features) directly in each BLE
notification — for the DATASET, the device remains the single source of
truth (both on flash and over BLE), never a locally-guessed label. That's
what avoids the old dual-clock-drift bug class (laptop timer vs device
timer disagreeing on what's currently being recorded).

Separately, this script ALSO keeps its own predicted schedule (see
resync()/predict()/local_ticker() in main()) purely to keep the
switch/countdown/finish audio cues going through a BLE dropout — this
project's BLE range is short, and cues silently stopping mid-dropout was
worse than a locally-predicted cue. That local schedule is re-synced to
the device's real values on every packet received, and is NEVER written
to the CSV or treated as the actual label — only real packets get logged.

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
import math
import os
import struct
import sys
import winsound
from datetime import datetime

from bleak import BleakScanner, BleakClient

DEVICE_NAME      = "WearableMonitor"
CHAR_UUID        = "AA10D002-0000-0000-0000-000000000001"
OUTPUT_DIR       = "experiments/wrist"

NUM_SESSIONS     = 5
SESSION_S        = 90            # must match SESSION_MS in firmware_ble/main.cpp
TRANSITION_S     = 15            # must match TRANSITION_MS in firmware_ble/main.cpp
MAX_RUNTIME_S    = NUM_SESSIONS * SESSION_S + 60   # small buffer past the expected total

BPM_MIN, BPM_MAX = 40, 180
MIN_CLEAN_ROWS   = 50
WARNING_COOLDOWN_S = 3    # min seconds between repeats of the same live warning

# Countdown checkpoints announced before a switch (seconds remaining).
# <=5s ones also get an audible beep — far enough out to react, close
# enough in to actually mean "get ready now".
COUNTDOWN_ANNOUNCE_S = {30, 15, 10, 5, 4, 3, 2, 1}
COUNTDOWN_BEEP_S     = 5

# Order matches ACTIVITY_LABELS in firmware_ble/main.cpp — the device is the
# single source of truth for *which* label a row has; this list is only used
# here to say what comes *next*, for the "get ready to switch" reminder.
ACTIVITY_LABELS = ["lying", "sitting", "standing", "walking", "running"]

FIELDNAMES = ["elapsed_ms", "label", "is_transition", "activity_class",
              "bpm", "mean_mag", "std_mag", "peak_rel", "peak_max",
              "ppg_contact", "seconds_left"]


def _make_beep_wav(freq_hz, duration_ms, sample_rate=44100):
    """Full-amplitude 16-bit mono PCM WAV of a single sine tone, built by hand
    (no numpy dependency) so beep() can play it through the real audio
    device via winsound.PlaySound."""
    n_samples = int(sample_rate * duration_ms / 1000)
    samples = [int(32767 * math.sin(2 * math.pi * freq_hz * i / sample_rate)) for i in range(n_samples)]
    data = struct.pack("<" + "h" * n_samples, *samples)
    n_channels, bits_per_sample = 1, 16
    byte_rate = sample_rate * n_channels * bits_per_sample // 8
    block_align = n_channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE",
        b"fmt ", 16, 1, n_channels, sample_rate, byte_rate, block_align, bits_per_sample,
        b"data", len(data),
    )
    return header + data


def beep(freq_hz, duration_ms):
    """Loud, reliable beep. winsound.Beep() plays through the legacy PC-speaker
    beeper driver — most modern laptops don't have that hardware at all, so it
    silently does nothing (no error, just no sound). This instead synthesizes
    an actual WAV tone and plays it through the real audio device."""
    winsound.PlaySound(_make_beep_wav(freq_hz, duration_ms), winsound.SND_MEMORY)


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
            if row.get("ppg_contact") == "0":
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
    # Firmware doesn't send an explicit "protocol finished" signal — after the
    # last activity, task_classifier/task_ble_streamer keep running forever
    # and just keep notifying seconds_left=0 for the same label indefinitely.
    # Detect that condition ourselves instead of relying on MAX_RUNTIME_S
    # (which is a much later fallback, not the actual end-of-protocol moment).
    protocol_done = [False]

    # wall-clock (loop time) estimate of when activity index 0 (lying) began.
    # The whole point: the countdown/switch/finish cues must keep working
    # through a BLE dropout (this project's own BLE range is short — see
    # module docstring), not just when a packet happens to arrive. The
    # protocol's timeline is fixed (prep + 5x90s in a known order), so once
    # this anchor is known, everything else is predictable from wall-clock
    # time alone. Re-derived from every real packet (resync()), so drift
    # never accumulates beyond the length of whatever outage is in progress.
    schedule = {"t0": None}

    def resync(label, seconds_left, now):
        if label not in ACTIVITY_LABELS or seconds_left is None:
            return
        idx = ACTIVITY_LABELS.index(label)
        seconds_into = SESSION_S - seconds_left
        schedule["t0"] = now - (idx * SESSION_S + seconds_into)

    def predict(now):
        """(label, seconds_left) from the schedule anchor alone — used to keep
        announcing during a dropout. Returns (None, None) before the first
        real packet ever arrives (no anchor yet)."""
        if schedule["t0"] is None:
            return None, None
        elapsed = now - schedule["t0"]
        idx = int(elapsed // SESSION_S)
        if idx >= NUM_SESSIONS:
            return ACTIVITY_LABELS[-1], 0
        label = ACTIVITY_LABELS[idx]
        seconds_into = elapsed - idx * SESSION_S
        return label, max(0, round(SESSION_S - seconds_into))

    def announce(label, seconds_left):
        """Switch/countdown/finish cues — the single place that decides what
        to print+beep, fed either by a real packet or by predict() during a
        dropout. Whichever source notices a change first wins; the dedup
        against live["last_label"]/last_countdown_second stops both sources
        from double-announcing the same moment."""
        if label is None:
            return

        if label != live["last_label"]:
            nxt = next_label(label)
            is_transition = seconds_left is not None and seconds_left > (SESSION_S - TRANSITION_S)
            settling = " (first 15s settling — not clean data yet)" if is_transition else ""
            print(f"\n=== NOW RECORDING: {label.upper()}{settling} ===")
            print(f"    Next up after this: {nxt}" if nxt else
                  "    This is the last activity — session ends after this.")
            for _ in range(3):
                beep(1200, 250)
            live["last_label"] = label
            live["last_countdown_second"] = None

        if seconds_left is not None and seconds_left in COUNTDOWN_ANNOUNCE_S \
                and seconds_left != live["last_countdown_second"]:
            nxt = next_label(label)
            if nxt:
                print(f"  [!] Switching to '{nxt}' in {seconds_left}s — get ready")
            else:
                print(f"  [!] Finishing '{label}' in {seconds_left}s — last activity, session almost done")
            if seconds_left <= COUNTDOWN_BEEP_S:
                beep(1800, 120)
            live["last_countdown_second"] = seconds_left

        if not protocol_done[0] and next_label(label) is None and seconds_left == 0:
            print(f"\n[DONE] '{label}' finished — all 5 activities complete. "
                  f"Retrieve the real dataset with log_serial.py (this file is live-view only).")
            for _ in range(3):
                beep(1200, 250)
            protocol_done[0] = True

    async def local_ticker():
        """Keeps switch/countdown/finish cues firing once per second using
        predict() alone — this is what actually survives a BLE dropout,
        since handle_notification simply doesn't run while disconnected."""
        while not protocol_done[0]:
            label, seconds_left = predict(asyncio.get_event_loop().time())
            announce(label, seconds_left)
            await asyncio.sleep(1)

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
        ppg_ok       = row["ppg_contact"]
        now          = asyncio.get_event_loop().time()

        resync(label, seconds_left, now)
        announce(label, seconds_left)

        # Sensor displacement warning — rate-limited so it doesn't spam at
        # ~2-3 rows/sec while the condition persists. Single low beep, distinct
        # from the 3-beep switch signal and the high-pitched countdown tick.
        # No fallback during a dropout — this needs real sensor data, unlike
        # the schedule-based cues above.
        if ppg_ok == 0 and now - live["last_ppg_warn"] > WARNING_COOLDOWN_S:
            print("  [WARNING] PPG sensor lost contact — check it's snug against your wrist")
            beep(600, 400)
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
              f"bpm={row['bpm']:>6} std={row['std_mag']} ppg_contact={ppg_ok} left={seconds_left}s")

    ticker_task = asyncio.create_task(local_ticker())

    try:
        while True:
            if protocol_done[0]:
                break

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
                        if protocol_done[0]:
                            break
                        elapsed = asyncio.get_event_loop().time() - start_time
                        if elapsed >= MAX_RUNTIME_S:
                            break
                        await asyncio.sleep(1)

            except Exception as e:
                print(f"[WARN] BLE connection problem: {e!r}")

            if protocol_done[0]:
                break

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
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass
        f.close()

    print(f"\nSaved {row_count[0]} rows (live-view only) to {out_path}")
    quality_check(out_path)


if __name__ == "__main__":
    asyncio.run(main())

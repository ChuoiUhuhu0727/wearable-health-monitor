"""
BLE data logger for WearableMonitor — 5-activity auto session
Usage: python log_ble.py
Output: experiments/wrist/session_<timestamp>.csv
"""

import asyncio
import csv
import json
import os
from datetime import datetime
from bleak import BleakScanner, BleakClient

DEVICE_NAME      = "WearableMonitor"
CHAR_UUID        = "AA10D002-0000-0000-0000-000000000001"
OUTPUT_DIR       = "experiments/wrist"
SESSION_SECONDS  = 60   # must match SESSION_MS in firmware

ACTIVITY_LABELS  = ["walk", "run", "sit", "stand", "lying"]
FIELDNAMES       = ["timestamp", "label", "activity_class", "bpm",
                    "mean_mag", "std_mag", "peak_rel", "peak_max"]


def make_handler(writer, current_label):
    def handler(sender, data):
        try:
            p = json.loads(data.decode())
            row = {
                "timestamp":      datetime.now().isoformat(),
                "label":          current_label[0],
                "activity_class": p.get("a"),
                "bpm":            p.get("bpm"),
                "mean_mag":       p.get("mean"),
                "std_mag":        p.get("std"),
                "peak_rel":       p.get("pr"),
                "peak_max":       p.get("pm"),
            }
            writer.writerow(row)
            print(f"  [{row['timestamp']}]  bpm={row['bpm']:.1f}  class={row['activity_class']}")
        except Exception as e:
            print(f"[WARN] bad packet: {e}")
    return handler


async def main():
    print(f"Scanning for '{DEVICE_NAME}'...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    if device is None:
        print("Device not found. Is the ESP32 powered on and advertising?")
        return

    print(f"Found {device.address}. Connecting...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = os.path.join(OUTPUT_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    connected = [True]

    def on_disconnect(client):
        connected[0] = False
        print("\n[WARN] BLE disconnected — move closer to the laptop!")

    with open(filename, "w", newline="") as f:
        writer     = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        current_label  = [ACTIVITY_LABELS[0]]
        rows_in_session = [0]

        original_handler = make_handler(writer, current_label)
        def counting_handler(sender, data):
            rows_in_session[0] += 1
            original_handler(sender, data)

        async with BleakClient(device, disconnected_callback=on_disconnect) as client:
            await client.start_notify(CHAR_UUID, counting_handler)

            for i, label in enumerate(ACTIVITY_LABELS):
                current_label[0]   = label
                rows_in_session[0] = 0
                print(f"\n{'='*50}")
                print(f"  SESSION {i+1}/{len(ACTIVITY_LABELS)}: {label.upper()}")
                print(f"  Duration: {SESSION_SECONDS}s  |  Stay within 5m of the laptop")
                print(f"{'='*50}")

                for _ in range(SESSION_SECONDS):
                    await asyncio.sleep(1)
                    if not connected[0]:
                        print(f"  [!] Session {i+1} aborted — reconnect and re-run.")
                        return

                print(f"  [OK] {rows_in_session[0]} rows saved for '{label}'")

            try:
                await client.stop_notify(CHAR_UUID)
            except Exception:
                pass

    print(f"\nAll sessions complete. Saved: {filename}")


if __name__ == "__main__":
    asyncio.run(main())

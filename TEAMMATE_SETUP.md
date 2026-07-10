# Setup Guide — Data Collection (Windows)

Follow these steps in order. Everything in a box is a command — paste it into
**PowerShell** exactly as written.

Recording happens fully untethered (battery-powered) — the wearable is
assumed to already be flashed and handed to you ready to go. You don't need
PlatformIO or to touch the firmware at all, just the Python scripts below.

## 0. Prerequisites (one-time install)

1. Install Git for Windows: https://git-scm.com/download/win (accept all defaults)
2. Install Python 3.10+: https://www.python.org/downloads/ — **check "Add python.exe to PATH"** during install
3. Accept the GitHub collaborator invite email vịt sends you (check your inbox/spam)
4. Have the wearable device charged/powered (battery or power bank — not USB into your laptop for the actual activities)

## 1. Get the code

```powershell
git clone https://github.com/ChuoiUhuhu0727/wearable-health-monitor.git
cd wearable-health-monitor
git checkout week1-2/baseline-freertos
```

## 2. Install the Python dependencies

```powershell
python -m pip install pyserial bleak matplotlib
```

- `pyserial` — required, for retrieving data over USB after recording
- `bleak` — optional, only needed if you want to watch data live during recording (recommended, see step 4)
- `matplotlib` — optional, only needed to self-check your data before pushing (recommended, see step 6)

## 3. Quick sensor check (before you start moving)

Plug the device into your laptop via USB, open a Serial Monitor (PlatformIO's
plug icon, or `pio device monitor -b 115200`), and watch for ~15-30 seconds:

- `ppgOK:1` → heart-rate sensor detected, good to go
- `ppgOK:0` or a `[WARN] MAX30102 không tìm thấy` message → sensor isn't
  detected — check its position/connection before doing a full session,
  otherwise that data will be unusable

This takes 30 seconds and saves you from redoing an entire session later.

## 4. Record — fully untethered, with an optional live view

1. Unplug the USB cable. Power the device from a battery/power bank instead.
2. It automatically starts a 5-activity sequence — lying, sitting, standing,
   walking, running — 90 seconds each (15s settle + 75s recorded).
3. Data is saved directly onto the device as it goes — nothing is lost even
   if you're not near a laptop, WiFi/BLE never connects, or it drops mid-way.

**Recommended: run the live view for stationary activities.**
The buzzer's audio output is not reliable on battery power (a known,
unresolved hardware quirk), so don't rely on beeps to know what's happening.
Instead, from your laptop:

```powershell
python log_ble.py
```

Keep the laptop within about a meter of the device. While connected, the
terminal tells you exactly what's going on — no guessing:
- `=== NOW RECORDING: STANDING ===` when an activity starts, plus what's next
- `[!] Switching to 'walking' in 5s — get ready` in the last 5 seconds of each activity
- `[WARNING] PPG sensor lost contact` if the sensor isn't reading you properly — **fix
  it immediately** (adjust the strap) rather than finishing the session and finding out later

**This will disconnect once you start walking/running** — BLE range is short
(roughly a meter), and that's expected, not an error. You'll see
`[WARN] BLE disconnected — likely moved out of range` — your data is still
safe on the device's flash. Before walking away, just note the time: each
activity is a fixed 90 seconds, in the order above, so once you've seen the
"NOW RECORDING: WALKING" banner you can count 90s yourself (phone timer) for
the walking and running legs.

## 5. Retrieve the recorded data

```powershell
python log_serial.py COM3
```

(Replace `COM3` with your device's actual port — check Device Manager → Ports
if unsure.)

**Important — start this script BEFORE plugging in / resetting the device.**
It listens first, then you plug in or press reset; it grabs a short window
right at boot to pull the data off. If it times out, just reset the board
again — the script keeps retrying automatically.

Each participant's run is saved as its own timestamped CSV in
`experiments/wrist/`, and the script immediately prints a quality check
(row counts, any suspicious BPM readings) so you know right away if anything
needs to be redone.

## 6. Check your data before pushing

```powershell
python visualize_session.py experiments/wrist/session_1_<your-timestamp>.csv
```

(Omit the path to auto-pick the most recently retrieved file.)

This plots BPM and motion for the whole session, shaded by activity. What a
**good** session looks like: motion (`mean_mag`/`std_mag`) trending upward
through lying → sitting → standing → walking → running, roughly in that
order of intensity. If your plot looks flat across all 5 activities, or has
a big unexplained dead zone, message vịt with the plot before pushing —
likely means the sensor slipped or a segment got skipped.

## 7. Push your data and open a Pull Request

```powershell
git checkout -b data/<your-name>
git add experiments/wrist/
git commit -m "Add wrist data session(s) from <your-name>"
git push origin data/<your-name>
```

Replace `<your-name>` with your actual name (e.g. `data/khang`).

After the push, GitHub will print a URL in the terminal like:
`https://github.com/ChuoiUhuhu0727/wearable-health-monitor/pull/new/data/<your-name>`

Open that URL in your browser, click **"Create pull request"**, and you're done.

## If something breaks

- Sensor check shows `ppgOK:0` → the MAX30102 isn't detected. Check its wiring/
  positioning before recording — data collected in this state is unusable.
- `log_ble.py` says "Device not found" and keeps retrying → the device isn't
  advertising (not powered, or already connected to something else) or
  you're too far away — get within a meter and check the battery.
- `log_serial.py` keeps timing out → make sure you started the script
  *before* resetting the device, and that you picked the right COM port.
- `python -m pip install ...` fails → make sure `pip` works at all: run
  `python -m pip --version` first; if that errors, Python wasn't added to PATH
  during install (reinstall Python and check the PATH box).
- `git push` says "permission denied" → the collaborator invite wasn't accepted
  yet — check email, or ask vịt to resend it.

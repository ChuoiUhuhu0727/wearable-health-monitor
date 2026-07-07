# Setup Guide — Data Collection (Windows)

Follow these steps in order. Everything in a box is a command — paste it into
**PowerShell** exactly as written.

Recording now happens fully untethered (battery-powered) — you don't need to
join any WiFi network or keep your laptop nearby while doing the activities.
Your laptop is only needed at the very start (quick sensor check) and the
very end (retrieving the data).

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

## 2. Install the Python dependency

```powershell
python -m pip install pyserial
```

## 3. Quick sensor check (before you start moving)

Plug the device into your laptop via USB, open a Serial Monitor (PlatformIO's
plug icon, or `pio device monitor -b 115200`), and watch for ~15-30 seconds:

- `ppgOK:1` → heart-rate sensor detected, good to go
- `ppgOK:0` or a `[WARN] MAX30102 không tìm thấy` message → sensor isn't
  detected — check its position/connection before doing a full session,
  otherwise that data will be unusable

This takes 30 seconds and saves you from redoing an entire session later.

## 4. Record — fully untethered

1. Unplug the USB cable. Power the device from a battery/power bank instead.
2. It automatically starts a 5-activity sequence — lying, sitting, standing,
   walking, running — 90 seconds each (15s settle + 75s recorded).
3. A buzzer signals **3 beeps** between activities, **5 beeps** when the whole
   sequence is done.
4. Data is saved directly onto the device — nothing is lost even without
   WiFi or a nearby laptop.
5. Repeat for more participants back-to-back if needed — just power-cycle the
   device between people. No need to plug into a laptop in between.

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

## 6. Push your data and open a Pull Request

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
- `log_serial.py` keeps timing out → make sure you started the script
  *before* resetting the device, and that you picked the right COM port.
- `python -m pip install pyserial` fails → make sure `pip` works at all: run
  `python -m pip --version` first; if that errors, Python wasn't added to PATH
  during install (reinstall Python and check the PATH box).
- `git push` says "permission denied" → the collaborator invite wasn't accepted
  yet — check email, or ask vịt to resend it.

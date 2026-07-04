# Setup Guide — Data Collection (Windows)

Follow these steps in order. Everything in a box is a command — paste it into
**PowerShell** exactly as written.

## 0. Prerequisites (one-time install)

1. Install Git for Windows: https://git-scm.com/download/win (accept all defaults)
2. Install Python 3.10+: https://www.python.org/downloads/ — **check "Add python.exe to PATH"** during install
3. Make sure Bluetooth is turned on on your laptop (Settings → Bluetooth & devices)
4. Accept the GitHub collaborator invite email vịt sends you (check your inbox/spam)

## 1. Get the code

```powershell
git clone https://github.com/ChuoiUhuhu0727/wearable-health-monitor.git
cd wearable-health-monitor
git checkout week1-2/baseline-freertos
```

## 2. Install the Python dependency

```powershell
pip install bleak
```

## 3. Run the data collection script

1. Power on the ESP32 (WearableMonitor device) and make sure it's advertising.
2. Run:

```powershell
python log_ble.py
```

3. The script scans for the device, connects, then walks you through 5 activities
   in order — **walk, run, sit, stand, lying** — 60 seconds each. Follow the
   on-screen prompt for each activity and stay within ~5m of the laptop.
4. When it finishes you'll see:
   `All sessions complete. Saved: experiments/wrist/session_<timestamp>.csv`

   You can re-run step 3 multiple times if you want more sessions — each run
   creates a new timestamped CSV file, nothing gets overwritten.

## 4. Push your data and open a Pull Request

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

- `python log_ble.py` says "Device not found" → check ESP32 is powered on and
  not already connected to another phone/laptop.
- `pip install bleak` fails → make sure `pip` works at all: run `python -m pip --version`
  first; if that errors, Python wasn't added to PATH during install (reinstall
  Python and check the PATH box).
- `git push` says "permission denied" → the collaborator invite wasn't accepted
  yet — check email, or ask vịt to resend it.

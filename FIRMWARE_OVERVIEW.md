# Firmware Overview — `firmware_main/main.cpp`

One-paragraph summary for a quick read: this is a FreeRTOS firmware for a wrist-worn
device (Seeed XIAO ESP32-S3) that reads motion (MPU6050) and heart-rate (MAX30102)
sensors in real time, classifies activity from the motion signal, and logs
`(time, activity label, heart rate, motion features)` rows to onboard flash —
fully untethered on battery, with no phone or laptop required during recording.
Data is pulled off later over USB with a retrieval script.

## Task architecture

Five FreeRTOS tasks, communicating only through queues (no shared globals holding
data) so each task can run at its own rate without blocking the others:

| Task | Priority | Rate | Role |
| :--- | :---: | :--- | :--- |
| `task_imu_reader` | 3 | 25 Hz | Reads raw accelerometer over I2C, pushes to `imu_queue` |
| `task_ppg_reader` | 3 | 100 Hz | Reads raw IR/Red signal from the heart-rate sensor, pushes to `ppg_queue` |
| `task_classifier` | 2 | driven by IMU | Slides a 60-sample window over the accel data → extracts features → activity class; separately drains the PPG queue → detects heartbeats → BPM |
| `task_ble_streamer` | 1 | driven by classifier output | Writes each result to the flash-backed session file (the permanent record) and optionally streams live over BLE/UDP for debugging |
| `task_session_buzzer` | 1 | every 90s | Drives the protocol timer: cycles through 5 fixed activities (lying → sitting → standing → walking → running), 90 seconds each, signaling transitions with the buzzer |

`classifier.h` holds a small decision-tree function (`classifySignal`) trained offline
on 3 features from the accelerometer window — this is the "AI" part of the pipeline,
currently a lightweight binary classifier (normal vs. intense movement).

## Untethered recording (the core design decision)

The device does **not** need WiFi, BLE, or a laptop connection to record — it writes
directly to its own onboard flash (LittleFS filesystem) as it collects. Each
participant run becomes its own file, `/session_N.csv`, auto-numbered so multiple
people can be recorded back-to-back just by power-cycling the device between them.

Retrieval happens later, in one batch: `log_serial.py` (repo root) is run on a
laptop, the device is plugged in/reset, and a short window right after boot lets the
script pull every stored file off, split them into timestamped CSVs under
`experiments/wrist/`, and print a per-file data-quality check (row counts, BPM
sanity) so problems surface immediately instead of after the fact.

## Diagnostic logging (`/diag.log`)

A second, separate flash file used purely for firmware debugging — logs the reset
reason on every boot (crash vs. clean power-on vs. brownout) and traces the buzzer's
mutex/hardware calls step-by-step. Not part of the actual dataset; retrieved and
cleared alongside session files by the same `log_serial.py` run.

## File map

| File | Purpose |
| :--- | :--- |
| `firmware_main/main.cpp` | All firmware logic described above |
| `firmware_main/classifier.h` | The trained activity decision-tree function |
| `log_serial.py` | Laptop-side retrieval + data-quality-check script |
| `TEAMMATE_SETUP.md` | Step-by-step instructions for a collaborator to record a participant |

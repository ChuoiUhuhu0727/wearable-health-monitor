# Firmware Overview — `firmware_main/main.cpp`

One-paragraph summary for a quick read: this is a FreeRTOS firmware for a wrist-worn
device (Seeed XIAO ESP32-S3) that reads motion (MPU6050) and heart-rate (MAX30102)
sensors in real time, classifies activity from the motion signal, and logs
`(time, activity label, heart rate, motion features)` rows to onboard flash —
fully untethered on battery, with no phone or laptop required during recording.
Data is pulled off later over USB with a retrieval script.

**Note on branches (as of 2026-07-10):** this document describes `firmware_main/`,
which uses Option 4 (a Jetson-hosted WiFi AP + UDP live telemetry) — that work is
parked, not abandoned, mid-way through debugging an untethered connectivity issue.
The team has switched to `firmware_ble/` for actual data collection in the meantime
— a simpler, previously-proven-stable branch using BLE instead of WiFi (shorter
range, but no Jetson/hotspot infrastructure required). Same sensor/classifier/flash
pipeline, same session protocol — only the live-view transport differs. See
`firmware_ble/main.cpp`'s own header comment and `log_ble.py` (repo root).

## Task architecture

Six FreeRTOS tasks, communicating only through queues (no shared globals holding
data) so each task can run at its own rate without blocking the others:

| Task | Priority | Rate | Role |
| :--- | :---: | :--- | :--- |
| `task_imu_reader` | 3 | 25 Hz | Reads raw accelerometer over I2C, pushes to `imu_queue` |
| `task_ppg_reader` | 3 | 100 Hz | Reads raw IR/Red signal from the heart-rate sensor, pushes to `ppg_queue` |
| `task_classifier` | 2 | driven by IMU | Slides a 60-sample window over the accel data → extracts features → activity class; separately drains the PPG queue → detects heartbeats → BPM |
| `task_ble_streamer` | 1 | driven by classifier output | Writes each result to the flash-backed session file (the permanent record) **first**, then best-effort forwards it to `telemetry_queue`. BLE is currently disabled |
| `task_session_buzzer` | 1 | every 90s | Drives the protocol timer: cycles through 5 fixed activities (lying → sitting → standing → walking → running), 90 seconds each, signaling transitions with the buzzer |
| `task_telemetry` | 1 | driven by `telemetry_queue` | **(Option 4)** Drains the queue and sends each packet to the Jetson over UDP — a live-view convenience layer, isolated from the recording path |

`classifier.h` holds a small decision-tree function (`classifySignal`) trained offline
on 3 features from the accelerometer window — this is the "AI" part of the pipeline,
currently a lightweight binary classifier (normal vs. intense movement).

## Data pipeline — one data point's journey, start to finish

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━ SENSING ━━━━━━━━━━━━━━━━━━━━━━━━━━━

 [MPU6050 motion sensor]         [MAX30102 heart-rate sensor]
   raw acceleration                 raw light reading
         │  I2C, 25×/sec                  │  I2C, 100×/sec
         ▼                                ▼
 task_imu_reader                   task_ppg_reader
 (main.cpp:374)                    (main.cpp:412)
         │                                │
         ▼  imu_queue                     ▼  ppg_queue
          ╲                              ╱
           ╲____________________________╱
                        │
━━━━━━━━━━━━━━━━━━━━━━━━━━━ THINKING ━━━━━━━━━━━━━━━━━━━━━━━━━━

                        ▼
               task_classifier
               (main.cpp:438)
     figures out: activity? heart rate?
                        │
                        ▼  output_queue

━━━━━━━━━━━━━━━━━━━━━━━━━━━ THE SPLIT ━━━━━━━━━━━━━━━━━━━━━━━━━

               task_ble_streamer  (main.cpp:546)
                        │
        ┌───────────────┴────────────────┐
        ▼ ALWAYS HAPPENS                  ▼ BEST-EFFORT ONLY
  sessionFile.printf()              xQueueSend(telemetry_queue)
  (main.cpp:575)                    (main.cpp:597)
        │                                 │
        ▼                                 ▼
  /session_N.csv                   task_telemetry
  on device's own flash            (main.cpp:621)
  ← THE REAL DATASET                      │
        │                                 ▼  telemetrySendUDP()
        │                           (main.cpp:636)
        │                                 │
        │                                 ▼  shouted over WiFi
        │                           [Jetson: udp_server.py]
        │                           live screen, may miss packets
        │
━━━━━━━━━━━━━━━━━━━━━━━━━━━ RETRIEVAL (later, over USB) ━━━━━━━

        ▼
  log_serial.py (your laptop)
        │
        ▼
  experiments/wrist/session_*.csv
  ← what you actually train on
```

**The split point** (`task_ble_streamer`) is the one and only place where "guaranteed"
and "best-effort" branch apart. Everything above it (sensing, thinking) is shared by
both paths equally. Everything below the left branch is rock-solid; everything below
the right branch can vanish and nothing upstream cares. Two different consumers read
this data at different times, from two different copies — the Jetson sees it *live*
(right branch), your laptop sees it *later* (bottom-left, via `log_serial.py`).

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

## Live telemetry over WiFi (Option 4, `jetson_server/`)

Solves a specific usability problem: checking sensor health before recording, and
retrieving data afterward, both used to require physically opening Serial Monitor,
closing it, unplugging USB, switching to battery, and resetting the device — a
fragile sequence that wasn't always reliable. Option 4 moves both of those off
USB entirely: a Jetson Orin Nano hosts its own private WiFi network (bypassing
the campus firewall, which is what broke an earlier WiFi attempt — see
`data_collection_pipeline_v2` project history), and the device pushes live
status/data to it over UDP while running purely on battery.

UDP was chosen over an earlier HTTP implementation (`firmware_main/http_client.h`,
kept intact but unused, not deleted) because it has no connection state to lose
and no `connect()` step to hang on — it structurally avoids the two most painful
failure modes for this layer ("connection lost mid-session," "can't connect at
all"), rather than just handling them gracefully after the fact. See
`jetson_server/udp_server.py` and `firmware_main/udp_client.h`.

**This is strictly a convenience/live-view layer, never a replacement for flash
logging.** UDP sends (`firmware_main/udp_client.h`) never block — no handshake,
no acknowledgment — and their result is ignored; if the Jetson is unreachable,
`task_telemetry` just drops packets silently, and nothing else in the firmware
is affected, because the flash write in `task_ble_streamer` always happens
first, before the telemetry push is even attempted. Setup instructions:
`jetson_server/setup_ap.md`. Known silent-failure points and how to tell them
apart during testing: `OBSERVATION_CHECKLIST.md` (repo root).

## Diagnostic logging (`/diag.log`)

A second, separate flash file used purely for firmware debugging — logs the reset
reason on every boot (crash vs. clean power-on vs. brownout) and traces the buzzer's
mutex/hardware calls step-by-step. Not part of the actual dataset; retrieved and
cleared alongside session files by the same `log_serial.py` run.

## File map

| File | Purpose |
| :--- | :--- |
| `firmware_main/main.cpp` | All firmware logic described above (Option 4 / WiFi branch, parked) |
| `firmware_ble/main.cpp` | Active data-collection branch — same pipeline, BLE instead of WiFi |
| `firmware_main/classifier.h`, `firmware_ble/classifier.h` | The trained activity decision-tree function |
| `firmware_main/udp_client.h` | Option 4 — UDP telemetry helper, in use |
| `firmware_main/http_client.h` | Option 4 — HTTP telemetry helper, kept but unused |
| `jetson_server/udp_server.py` | Option 4 — Jetson-side UDP receiver + live console/log output, in use |
| `jetson_server/server.py` | Option 4 — Jetson-side HTTP receiver, kept but unused |
| `jetson_server/setup_ap.md` | Option 4 — one-time Jetson WiFi AP setup instructions |
| `OBSERVATION_CHECKLIST.md` | What to watch for while testing Option 4 — silent-failure points, task-concurrency risks, hardware→software layers |
| `log_serial.py` | Laptop-side retrieval + data-quality-check script (works for both branches — flash schema is identical) |
| `log_ble.py` | Laptop-side live view over BLE (`firmware_ble/` only) — countdown/next-activity/sensor warnings, auto-reconnect |
| `visualize_session.py` | Plots a retrieved session CSV (BPM + motion, shaded by activity) so you can eyeball whether it's valid before training on it |
| `TEAMMATE_SETUP.md` | Step-by-step instructions for a collaborator to record a participant |

# Observation Checklist — what to watch for as you test Option 4

This isn't a "does it work" checklist — it's a "how would I know if it
*didn't*" checklist. Most of this project's real bugs so far (mutex
deadlock, USB-CDC hang, stack overflow, solder issues) never announced
themselves with an error message. They looked like normal operation
until someone noticed a symptom days later. Use this list to actively
look for symptoms rather than waiting for a crash to tell you something's
wrong.

---

## 1. What can fail silently (no error, no crash — check these actively)

| # | What | Why it's silent | How to actually check |
| :-: | :--- | :--- | :--- |
| 1 | UDP packet loss | No delivery confirmation by design — sender never learns a packet didn't arrive | Watch the Jetson console for gaps in the expected ~2.4s-per-window telemetry cadence, not just "is anything showing up at all" |
| 2 | Wrong/stale destination address | `endPacket()` returns success whether or not anything is listening at that address | Confirm `JETSON_UDP_HOST` in `udp_client.h` actually matches the Jetson's current hotspot IP (`ip addr show wlan0` on the Jetson) — re-check after any Jetson reboot, DHCP can reassign |
| 3 | WiFi not actually connected | `telemetrySendUDP()` silently no-ops if `WiFi.status() != WL_CONNECTED` — by design, so it never blocks, but that also means it never tells you | Add a periodic `Serial.printf("[WiFi] status=%d\n", WiFi.status())` during bench testing, or watch for total silence on the Jetson from the moment of boot |
| 4 | PPG sensor losing skin contact | Already flagged via `ppgOK`/BPM-range checks in the telemetry payload and `log_serial.py`'s quality check — but only if something is actually reading those flags | Don't just glance at the Jetson console scrolling by — actually read the `OK` / flag column per line during a real session |
| 5 | LittleFS silently near-full | `if (sessionFile)` guards catch total open failure, not a flash that's nearly full and starts failing mid-write | Periodically check `LittleFS.usedBytes()` / `LittleFS.totalBytes()` if sessions start looking truncated for no other reason |
| 6 | A task crash/reboot mid-session | Session just stops; a new boot silently starts a new `/session_N.csv` | Check `/diag.log`'s reset reason after every retrieval — `POWERON`/`OTHER` is a clean stop, `PANIC`/`*_WDT`/`BROWNOUT` means something crashed and nobody told you live |
| 7 | Device rebooted mid-telemetry-stream | `elapsed_ms` just resets to a small number again — easy to misread as continuous data | `udp_server.py` already flags this (a big backward jump in `elapsed_ms`) — don't ignore that `[NOTE]` line when it appears |
| 8 | Buzzer not sounding | Known, already-parked issue — code path completes with no error even when no sound is produced | Don't assume "no crash" means "beeped" — this project already learned that lesson once |

---

## 2. What can overlap / run concurrently (task-timing and shared-resource risks)

| # | Tasks involved | Shared resource | What to watch |
| :-: | :--- | :--- | :--- |
| 1 | `task_imu_reader` + `task_ppg_reader` | `i2c_mutex` (I2C bus) | Both are priority 3 — if one holds the bus longer than expected, the other's sample rate degrades. Watch IMU/PPG data for gaps or timing jitter, not just "is data present" |
| 2 | `task_session_buzzer` + `task_classifier`'s PPG watchdog | `buzzer_mutex` | Both call `buzz()`. The bounded 500ms wait means one *can* skip a beep under contention rather than block — if beeps go missing, this is a candidate before assuming hardware |
| 3 | Any task calling `diagLog()` | `diag_mutex` | Bounded 200ms wait, same pattern — a missing diagnostic line doesn't necessarily mean the event didn't happen, it could mean the mutex wait timed out |
| 4 | `task_ble_streamer` (producer) + `task_telemetry` (consumer) | `telemetry_queue` | Producer never blocks (`xQueueSend(..., 0)`) — under sustained WiFi slowness, packets get silently dropped rather than queued forever. This is intentional, but means telemetry can under-represent activity during exactly the moments WiFi is struggling |
| 5 | WiFi radio activity vs. sensor-reading tasks | CPU/radio scheduling, not an explicit mutex | This is **new** with Option 4 — the WiFi stack's own internal tasks run at system-level priority and can compete for CPU with `task_imu_reader`/`task_ppg_reader` (priority 3) in ways that didn't exist when WiFi was mostly idle. Watch IMU sample timing specifically during periods of active UDP sending — if 25 Hz starts looking uneven only when telemetry is flowing, this is the suspect |
| 6 | Buzzer current draw + WiFi TX current draw | Shared battery/power rail | Also new — a buzzer beep now has a real chance of overlapping with active WiFi transmission (previously WiFi was mostly idle broadcast). If buzzer reliability regresses further specifically after adding Option 4, check whether beeps and telemetry sends are landing at the same moment |
| 7 | Multiple device boots writing to the same Jetson log session | None (by design — `udp_server.py` doesn't distinguish boots except via the elapsed_ms heuristic) | If you power-cycle the device multiple times during one Jetson server run, all boots' telemetry lands in the same `.jsonl` file — use the `[NOTE]` reboot markers to mentally segment it, don't treat it as one continuous timeline |

---

## 3. Layers to observe, hardware → software (check top-to-bottom when something looks wrong)

Work down this list when diagnosing — each layer can look fine while the one below it is actually broken, which is why isolating *which* layer is at fault (rather than guessing) is what saved time in every bug this project has actually solved so far.

1. **Power** — battery charge level, voltage under load. New risk from Option 4: WiFi TX current spikes now happen throughout the session (not just at boot), stacking with buzzer current draw. If problems correlate with low battery specifically, this is the layer.
2. **Physical/electrical connections** — solder joints, connector seating. This project's most expensive-to-diagnose bugs (twice) were here, not in code. Re-check after any physical handling of the board.
3. **I2C bus** — SDA/SCL signal integrity, shared mutex correctness. Symptom: `Wire.cpp` errors in Serial, or IMU/PPG data going stale.
4. **RF/WiFi link** — signal strength and range between device and Jetson AP. No direct RSSI logging exists yet — if you want this, `WiFi.RSSI()` can be added to the telemetry payload cheaply. Until then, infer link quality from UDP packet arrival consistency as the participant moves.
5. **Transport (UDP)** — best-effort delivery. Expect *some* loss under motion/range; distinguish that from *total* silence (wrong address/port, or WiFi never connected — see section 1).
6. **Application/data layer** — JSON payload correctness, field values making physical sense (`bpm` in range, `label` matching the activity actually being performed, `ppgOK` true when the sensor is worn correctly).
7. **FreeRTOS task-scheduling layer** — stack margins, task priorities, queue depths. This is where the stack-overflow bug lived. If you want proactive visibility instead of waiting for a crash, `uxTaskGetStackHighWaterMark(NULL)` inside a task reports its remaining stack headroom — worth checking on `task_telemetry` specifically the first few times, since it's the newest task and has the least track record.
8. **Flash storage (LittleFS)** — free space, file count vs. `MAX_STORED_SESSIONS`. Symptom of exhaustion: writes silently stop succeeding rather than erroring loudly.
9. **Retrieval/host tooling** — `log_serial.py`, COM port assignment (already a known friction point — Windows can reassign the port number after any replug).

**Rule of thumb:** when something looks broken, don't start by re-reading code — start by figuring out which layer in this list is actually where the observed symptom first appears. Every bug this project has actually resolved (not just worked around) was found this way, not by guessing at the code first.

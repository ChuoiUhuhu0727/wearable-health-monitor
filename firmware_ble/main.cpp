// =====================================================================
//  WEARABLE ACTIVITY & HEART-RATE MONITOR — FreeRTOS firmware (BLE branch)
//
//  Forked from firmware_main/ on 2026-07-10. That branch (Option 4 —
//  Jetson-hosted WiFi AP + UDP telemetry) is kept intact and untouched
//  for whenever there's time to come back to it — see
//  [[project-option4-jetson-plan]] and firmware_main/main.cpp.
//
//  This branch goes back to BLE — the original transport, less polished
//  but proven stable. Known limitation: BLE range is short (data drops
//  if the participant moves more than roughly a meter from the laptop),
//  but that's an accepted tradeoff for something that reliably works
//  right now, rather than continuing to debug the WiFi/Jetson setup.
//
//  WHAT THIS DOES: reads motion (IMU) + heart-rate (PPG) sensors, classifies
//  activity from the motion signal, and logs every result BOTH to onboard
//  flash (the guaranteed record, works with zero connection at all) AND
//  live over BLE notify (convenience/near-real-time view — same row
//  schema as the flash CSV, so nothing needs a separate clock or label
//  tracker on the laptop side; see log_ble.py, repo root).
//
//  A fixed 5-activity protocol (lying/sitting/standing/walking/running,
//  90s each) is driven by an internal timer and signaled with a buzzer
//  (currently disabled — see BUZZER_ENABLED below, inherited from the
//  Option 4 branch where it was parked to isolate a different bug; the
//  underlying "no audible sound when untethered" issue is unrelated to
//  BLE vs WiFi and still unresolved either way).
//
//  TASK ARCHITECTURE — 5 FreeRTOS tasks, communicating only through
//  queues (no data in shared globals), so each runs at its own rate
//  without blocking the others:
//
//   task_imu_reader     (priority 3, 25 Hz)   → imu_queue
//   task_ppg_reader     (priority 3, 100 Hz)  → ppg_queue
//   task_classifier     (priority 2, driven by IMU) — slides a window over
//                         the accel data → features → activity class;
//                         separately drains ppg_queue → beat detection →
//                         BPM → output_queue
//   task_ble_streamer   (priority 1, driven by classifier output) — writes
//                         each result to the flash-backed session file
//                         (THE permanent record) FIRST, then best-effort
//                         notifies the same row over BLE
//   task_session_buzzer (priority 1) — the protocol's master timer: owns
//                         currentSessionIndex/sessionStartMs, advances
//                         through the 5 fixed activities every 90s, and
//                         signals each transition with the buzzer
//
//  KEY DESIGN RULES (unchanged from firmware_main):
//    - No data in global variables shared between tasks — everything
//      goes through a queue.
//    - No delay() — only vTaskDelay / vTaskDelayUntil.
//    - I2C is shared via a mutex to prevent bus contention between the
//      two sensor-reading tasks.
//    - Every Serial.print() in a hot loop is guarded with `if (Serial)` —
//      without a connected USB host, unread USB-CDC output fills its
//      buffer and further writes block forever, silently freezing
//      whichever task called it.
//
//  DIAGNOSTIC LOGGING: a separate flash file, /diag.log, records the reset
//  reason on every boot (crash vs. clean power-on vs. brownout) and traces
//  buzzer mutex/tone() calls step-by-step. Purely a debugging aid, not
//  part of the actual dataset — see diagLog() below.
// =====================================================================

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <NimBLEDevice.h>
#include <LittleFS.h>
#include "esp_system.h"
#include "MAX30105.h"
#include "classifier.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

// -----------------------------------------------------------------------
// CẤU HÌNH PHẦN CỨNG
// -----------------------------------------------------------------------
#define IMU_ADDR       0x68
#define IMU_HZ         25
#define PPG_HZ         100
#define WINDOW_SIZE    60
#define STRIDE_SIZE    10
#define ACTIVITY_GATE  150.0f    // bỏ qua window yên tĩnh (rest≈7, walk≈200–800)

// Live PPG contact — how long without a good IR sample before a row is
// marked "contact lost". Shared by the watchdog buzzer AND the per-row
// ppg_contact flag written to flash/BLE, so both agree on the same threshold.
#define PPG_CONTACT_TIMEOUT_MS 3000

// Queue depthspython
#define IMU_Q_DEPTH    5
#define PPG_Q_DEPTH    20        // PPG nhanh hơn IMU 4x nên buffer to hơn
#define OUT_Q_DEPTH    3

// Buzzer + session timer
#define BUZZER_PIN       3          // D2 on XIAO ESP32-S3
#define SESSION_MS       90000      // 90 seconds per activity (15s transition + 75s clean)
#define TRANSITION_MS    15000      // first 15s of each session — body settling, not clean data
#define PREP_MS          30000      // silent window before activity 1 — time to get into position
#define NUM_SESSIONS     5

// Onboard flash logging (LittleFS) — untethered recording, retrieved later over Serial
#define MAX_STORED_SESSIONS 20      // cap on how many participant runs can queue up before a dump

#define BLE_DEVICE_NAME  "WearableMonitor"
#define SVC_UUID         "AA10D001-0000-0000-0000-000000000001"
#define CHAR_STREAM_UUID "AA10D002-0000-0000-0000-000000000001"

// Kept off (2026-07-14 decision): audible cues now come from the laptop
// side (log_ble.py, via winsound) instead of this hardware buzzer — sidesteps
// the still-unresolved "no audible sound when untethered" issue inherited
// from the Option 4 branch entirely, rather than debugging it. Flip to 1
// only if testing tethered and want the hardware buzzer as well.
#define BUZZER_ENABLED 0

// Task stack sizes (bytes)
#define STACK_IMU    4096
#define STACK_PPG    4096
#define STACK_CLF    6144   // có windowBuffer[60] + beat detection state
#define STACK_BLE    8192   // NimBLE stack cần nhiều hơn
#define STACK_BUZZER 4096   // buzz()'s diagLog()/File::printf() calls need more than a
                             // bare-minimum stack — see firmware_main history for why

// -----------------------------------------------------------------------
// DATA STRUCTURES — chỉ dùng để truyền qua queue
// -----------------------------------------------------------------------
struct ImuSample {
    int16_t ax, ay, az;
};

struct PpgSample {
    long ir;
};

struct OutputResult {
    int   activity_class;  // 0 = normal, 1 = intense
    float bpm;
    float mean_mag;
    float std_mag;
    float peak_rel;
    float peak_max;
    bool  ppg_contact;     // live: good IR sample seen within PPG_CONTACT_TIMEOUT_MS?
};

// -----------------------------------------------------------------------
// QUEUE HANDLES VÀ MUTEX
// (handles là global nhưng KHÔNG chứa data — đây là pattern đúng)
// -----------------------------------------------------------------------
static QueueHandle_t     imu_queue;
static QueueHandle_t     ppg_queue;
static QueueHandle_t     output_queue;
static SemaphoreHandle_t i2c_mutex;
static SemaphoreHandle_t buzzer_mutex;   // task_session_buzzer + classifier watchdog both call tone() on BUZZER_PIN
static SemaphoreHandle_t diag_mutex;     // guards diagFile writes from multiple tasks — separate from buzzer_mutex
                                          // so logging inside a buzz() call never self-deadlocks

// Order matches log_ble.py's ACTIVITY_LABELS — ascending intensity (warm-up/cool-down safety)
static const char* ACTIVITY_LABELS[NUM_SESSIONS] = {
    "lying", "sitting", "standing", "walking", "running"
};

// Current activity index + when it started — written by task_session_buzzer,
// read by task_ble_streamer to label each row it writes to flash and BLE.
static volatile int           currentSessionIndex = 0;
static volatile unsigned long sessionStartMs       = 0;

// False during the PREP_MS window right after boot — task_ble_streamer
// discards windows until this flips true, so rows recorded before the
// participant is actually in position (still getting into place after
// hearing "recording starts") never make it into the dataset.
static volatile bool          protocolStarted      = false;

// True once all 5 activities are done for this boot — gates the on-demand
// dump trigger below (checkSerialDumpRequest()), so it can never fire
// mid-recording and delete/corrupt the still-open session file.
static volatile bool          protocolFinished     = false;

static File sessionFile;   // open for the whole run, closed when the 5th session ends
static File diagFile;      // open for the whole run — forensic log independent of USB/Serial

// BLE characteristic handle — ghi bởi setup, đọc bởi ble_streamer
static NimBLECharacteristic* pStreamChar = nullptr;
static NimBLEServer*         pBleServer  = nullptr;   // needed by the advertising watchdog below

// Forward declaration — defined near setupBLE() below, but called from
// task_classifier, which appears earlier in the file.
static void bleAdvertisingWatchdog();

// -----------------------------------------------------------------------
// SENSOR OBJECT (khởi tạo trong setup, dùng trong task_ppg_reader)
// -----------------------------------------------------------------------
static MAX30105 ppgSensor;
static bool     ppgOK = false;
static long     lastIR = 0;   // most recent raw IR reading, for live debug print

// -----------------------------------------------------------------------
// ONBOARD FLASH LOGGING (LittleFS)
// Each participant run gets its own /session_N.csv. Files persist across
// power cycles, so multiple participants can be recorded back-to-back
// fully untethered — retrieval happens later in one batch (see dump below).
// This is the guaranteed record — unaffected by BLE range/dropouts.
// -----------------------------------------------------------------------
static String nextSessionPath() {
    for (int n = 1; n <= MAX_STORED_SESSIONS; n++) {
        String path = "/session_" + String(n) + ".csv";
        if (!LittleFS.exists(path)) return path;
    }
    return "/session_overflow.csv";   // shouldn't happen at normal batch sizes
}

// -----------------------------------------------------------------------
// DIAGNOSTIC LOG (LittleFS) — /diag.log
// Logs to flash instead of Serial, which survives with no USB connection
// at all. Logged before AND after every risky operation (mutex take,
// tone() call) so that if something hangs, the last line in the log
// tells you exactly which step never completed.
// -----------------------------------------------------------------------
static const char* resetReasonStr(esp_reset_reason_t r) {
    switch (r) {
        case ESP_RST_POWERON:  return "POWERON";
        case ESP_RST_EXT:      return "EXT_RESET (reset button / DTR toggle)";
        case ESP_RST_SW:       return "SW_RESET";
        case ESP_RST_PANIC:    return "PANIC (crash)";
        case ESP_RST_INT_WDT:  return "INT_WDT";
        case ESP_RST_TASK_WDT: return "TASK_WDT (a task never yielded — likely hang)";
        case ESP_RST_WDT:      return "OTHER_WDT";
        case ESP_RST_BROWNOUT: return "BROWNOUT (power dipped below threshold)";
        default:               return "OTHER";
    }
}

static void diagLog(const char* msg) {
    if (!diagFile) return;
    // Bounded wait — a stuck diagnostic write must never become its own hang.
    if (xSemaphoreTake(diag_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        diagFile.printf("%lu,%s\n", millis(), msg);
        diagFile.flush();
        xSemaphoreGive(diag_mutex);
    }
}

// Prints every stored session file (and diag.log) to Serial, then deletes
// them. Triggered only when something is actually listening on boot (see
// waitForDumpRequest).
static void dumpAndClearSessions() {
    Serial.println("\n===== SESSION DUMP START =====");
    bool any = false;
    for (int n = 1; n <= MAX_STORED_SESSIONS; n++) {
        String path = "/session_" + String(n) + ".csv";
        if (!LittleFS.exists(path)) continue;
        any = true;

        File f = LittleFS.open(path, "r");
        Serial.printf("----- FILE: session_%d.csv -----\n", n);
        while (f.available()) Serial.write(f.read());
        Serial.printf("----- END: session_%d.csv -----\n", n);
        f.close();
        LittleFS.remove(path);
    }

    if (LittleFS.exists("/diag.log")) {
        any = true;
        if (diagFile) diagFile.close();

        File f = LittleFS.open("/diag.log", "r");
        Serial.println("----- FILE: diag.log -----");
        while (f.available()) Serial.write(f.read());
        Serial.println("----- END: diag.log -----");
        f.close();
        LittleFS.remove("/diag.log");
    }

    if (!any) Serial.println("(no stored sessions found)");
    Serial.println("===== SESSION DUMP END =====\n");
}

// -----------------------------------------------------------------------
// ON-DEMAND DUMP TRIGGER — lets retrieval happen any time after this run's
// protocol finishes, no reboot required at all. Added because reset access
// disappeared once the board went into its enclosure, and both software
// workarounds tried (DTR pulse, relying on a timed unplug/replug) proved
// unreliable on this board/OS combo — this sidesteps needing a reset in
// the first place instead of chasing those further.
//
// Gated on protocolFinished: dumping mid-recording would open/delete the
// SAME file task_ble_streamer still has open for writing — real corruption
// risk, not just an inconvenience. Called from task_classifier's loop,
// which already runs on a reliable ~40-60ms cycle regardless of session
// state (same task the BLE advertising watchdog piggybacks on).
// -----------------------------------------------------------------------
static void checkSerialDumpRequest() {
    if (!Serial || !Serial.available()) return;
    while (Serial.available()) Serial.read();   // drain whatever was sent

    if (!protocolFinished) {
        Serial.println("[BUSY] Recording still in progress — can't dump until "
                        "all 5 activities finish.");
        return;
    }
    dumpAndClearSessions();
    Serial.println("[READY] Power off any time, or send another character to dump again "
                    "(nothing left will just say so).");
}

// Gives you a window to request a dump right after reset — send any
// character in Serial Monitor within WAIT_MS. Times out silently (and
// harmlessly) when running untethered on battery, since nothing can send
// a character in that case.
static bool waitForDumpRequest(unsigned long waitMs) {
    Serial.printf("[BOOT] Send any character within %lus to dump + clear stored sessions...\n",
                  waitMs / 1000);
    unsigned long start = millis();
    while (millis() - start < waitMs) {
        if (Serial.available()) {
            while (Serial.available()) Serial.read();   // drain
            return true;
        }
        delay(50);
    }
    return false;
}

static void initMPU6050() {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x6B); Wire.write(0x00);   // wake up
    Wire.endTransmission(true);
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x1C); Wire.write(0x18);   // ±16g
    Wire.endTransmission(true);
}

// -----------------------------------------------------------------------
// TASK 5: SESSION BUZZER (also the protocol's master timer)
// Silent PREP_MS window first (time to get into position — no rows are
// recorded during this window, see protocolStarted), then 3 buzzes signal
// "activity 1 starts now". Advances currentSessionIndex/sessionStartMs
// through the 5 fixed activities, 90s each — every switch (including the
// final "all done") uses the same 3-buzz signal, so there's only one
// pattern to recognize by ear. buzz() is also reused by task_classifier's
// PPG-lost-contact watchdog below (single beep, different pitch).
// -----------------------------------------------------------------------
static void buzz(int count, int freq, int on_ms, int off_ms) {
#if !BUZZER_ENABLED
    return;   // buzzer disabled — see BUZZER_ENABLED at top of file
#endif
    char msg[64];
    for (int i = 0; i < count; i++) {
        snprintf(msg, sizeof(msg), "buzz: beep %d/%d freq=%d waiting for mutex", i + 1, count, freq);
        diagLog(msg);

        // Bounded wait — if tone() ever hangs while holding this mutex, we skip
        // this beep instead of freezing the whole session-progression loop forever.
        if (xSemaphoreTake(buzzer_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
            diagLog("buzz: mutex acquired, calling tone()");

            // Manual on/off instead of tone()'s duration param — avoids relying
            // on its internal auto-stop timer, which is the suspected hang point.
            tone(BUZZER_PIN, freq);
            vTaskDelay(pdMS_TO_TICKS(on_ms));
            noTone(BUZZER_PIN);
            diagLog("buzz: tone() cycle complete, releasing mutex");
            xSemaphoreGive(buzzer_mutex);
            vTaskDelay(pdMS_TO_TICKS(off_ms));
        } else {
            diagLog("buzz: mutex TIMEOUT after 500ms, skipping this beep");
            vTaskDelay(pdMS_TO_TICKS(on_ms + off_ms));
        }
    }
}

static void task_session_buzzer(void* arg) {
    vTaskDelay(pdMS_TO_TICKS(PREP_MS));   // silent — time to get into position
    buzz(3, 800, 200, 150);               // recording starts now (activity 1)
    protocolStarted = true;

    for (int session = 0; session < NUM_SESSIONS; session++) {
        currentSessionIndex = session;
        sessionStartMs      = millis();

        vTaskDelay(pdMS_TO_TICKS(SESSION_MS));

        buzz(3, 800, 200, 150);   // next activity, or "all done" on the last one — same signal
    }

    if (sessionFile) {
        sessionFile.flush();
        sessionFile.close();
    }
    protocolFinished = true;
    Serial.println("[SESSION] All 5 activities complete for this participant. "
                    "Send any character any time to dump + retrieve (no reset needed), "
                    "or power off / reset to start the next one.");

    vTaskDelete(nullptr);   // one participant per boot — done for this run
}

// -----------------------------------------------------------------------
// TASK 1: IMU READER
// Reads raw accelerometer from the MPU6050 at 25 Hz, pushes to imu_queue.
// -----------------------------------------------------------------------
static void task_imu_reader(void* arg) {
    TickType_t       xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod       = pdMS_TO_TICKS(1000 / IMU_HZ);  // 40 ms

    while (true) {
        vTaskDelayUntil(&xLastWakeTime, xPeriod);

        ImuSample sample;
        bool ok = false;

        xSemaphoreTake(i2c_mutex, portMAX_DELAY);
        Wire.beginTransmission(IMU_ADDR);
        Wire.write(0x3B);
        Wire.endTransmission(false);
        Wire.requestFrom(IMU_ADDR, 6);
        if (Wire.available() >= 6) {
            sample.ax = (Wire.read() << 8) | Wire.read();
            sample.ay = (Wire.read() << 8) | Wire.read();
            sample.az = (Wire.read() << 8) | Wire.read();
            ok = true;
        }
        xSemaphoreGive(i2c_mutex);

        if (ok) {
            // Nếu queue đầy → drop sample cũ nhất để ưu tiên sample mới
            if (xQueueSend(imu_queue, &sample, 0) == errQUEUE_FULL) {
                ImuSample discard;
                xQueueReceive(imu_queue, &discard, 0);
                xQueueSend(imu_queue, &sample, 0);
            }
        }
    }
}

// -----------------------------------------------------------------------
// TASK 2: PPG READER
// Đọc IR từ MAX30102 ở 100 Hz, đẩy vào ppg_queue
// -----------------------------------------------------------------------
static void task_ppg_reader(void* arg) {
    TickType_t       xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod       = pdMS_TO_TICKS(1000 / PPG_HZ);  // 10 ms

    while (true) {
        vTaskDelayUntil(&xLastWakeTime, xPeriod);

        if (!ppgOK) { vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        xSemaphoreTake(i2c_mutex, portMAX_DELAY);
        long ir = ppgSensor.getIR();
        xSemaphoreGive(i2c_mutex);
        lastIR = ir;

        if (ir > 3000) {   // wrist IR is weaker than fingertip — lower contact threshold
            PpgSample sample = { ir };
            xQueueSend(ppg_queue, &sample, 0);  // drop nếu đầy
        }
    }
}

// -----------------------------------------------------------------------
// TASK 3: CLASSIFIER
// Nhận IMU → sliding window → feature extraction → classifySignal()
// Drain PPG queue → beat detection → BPM
// Đẩy OutputResult vào output_queue
// -----------------------------------------------------------------------
static void task_classifier(void* arg) {
    // --- Sliding window (private, không ra ngoài task này) ---
    float windowBuffer[WINDOW_SIZE] = {};
    int   windowCount  = 0;
    float globalAccMag = 2048.0f;

    // --- PPG beat detection state ---
    float         dcOffset    = 0;
    float         maxInWave   = 0;
    float         currentBPM  = 75.0f;
    unsigned long lastBeatMs  = 0;

    // --- PPG watchdog ---
    unsigned long lastPpgMs   = millis();

    ImuSample    imuSample;
    PpgSample    ppgSample;
    OutputResult result = { 0, 75.0f };

    while (true) {
        // --- A. Nhận 1 IMU sample (blocking, timeout 60ms) ---
        if (xQueueReceive(imu_queue, &imuSample, pdMS_TO_TICKS(60)) == pdTRUE) {

            globalAccMag = sqrtf((float)imuSample.ax * imuSample.ax +
                                 (float)imuSample.ay * imuSample.ay +
                                 (float)imuSample.az * imuSample.az);
            windowBuffer[windowCount++] = globalAccMag;

            if (windowCount >= WINDOW_SIZE) {
                // Feature extraction
                float sumMag  = 0, peak_max = 0;
                for (int i = 0; i < WINDOW_SIZE; i++) {
                    sumMag += windowBuffer[i];
                    if (windowBuffer[i] > peak_max) peak_max = windowBuffer[i];
                }
                float meanMag = sumMag / WINDOW_SIZE;
                float sumVar  = 0;
                for (int i = 0; i < WINDOW_SIZE; i++)
                    sumVar += (windowBuffer[i] - meanMag) * (windowBuffer[i] - meanMag);
                float acc_std  = sqrtf(sumVar / WINDOW_SIZE);
                float peak_rel = (meanMag > 0.0f) ? (peak_max / meanMag) : 0.0f;

                // Guarded: without a connected USB host, unread USB-CDC output
                // eventually fills its buffer and further Serial writes block
                // forever — silently freezing this task when running untethered.
                if (Serial) Serial.printf(">acc_std:%.1f|mean:%.1f\n", acc_std, meanMag);
                result.activity_class = (acc_std >= ACTIVITY_GATE)
                                      ? classifySignal(peak_max, acc_std, peak_rel)
                                      : 0;
                result.bpm      = currentBPM;
                result.mean_mag = meanMag;
                result.std_mag  = acc_std;
                result.peak_rel = peak_rel;
                result.peak_max = peak_max;
                result.ppg_contact = (millis() - lastPpgMs) < PPG_CONTACT_TIMEOUT_MS;

                xQueueSend(output_queue, &result, 0);

                // Slide window
                for (int i = 0; i < WINDOW_SIZE - STRIDE_SIZE; i++)
                    windowBuffer[i] = windowBuffer[i + STRIDE_SIZE];
                windowCount = WINDOW_SIZE - STRIDE_SIZE;
            }
        }

        // --- B. Drain tất cả PPG samples đang chờ (non-blocking) ---
        bool gotPpg = false;
        while (xQueueReceive(ppg_queue, &ppgSample, 0) == pdTRUE) {
            gotPpg = true;
            // DC removal
            dcOffset = dcOffset * 0.99f + ppgSample.ir * 0.01f;
            float ac = ppgSample.ir - dcOffset;

            // Peak detection → BPM
            if (ac > 50.0f) {   // wrist AC amplitude ~3–5x smaller than fingertip
                if (ac > maxInWave) maxInWave = ac;
            } else if (ac < -15.0f && maxInWave > 50.0f) {
                unsigned long now      = millis();
                long          interval = now - lastBeatMs;
                if (lastBeatMs > 0 && interval > 375 && interval < 1200
                    && globalAccMag < 14000.0f) {
                    float rawBPM = 60000.0f / interval;
                    if (fabsf(rawBPM - currentBPM) < 35.0f || currentBPM == 75.0f)
                        currentBPM = currentBPM * 0.6f + rawBPM * 0.4f;
                }
                lastBeatMs = now;
                maxInWave  = 0;
            }
        }

        // --- C. PPG watchdog — buzz high pitch if sensor lost contact ---
        if (gotPpg) {
            lastPpgMs = millis();
        } else if (millis() - lastPpgMs > PPG_CONTACT_TIMEOUT_MS) {
            diagLog("watchdog: PPG lost contact, firing warning beep");
            buzz(1, 3000, 300, 0);        // single high-pitch warning beep
            lastPpgMs = millis();         // reset — warns again after 3s if still lost
        }

        // --- D. BLE advertising watchdog — see bleAdvertisingWatchdog() ---
        // Runs on this task's reliable ~40-60ms cycle, rate-limited to once
        // per 5s internally, independent of sensor/BLE state.
        bleAdvertisingWatchdog();

        // --- E. On-demand dump trigger — see checkSerialDumpRequest() ---
        checkSerialDumpRequest();
    }
}

// -----------------------------------------------------------------------
// TASK 4: BLE STREAMER
// Writes each result to flash FIRST (the guaranteed record, unaffected by
// BLE range/dropouts), then best-effort notifies the SAME row over BLE.
// The BLE payload now carries the full row (elapsed_ms/label/is_transition
// included) so the laptop-side script (log_ble.py) doesn't need its own
// clock or activity tracker — it just records whatever the device says,
// eliminating the dual-clock-drift risk the original BLE version had.
// -----------------------------------------------------------------------
static void task_ble_streamer(void* arg) {
    OutputResult result;

    while (true) {
        // Blocking — task chỉ thức khi có data
        if (xQueueReceive(output_queue, &result, portMAX_DELAY) == pdTRUE) {
            // Still in the silent PREP_MS window — participant isn't in
            // position yet, discard rather than log a bogus "lying" row.
            if (!protocolStarted) continue;

            bool isTransition = (millis() - sessionStartMs) < TRANSITION_MS;
            unsigned long nowMs = millis();

            // Flash log → the guaranteed record, independent of BLE entirely.
            // Always happens BEFORE the BLE notify below, so a BLE range
            // problem can never delay or skip the actual data record.
            if (sessionFile) {
                sessionFile.printf("%lu,%s,%d,%d,%.2f,%.1f,%.1f,%.2f,%.1f,%d\n",
                                    nowMs,
                                    ACTIVITY_LABELS[currentSessionIndex],
                                    (int)isTransition,
                                    result.activity_class,
                                    result.bpm,
                                    result.mean_mag,
                                    result.std_mag,
                                    result.peak_rel,
                                    result.peak_max,
                                    (int)result.ppg_contact);
                sessionFile.flush();
            }

            // BLE notify — best-effort live view, same row schema as flash.
            // setValue()/notify() don't block waiting for a connected client;
            // if nothing's subscribed or the client is out of range, this is
            // effectively a no-op (NimBLE handles that internally).
            if (pStreamChar != nullptr) {
                // Computed here (device is the single source of truth for
                // timing, same reasoning as elapsed_ms/label/is_transition
                // above) so log_ble.py never needs its own clock to predict
                // an upcoming switch — it just displays what the device says.
                long msIntoSession = (long)nowMs - (long)sessionStartMs;
                int  secondsLeft   = (int)((SESSION_MS - msIntoSession) / 1000);
                if (secondsLeft < 0) secondsLeft = 0;

                char payload[200];
                snprintf(payload, sizeof(payload),
                         "{\"elapsed_ms\":%lu,\"label\":\"%s\",\"is_transition\":%d,"
                         "\"activity_class\":%d,\"bpm\":%.2f,\"mean_mag\":%.1f,"
                         "\"std_mag\":%.1f,\"peak_rel\":%.2f,\"peak_max\":%.1f,"
                         "\"ppg_contact\":%d,\"seconds_left\":%d}",
                         nowMs, ACTIVITY_LABELS[currentSessionIndex], (int)isTransition,
                         result.activity_class, result.bpm, result.mean_mag,
                         result.std_mag, result.peak_rel, result.peak_max,
                         (int)result.ppg_contact, secondsLeft);
                pStreamChar->setValue((uint8_t*)payload, strlen(payload));
                pStreamChar->notify();
            }

            // Serial stream cho Serial Plotter / debug — guarded, see note above
            if (Serial) {
                Serial.printf(">activity:%d|bpm:%.2f|heap:%lu|ppgOK:%d|ir:%ld\n",
                              result.activity_class,
                              result.bpm,
                              (unsigned long)ESP.getFreeHeap(),
                              (int)ppgOK,
                              lastIR);
            }
        }
    }
}

// -----------------------------------------------------------------------
// BLE CONNECTION LOGGING
// Root-cause fix (2026-07-10): NimBLE stops advertising once a central
// connects, and does NOT resume automatically on disconnect — without
// explicitly restarting it here, the device becomes permanently
// undiscoverable after the very first BLE disconnect, no matter how many
// times the laptop re-scans. This is very likely why reconnection was
// failing 100% of the time rather than intermittently. Also logs to
// diag.log (and Serial, if connected) so a future dropout can be
// confirmed as a real range/RF event rather than guessed at.
// -----------------------------------------------------------------------
class WearableServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* pServer) {
        diagLog("BLE: client connected");
        if (Serial) Serial.println("[BLE] Client connected.");
    }
    void onDisconnect(NimBLEServer* pServer) {
        diagLog("BLE: client disconnected, restarting advertising");
        if (Serial) Serial.println("[BLE] Client disconnected — restarting advertising.");
        // startAdvertising() returns bool — checking it, not discarding it,
        // is the whole point: if THIS call silently fails too, we'd be back
        // to square one with no way to tell. Log either outcome explicitly.
        bool ok = NimBLEDevice::startAdvertising();
        diagLog(ok ? "BLE: advertising restarted OK"
                   : "BLE: advertising restart FAILED — device will stay undiscoverable "
                     "until the periodic watchdog catches it (see task_classifier)");
    }
};

// -----------------------------------------------------------------------
// SETUP BLE
// -----------------------------------------------------------------------
static void setupBLE() {
    NimBLEDevice::init(BLE_DEVICE_NAME);

    // Max TX power — was left at NimBLE's default. Cheap to try, but this
    // is a real-RF (body attenuation / antenna orientation) symptom per
    // earlier diagnosis, not a software config issue, so don't expect this
    // alone to fix drops that happen standing right next to the laptop.
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);

    pBleServer = NimBLEDevice::createServer();
    static WearableServerCallbacks serverCallbacks;
    pBleServer->setCallbacks(&serverCallbacks);

    NimBLEService* pService = pBleServer->createService(SVC_UUID);

    pStreamChar = pService->createCharacteristic(
        CHAR_STREAM_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    pService->start();

    NimBLEAdvertising* pAdv = NimBLEDevice::getAdvertising();
    pAdv->addServiceUUID(SVC_UUID);
    pAdv->setScanResponse(true);
    bool advOk = pAdv->start();   // checked, not discarded — see WearableServerCallbacks note

    Serial.println("[BLE] Advertising: " BLE_DEVICE_NAME);
    {
        char msg[64];
        snprintf(msg, sizeof(msg), "BLE: initial advertising start %s", advOk ? "OK" : "FAILED");
        diagLog(msg);
    }
}

// -----------------------------------------------------------------------
// BLE ADVERTISING WATCHDOG
// Defense in depth beyond the onDisconnect() restart above: periodically
// (every ~5s, checked from task_classifier so it runs on a reliable cycle
// independent of BLE/sensor state) confirms the device is either connected
// or actively advertising. If it's neither — e.g. the onDisconnect restart
// itself silently failed — this catches it and tries again, rather than
// leaving the device permanently invisible for the rest of the session.
// -----------------------------------------------------------------------
static void bleAdvertisingWatchdog() {
    static unsigned long lastCheckMs = 0;
    unsigned long nowMs = millis();
    if (nowMs - lastCheckMs < 5000) return;
    lastCheckMs = nowMs;

    if (!pBleServer) return;   // BLE not initialized yet
    bool connected    = pBleServer->getConnectedCount() > 0;
    bool advertising  = NimBLEDevice::getAdvertising()->isAdvertising();

    if (!connected && !advertising) {
        diagLog("BLE watchdog: not connected AND not advertising — forcing restart");
        bool ok = NimBLEDevice::startAdvertising();
        diagLog(ok ? "BLE watchdog: advertising restarted OK"
                   : "BLE watchdog: restart FAILED again — will retry in 5s");
    }
}

// -----------------------------------------------------------------------
// SETUP — khởi tạo hardware, tạo queues, tạo tasks
// -----------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n=======================================================");
    Serial.println("   WEARABLE MONITOR — FreeRTOS (BLE branch)");
    Serial.printf( "   CPU: %d MHz  |  Free heap: %.1f KB\n",
                   ESP.getCpuFreqMHz(), ESP.getFreeHeap() / 1024.0f);
    Serial.println("=======================================================");
    Serial.flush();

    if (!LittleFS.begin(true)) {
        Serial.println("[FATAL] LittleFS mount failed — flash logging unavailable.");
        Serial.flush();
    }

    // diag_mutex + diagFile must exist before anything can call diagLog() —
    // create/open them first, and log the reset reason for THIS boot before
    // doing anything else, so every boot (including ones that turn out to
    // crash later) leaves a record of how it started.
    diag_mutex = xSemaphoreCreateMutex();
    diagFile   = LittleFS.open("/diag.log", "a");
    {
        char msg[64];
        snprintf(msg, sizeof(msg), "BOOT reset_reason=%s heap=%lu",
                 resetReasonStr(esp_reset_reason()), (unsigned long)ESP.getFreeHeap());
        diagLog(msg);
    }

    // Retrieval mode: if someone sends a character within the window, dump
    // + clear stored sessions and halt. Otherwise (untethered on battery,
    // nothing to send a character) this times out harmlessly and recording
    // proceeds normally below.
    if (waitForDumpRequest(3000)) {
        dumpAndClearSessions();
        Serial.println("[BOOT] Reset without sending a character to start a new recording.");
        while (true) { delay(1000); }
    }

    String sessionPath = nextSessionPath();
    sessionFile = LittleFS.open(sessionPath, "w");
    if (sessionFile) {
        sessionFile.println("elapsed_ms,label,is_transition,activity_class,bpm,mean_mag,std_mag,peak_rel,peak_max,ppg_contact");
        Serial.printf("[FS] Recording this run to %s\n", sessionPath.c_str());
    } else {
        Serial.println("[FATAL] Could not open a session file — recording will not be saved to flash!");
    }
    Serial.flush();

    // Hardware
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);

    Wire.begin(5, 6);
    Wire.setClock(100000);
    initMPU6050();
    ppgOK = ppgSensor.begin(Wire, I2C_SPEED_STANDARD);
    if (!ppgOK) {
        Serial.println("[WARN] MAX30102 không tìm thấy — chạy không có PPG (BPM=0).");
    } else {
        ppgSensor.setup(30, 1, 2, 100, 411, 4096);
    }
    Serial.println("[OK]  Sensors initialized.");
    Serial.flush();

    // Tạo mutex + queues
    i2c_mutex    = xSemaphoreCreateMutex();
    buzzer_mutex = xSemaphoreCreateMutex();
    imu_queue    = xQueueCreate(IMU_Q_DEPTH, sizeof(ImuSample));
    ppg_queue    = xQueueCreate(PPG_Q_DEPTH, sizeof(PpgSample));
    output_queue = xQueueCreate(OUT_Q_DEPTH,  sizeof(OutputResult));
    Serial.println("[OK]  Queues created.");
    Serial.flush();

    setupBLE();
    Serial.flush();

    // Tạo 5 tasks
    //                         name           stack       arg  prio  handle
    xTaskCreate(task_imu_reader,    "imu_reader",    STACK_IMU,    nullptr, 3, nullptr);
    xTaskCreate(task_ppg_reader,    "ppg_reader",    STACK_PPG,    nullptr, 3, nullptr);
    xTaskCreate(task_classifier,    "classifier",    STACK_CLF,    nullptr, 2, nullptr);
    xTaskCreate(task_ble_streamer,  "ble_streamer",  STACK_BLE,    nullptr, 1, nullptr);
    xTaskCreate(task_session_buzzer,"session_buzzer",STACK_BUZZER, nullptr, 1, nullptr);

    Serial.println("[OK]  5 FreeRTOS tasks created.");
    Serial.printf( "[RAM] Free heap after init: %.1f KB\n\n",
                   ESP.getFreeHeap() / 1024.0f);
    Serial.flush();
}

// -----------------------------------------------------------------------
// LOOP — không dùng trong FreeRTOS architecture
// Arduino loop() vẫn chạy như một task ưu tiên thấp — block nó lại
// -----------------------------------------------------------------------
void loop() {
    vTaskDelay(portMAX_DELAY);
}

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

// Second MAX30102 (fingertip, ground-truth channel for the LMS/RLS/Wiener
// research track — added 2026-07-16). MAX30102 has a FIXED I2C address
// (0x57, no ADDR pin), so it cannot share the wrist sensor's bus — it gets
// its own bus on Wire1, separate pins, no contention with i2c_mutex at all.
#define PPG2_SDA_PIN   3   // D2
#define PPG2_SCL_PIN   2   // D1
#define WINDOW_SIZE    60
#define STRIDE_SIZE    10
#define ACTIVITY_GATE  150.0f    // bỏ qua window yên tĩnh (rest≈7, walk≈200–800)

// Live PPG contact — how long without a good IR sample before a row is
// marked "contact lost". Shared by the watchdog buzzer AND the per-row
// ppg_contact flag written to flash/BLE, so both agree on the same threshold.
#define PPG_CONTACT_TIMEOUT_MS 3000

// Beat-detection thresholds, as a FRACTION of a rolling estimate of recent
// peak AC amplitude, instead of fixed constants. Fixed thresholds (found
// 2026-07-14, via check_dataset_readiness.py against real collected data)
// caused BPM to freeze for a long time in two different situations: (1)
// motion artifact temporarily inflating/collapsing the true AC amplitude,
// and (2) sitting very still, where the wrist's real AC swing is smaller
// than the old fixed 50/-15 constants could ever cross. Scaling to recent
// amplitude adapts to both. Min/max clamps stop the threshold collapsing
// to near-zero noise or ballooning from one big motion spike.
#define PPG_AC_ONSET_FRAC    0.30f
#define PPG_AC_RESET_FRAC    0.15f
#define PPG_AC_ONSET_MIN     15.0f
#define PPG_AC_ONSET_MAX     200.0f
#define PPG_AC_RESET_MIN     5.0f
#define PPG_AC_RESET_MAX     80.0f

// If no beat has been ACCEPTED (not just "a wave came and went") within
// this long, the current bpm value is stale — it's still whatever the EMA
// last computed, not a fresh reading. Exposed as bpm_fresh so bad stretches
// can be filtered out of the dataset instead of silently trusted.
#define BPM_STALE_TIMEOUT_MS 4000

// Queue depthspython
#define IMU_Q_DEPTH    5
#define PPG_Q_DEPTH    20        // PPG nhanh hơn IMU 4x nên buffer to hơn
#define OUT_Q_DEPTH    3

// Buzzer + session timer
#define BUZZER_PIN       4          // D3 on XIAO ESP32-S3 — moved off D2 (GPIO3) to make room for PPG2_SCL_PIN
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
// Was 8192 (~4.2KB of arrays, ~4KB margin) before RAW_PPG2 was added. The
// three static buffers now total ~7.6KB (100*12 + 400*8 + 400*8), which
// would leave only ~600B of margin at 8192 — bumped to keep a safe margin.
#define STACK_RAW    12288  // holds RAW_IMU_Q_DEPTH + RAW_PPG_Q_DEPTH + RAW_PPG2_Q_DEPTH sample arrays
#define STACK_PPG2   4096   // task_ppg2_reader — mirrors STACK_PPG

// -----------------------------------------------------------------------
// RAW WAVEFORM CAPTURE (2026-07-15) — supplementary to the feature dataset
// above, added for the LMS/RLS/Wiener comparison research track: you can't
// run a candidate filtering algorithm on an already-computed BPM number,
// only on the raw signal. NOT required for activity classification or the
// existing validity checks — session_N.csv remains the guaranteed record.
//
// Deliberately a SEPARATE task + SEPARATE queues from task_imu_reader/
// task_ppg_reader (rather than writing to flash inline in those tasks) —
// a flash write is slow enough that doing it inline would risk delaying
// the 25Hz/100Hz sensor read cadence those tasks must keep up. This task
// only drains queues and writes; it never touches I2C.
//
// Generous queue depths (~4s buffer each) so a momentary flash-write stall
// doesn't drop samples silently — samples are only discarded if the writer
// falls behind by more than that. RAW_FLUSH_MS is intentionally SHORT
// (not batched into large infrequent writes) — caps how much raw data is
// lost if the board loses power mid-run to that same short window, at the
// cost of a few more flash writes/sec than a larger-batch design would need.
// -----------------------------------------------------------------------
#define RAW_IMU_Q_DEPTH 100   // ~4s at 25Hz
#define RAW_PPG_Q_DEPTH 400   // ~4s at 100Hz
#define RAW_PPG2_Q_DEPTH 400  // fingertip channel, same depth/rate as wrist PPG
#define RAW_FLUSH_MS    500   // how often the writer task drains+flushes

// -----------------------------------------------------------------------
// DATA STRUCTURES — chỉ dùng để truyền qua queue
// -----------------------------------------------------------------------
struct ImuSample {
    int16_t ax, ay, az;
};

struct PpgSample {
    long ir;
};

// Raw samples for the waveform-capture task — carry their own timestamp
// since they're written to a file separate from session_N.csv; cross-
// reference against that file's label/is_transition by elapsed_ms range
// rather than duplicating the label string on every raw sample.
struct RawImuSample {
    unsigned long ms;
    int16_t ax, ay, az;
};

struct RawPpgSample {
    unsigned long ms;
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
    bool  bpm_fresh;       // live: a beat was actually ACCEPTED within BPM_STALE_TIMEOUT_MS?
};

// -----------------------------------------------------------------------
// QUEUE HANDLES VÀ MUTEX
// (handles là global nhưng KHÔNG chứa data — đây là pattern đúng)
// -----------------------------------------------------------------------
static QueueHandle_t     imu_queue;
static QueueHandle_t     ppg_queue;
static QueueHandle_t     output_queue;
static QueueHandle_t     raw_imu_queue;   // task_imu_reader -> task_raw_writer
static QueueHandle_t     raw_ppg_queue;   // task_ppg_reader -> task_raw_writer
static QueueHandle_t     raw_ppg2_queue;  // task_ppg2_reader (fingertip) -> task_raw_writer
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
static File rawPpgFile;    // /raw_ppg_N.csv — paired with sessionFile, see task_raw_writer
static File rawAccelFile;  // /raw_accel_N.csv — paired with sessionFile, see task_raw_writer
static File rawPpg2File;   // /raw_ppg2_N.csv — fingertip ground-truth channel, same pairing

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

// Second sensor — fingertip, on its own I2C bus (Wire1). Read only by
// task_ppg2_reader, so unlike ppgSensor it never needs i2c_mutex.
static MAX30105 ppgSensor2;
static bool     ppgOK2 = false;
static long     lastIR2 = 0;

// -----------------------------------------------------------------------
// ONBOARD FLASH LOGGING (LittleFS)
// Each participant run gets its own /session_N.csv. Files persist across
// power cycles, so multiple participants can be recorded back-to-back
// fully untethered — retrieval happens later in one batch (see dump below).
// This is the guaranteed record — unaffected by BLE range/dropouts.
// -----------------------------------------------------------------------
// Returns the next free participant number, or -1 if all MAX_STORED_SESSIONS
// slots are taken. Used to derive session_N.csv AND its paired raw_ppg_N.csv/
// raw_accel_N.csv from the same N, so retrieval/dump can always find all
// three files for a given run together.
static int nextSessionNumber() {
    for (int n = 1; n <= MAX_STORED_SESSIONS; n++) {
        String path = "/session_" + String(n) + ".csv";
        if (!LittleFS.exists(path)) return n;
    }
    return -1;   // shouldn't happen at normal batch sizes
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
// Prints then removes 1 file if it exists — shared by dumpAndClearSessions()
// for session_N.csv and its paired raw_ppg_N.csv/raw_accel_N.csv.
static void dumpAndRemoveFile(const String& path, const char* label) {
    if (!LittleFS.exists(path)) return;
    File f = LittleFS.open(path, "r");
    Serial.printf("----- FILE: %s -----\n", label);
    while (f.available()) Serial.write(f.read());
    Serial.printf("----- END: %s -----\n", label);
    f.close();
    LittleFS.remove(path);
}

static void dumpAndClearSessions() {
    Serial.println("\n===== SESSION DUMP START =====");
    bool any = false;
    for (int n = 1; n <= MAX_STORED_SESSIONS; n++) {
        String sessionPath = "/session_" + String(n) + ".csv";
        if (!LittleFS.exists(sessionPath)) continue;   // session file is the "this N exists" marker
        any = true;

        char label[32];
        snprintf(label, sizeof(label), "session_%d.csv", n);
        dumpAndRemoveFile(sessionPath, label);

        // Raw waveform files, if this run had them (older runs won't).
        snprintf(label, sizeof(label), "raw_ppg_%d.csv", n);
        dumpAndRemoveFile("/raw_ppg_" + String(n) + ".csv", label);
        snprintf(label, sizeof(label), "raw_accel_%d.csv", n);
        dumpAndRemoveFile("/raw_accel_" + String(n) + ".csv", label);
        snprintf(label, sizeof(label), "raw_ppg2_%d.csv", n);
        dumpAndRemoveFile("/raw_ppg2_" + String(n) + ".csv", label);
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
    // Closing these makes task_raw_writer's `if (rawAccelFile)`/`if (rawPpgFile)`
    // checks evaluate false from here on — same safe pattern as sessionFile
    // above, so a queued-but-not-yet-flushed batch just gets silently
    // skipped rather than written to a closed file.
    if (rawAccelFile) { rawAccelFile.flush(); rawAccelFile.close(); }
    if (rawPpgFile)   { rawPpgFile.flush();   rawPpgFile.close();   }
    if (rawPpg2File)  { rawPpg2File.flush();  rawPpg2File.close();  }
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

            // Raw waveform capture — only once the participant is actually
            // in position (matches the same gate used for the feature CSV).
            // Best-effort: if raw_imu_queue is full, drop rather than block
            // this task's 25Hz cadence.
            if (protocolStarted) {
                RawImuSample rawSample = { millis(), sample.ax, sample.ay, sample.az };
                xQueueSend(raw_imu_queue, &rawSample, 0);
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

        // Raw waveform capture — unconditional (not gated by the ir>3000
        // contact threshold above), so contact-loss transitions are visible
        // in the raw signal too. Same protocolStarted gate as the IMU side.
        if (protocolStarted) {
            RawPpgSample rawSample = { millis(), ir };
            xQueueSend(raw_ppg_queue, &rawSample, 0);
        }
    }
}

// -----------------------------------------------------------------------
// TASK: PPG2 READER (fingertip, added 2026-07-16)
// Reads IR from the second MAX30102 over its own bus (Wire1) at 100 Hz —
// raw capture ONLY, same millis() clock as raw_ppg_queue so the two
// channels line up sample-for-sample later in analysis. Deliberately does
// NOT feed ppg_queue/BPM detection or session_N.csv: this sensor's whole
// job is being the ground-truth reference for the LMS filter comparison
// (see experiments/fingertip/ in FIRMWARE_OVERVIEW.md), not a second live
// BPM to fuse into the existing feature pipeline. No i2c_mutex needed —
// Wire1 is touched by no other task.
// -----------------------------------------------------------------------
static void task_ppg2_reader(void* arg) {
    TickType_t       xLastWakeTime = xTaskGetTickCount();
    const TickType_t xPeriod       = pdMS_TO_TICKS(1000 / PPG_HZ);  // 10 ms

    while (true) {
        vTaskDelayUntil(&xLastWakeTime, xPeriod);

        if (!ppgOK2) { vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        long ir = ppgSensor2.getIR();
        lastIR2 = ir;

        if (protocolStarted) {
            RawPpgSample rawSample = { millis(), ir };
            xQueueSend(raw_ppg2_queue, &rawSample, 0);
        }
    }
}

// -----------------------------------------------------------------------
// TASK: RAW WAVEFORM WRITER (added 2026-07-15 for the LMS/RLS/Wiener
// research track — see the RAW_IMU_Q_DEPTH comment near the top of the
// file for the full rationale). Drains raw_imu_queue/raw_ppg_queue and
// appends to /raw_accel_N.csv + /raw_ppg_N.csv every RAW_FLUSH_MS.
//
// Deliberately its own task: the only thing this task does is queue
// draining + flash writes, so a slow flush can never delay the 25Hz/100Hz
// sensor reads happening in task_imu_reader/task_ppg_reader. Never touches
// I2C, so it can't contend with i2c_mutex either.
//
// Rabbit-hole guard: if this task ever causes the FEATURE pipeline
// (session_N.csv / ppg_contact / bpm_fresh — all validated working
// 2026-07-14) to regress — missed IMU/PPG samples, task watchdog resets,
// visibly wrong bpm/std_mag — stop and disable raw capture (comment out
// its xTaskCreate call and the two raw_*_queue sends above) rather than
// debugging it further under time pressure. The feature pipeline is the
// guaranteed dataset; raw capture is supplementary and expendable.
// -----------------------------------------------------------------------
static void task_raw_writer(void* arg) {
    static RawImuSample imuBuf[RAW_IMU_Q_DEPTH];
    static RawPpgSample ppgBuf[RAW_PPG_Q_DEPTH];
    static RawPpgSample ppg2Buf[RAW_PPG2_Q_DEPTH];

    while (true) {
        vTaskDelay(pdMS_TO_TICKS(RAW_FLUSH_MS));
        if (!protocolStarted) continue;

        int imuCount = 0;
        while (imuCount < RAW_IMU_Q_DEPTH &&
               xQueueReceive(raw_imu_queue, &imuBuf[imuCount], 0) == pdTRUE) {
            imuCount++;
        }
        if (imuCount > 0 && rawAccelFile) {
            for (int i = 0; i < imuCount; i++) {
                rawAccelFile.printf("%lu,%d,%d,%d\n", imuBuf[i].ms,
                                     imuBuf[i].ax, imuBuf[i].ay, imuBuf[i].az);
            }
            rawAccelFile.flush();
        }

        int ppgCount = 0;
        while (ppgCount < RAW_PPG_Q_DEPTH &&
               xQueueReceive(raw_ppg_queue, &ppgBuf[ppgCount], 0) == pdTRUE) {
            ppgCount++;
        }
        if (ppgCount > 0 && rawPpgFile) {
            for (int i = 0; i < ppgCount; i++) {
                rawPpgFile.printf("%lu,%ld\n", ppgBuf[i].ms, ppgBuf[i].ir);
            }
            rawPpgFile.flush();
        }

        int ppg2Count = 0;
        while (ppg2Count < RAW_PPG2_Q_DEPTH &&
               xQueueReceive(raw_ppg2_queue, &ppg2Buf[ppg2Count], 0) == pdTRUE) {
            ppg2Count++;
        }
        if (ppg2Count > 0 && rawPpg2File) {
            for (int i = 0; i < ppg2Count; i++) {
                rawPpg2File.printf("%lu,%ld\n", ppg2Buf[i].ms, ppg2Buf[i].ir);
            }
            rawPpg2File.flush();
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
    float         acAmplitudeEstimate = 100.0f;  // rolling estimate of recent peak AC swing
    unsigned long lastAcceptedBeatMs  = 0;       // last beat that actually updated currentBPM

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
                result.bpm_fresh   = (millis() - lastAcceptedBeatMs) < BPM_STALE_TIMEOUT_MS;

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

            // Peak detection → BPM. Thresholds scale with acAmplitudeEstimate
            // (recent peak AC swing) instead of fixed constants — see
            // PPG_AC_*_FRAC comment near the top of the file for why.
            float onsetThreshold = constrain(acAmplitudeEstimate * PPG_AC_ONSET_FRAC,
                                              PPG_AC_ONSET_MIN, PPG_AC_ONSET_MAX);
            float resetThreshold = -constrain(acAmplitudeEstimate * PPG_AC_RESET_FRAC,
                                               PPG_AC_RESET_MIN, PPG_AC_RESET_MAX);

            if (ac > onsetThreshold) {
                if (ac > maxInWave) maxInWave = ac;
            } else if (ac < resetThreshold && maxInWave > onsetThreshold) {
                unsigned long now      = millis();
                long          interval = now - lastBeatMs;
                if (lastBeatMs > 0 && interval > 375 && interval < 1200
                    && globalAccMag < 14000.0f) {
                    float rawBPM = 60000.0f / interval;
                    if (fabsf(rawBPM - currentBPM) < 35.0f || currentBPM == 75.0f) {
                        currentBPM = currentBPM * 0.6f + rawBPM * 0.4f;
                        lastAcceptedBeatMs = now;   // only a truly accepted beat counts as "fresh"
                    }
                }
                // Adapt to the wave that just completed, whether or not it was
                // accepted as a beat — this is what lets the threshold track
                // a genuinely weak-but-real signal at rest.
                acAmplitudeEstimate = acAmplitudeEstimate * 0.9f + maxInWave * 0.1f;
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
                sessionFile.printf("%lu,%s,%d,%d,%.2f,%.1f,%.1f,%.2f,%.1f,%d,%d\n",
                                    nowMs,
                                    ACTIVITY_LABELS[currentSessionIndex],
                                    (int)isTransition,
                                    result.activity_class,
                                    result.bpm,
                                    result.mean_mag,
                                    result.std_mag,
                                    result.peak_rel,
                                    result.peak_max,
                                    (int)result.ppg_contact,
                                    (int)result.bpm_fresh);
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

                char payload[220];
                snprintf(payload, sizeof(payload),
                         "{\"elapsed_ms\":%lu,\"label\":\"%s\",\"is_transition\":%d,"
                         "\"activity_class\":%d,\"bpm\":%.2f,\"mean_mag\":%.1f,"
                         "\"std_mag\":%.1f,\"peak_rel\":%.2f,\"peak_max\":%.1f,"
                         "\"ppg_contact\":%d,\"bpm_fresh\":%d,\"seconds_left\":%d}",
                         nowMs, ACTIVITY_LABELS[currentSessionIndex], (int)isTransition,
                         result.activity_class, result.bpm, result.mean_mag,
                         result.std_mag, result.peak_rel, result.peak_max,
                         (int)result.ppg_contact, (int)result.bpm_fresh, secondsLeft);
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

    int sessionNum = nextSessionNumber();
    String sessionPath  = (sessionNum > 0) ? "/session_" + String(sessionNum) + ".csv"
                                            : "/session_overflow.csv";
    String rawPpgPath   = (sessionNum > 0) ? "/raw_ppg_" + String(sessionNum) + ".csv"
                                            : "/raw_ppg_overflow.csv";
    String rawAccelPath = (sessionNum > 0) ? "/raw_accel_" + String(sessionNum) + ".csv"
                                            : "/raw_accel_overflow.csv";
    String rawPpg2Path  = (sessionNum > 0) ? "/raw_ppg2_" + String(sessionNum) + ".csv"
                                            : "/raw_ppg2_overflow.csv";

    sessionFile = LittleFS.open(sessionPath, "w");
    if (sessionFile) {
        sessionFile.println("elapsed_ms,label,is_transition,activity_class,bpm,mean_mag,std_mag,peak_rel,peak_max,ppg_contact,bpm_fresh");
        Serial.printf("[FS] Recording this run to %s\n", sessionPath.c_str());
    } else {
        Serial.println("[FATAL] Could not open a session file — recording will not be saved to flash!");
    }

    // Raw waveform files — supplementary, not the guaranteed record. A
    // failure here only loses the raw capture, never the feature dataset
    // above, so it's a [WARN] not a [FATAL].
    rawPpgFile = LittleFS.open(rawPpgPath, "w");
    if (rawPpgFile) rawPpgFile.println("elapsed_ms,ir");
    else Serial.println("[WARN] Could not open raw PPG file — raw capture unavailable this run.");

    rawAccelFile = LittleFS.open(rawAccelPath, "w");
    if (rawAccelFile) rawAccelFile.println("elapsed_ms,ax,ay,az");
    else Serial.println("[WARN] Could not open raw accel file — raw capture unavailable this run.");

    rawPpg2File = LittleFS.open(rawPpg2Path, "w");
    if (rawPpg2File) rawPpg2File.println("elapsed_ms,ir");
    else Serial.println("[WARN] Could not open raw fingertip PPG file — ground-truth capture unavailable this run.");

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
        // LED brightness bumped 30 -> 55 (2026-07-14 experiment): raises raw
        // PPG AC amplitude at the sensor itself, complementing the adaptive
        // threshold above for the "sitting still, signal too weak" case —
        // that case can't be fixed by threshold tuning alone if the real
        // signal is this close to the noise floor. A/B against 30 if BPM
        // quality doesn't visibly improve; safe range for this library is 0-255.
        ppgSensor.setup(55, 1, 2, 100, 411, 4096);
    }

    // Second sensor — fingertip, own bus (Wire1), own pins (see PPG2_SDA_PIN/
    // PPG2_SCL_PIN). Fingertip signal is naturally much stronger than wrist,
    // so brightness may need to come DOWN from 55 if this saturates — check
    // raw_ppg2_N.csv after the first real run before assuming this value is fine.
    Wire1.begin(PPG2_SDA_PIN, PPG2_SCL_PIN);
    Wire1.setClock(100000);
    ppgOK2 = ppgSensor2.begin(Wire1, I2C_SPEED_STANDARD);
    if (!ppgOK2) {
        Serial.println("[WARN] Fingertip MAX30102 (Wire1) không tìm thấy — chạy không có ground-truth channel.");
    } else {
        ppgSensor2.setup(55, 1, 2, 100, 411, 4096);
    }

    Serial.println("[OK]  Sensors initialized.");
    Serial.flush();

    // Tạo mutex + queues
    i2c_mutex     = xSemaphoreCreateMutex();
    buzzer_mutex  = xSemaphoreCreateMutex();
    imu_queue     = xQueueCreate(IMU_Q_DEPTH, sizeof(ImuSample));
    ppg_queue     = xQueueCreate(PPG_Q_DEPTH, sizeof(PpgSample));
    output_queue  = xQueueCreate(OUT_Q_DEPTH,  sizeof(OutputResult));
    raw_imu_queue = xQueueCreate(RAW_IMU_Q_DEPTH, sizeof(RawImuSample));
    raw_ppg_queue = xQueueCreate(RAW_PPG_Q_DEPTH, sizeof(RawPpgSample));
    raw_ppg2_queue = xQueueCreate(RAW_PPG2_Q_DEPTH, sizeof(RawPpgSample));
    Serial.println("[OK]  Queues created.");
    Serial.flush();

    setupBLE();
    Serial.flush();

    // Tạo 6 tasks
    //                         name           stack       arg  prio  handle
    xTaskCreate(task_imu_reader,    "imu_reader",    STACK_IMU,    nullptr, 3, nullptr);
    xTaskCreate(task_ppg_reader,    "ppg_reader",    STACK_PPG,    nullptr, 3, nullptr);
    xTaskCreate(task_ppg2_reader,   "ppg2_reader",   STACK_PPG2,   nullptr, 3, nullptr);
    xTaskCreate(task_classifier,    "classifier",    STACK_CLF,    nullptr, 2, nullptr);
    xTaskCreate(task_ble_streamer,  "ble_streamer",  STACK_BLE,    nullptr, 1, nullptr);
    xTaskCreate(task_session_buzzer,"session_buzzer",STACK_BUZZER, nullptr, 1, nullptr);
    xTaskCreate(task_raw_writer,    "raw_writer",    STACK_RAW,    nullptr, 1, nullptr);

    Serial.println("[OK]  7 FreeRTOS tasks created.");
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

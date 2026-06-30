// =====================================================================
//  WEARABLE ACTIVITY MONITOR — FreeRTOS Architecture v1
//  Week 2 milestone: 4 tasks + queues + BLE advertising
//
//  Kiến trúc:
//   task_imu_reader  (priority 3) → imu_queue    → 25 Hz
//    task_ppg_reader  (priority 3) → ppg_queue    → 100 Hz
//    task_classifier  (priority 2) → output_queue → driven by IMU
//    task_ble_streamer(priority 1) → BLE notify   → driven by output
//
//  Rules:
//    - Không có global variable chứa DATA giữa các task
//    - Tất cả data đi qua queue
//    - Không có delay() — chỉ dùng vTaskDelay / vTaskDelayUntil
//    - I2C dùng chung mutex để tránh xung đột
// =====================================================================

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <NimBLEDevice.h>
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

// Queue depths
#define IMU_Q_DEPTH    5
#define PPG_Q_DEPTH    20        // PPG nhanh hơn IMU 4x nên buffer to hơn
#define OUT_Q_DEPTH    3

// BLE
// Buzzer + session timer
#define BUZZER_PIN       3          // D2 on XIAO ESP32-S3
#define SESSION_MS       60000      // 60 seconds per activity
#define NUM_SESSIONS     5

#define BLE_DEVICE_NAME  "WearableMonitor"
#define SVC_UUID         "AA10D001-0000-0000-0000-000000000001"
#define CHAR_STREAM_UUID "AA10D002-0000-0000-0000-000000000001"

// Task stack sizes (bytes) — dựa trên dự đoán baseline
#define STACK_IMU    4096
#define STACK_PPG    4096
#define STACK_CLF    6144   // có windowBuffer[60] + beat detection state
#define STACK_BLE    8192   // NimBLE stack cần nhiều hơn

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
};

// -----------------------------------------------------------------------
// QUEUE HANDLES VÀ MUTEX
// (handles là global nhưng KHÔNG chứa data — đây là pattern đúng)
// -----------------------------------------------------------------------
static QueueHandle_t     imu_queue;
static QueueHandle_t     ppg_queue;
static QueueHandle_t     output_queue;
static SemaphoreHandle_t i2c_mutex;

// BLE characteristic handle — ghi bởi setup, đọc bởi ble_streamer
static NimBLECharacteristic* pStreamChar = nullptr;

// -----------------------------------------------------------------------
// SENSOR OBJECT (khởi tạo trong setup, dùng trong task_ppg_reader)
// -----------------------------------------------------------------------
static MAX30105 ppgSensor;
static bool     ppgOK = false;

static void initMPU6050() {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x6B); Wire.write(0x00);   // wake up
    Wire.endTransmission(true);
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x1C); Wire.write(0x18);   // ±16g
    Wire.endTransmission(true);
}

// -----------------------------------------------------------------------
// TASK 1: IMU READER
// Đọc gia tốc thô từ MPU6050 ở 25 Hz, đẩy vào imu_queue
// -----------------------------------------------------------------------
// -----------------------------------------------------------------------
// TASK 5: SESSION BUZZER
// Buzzes 3 times between activity sessions, 5 times when all done
// -----------------------------------------------------------------------
static void buzz(int count, int on_ms, int off_ms) {
    for (int i = 0; i < count; i++) {
        tone(BUZZER_PIN, 2000, on_ms);
        vTaskDelay(pdMS_TO_TICKS(on_ms + off_ms));
    }
}

static void task_session_buzzer(void* arg) {
    for (int session = 0; session < NUM_SESSIONS - 1; session++) {
        vTaskDelay(pdMS_TO_TICKS(SESSION_MS));
        buzz(3, 200, 150);   // 3 short beeps → next activity
    }
    vTaskDelay(pdMS_TO_TICKS(SESSION_MS));
    buzz(5, 500, 150);       // 5 long beeps → all done
    vTaskDelete(NULL);
}

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

                Serial.printf(">acc_std:%.1f|mean:%.1f\n", acc_std, meanMag);
                result.activity_class = (acc_std >= ACTIVITY_GATE)
                                      ? classifySignal(peak_max, acc_std, peak_rel)
                                      : 0;
                result.bpm      = currentBPM;
                result.mean_mag = meanMag;
                result.std_mag  = acc_std;
                result.peak_rel = peak_rel;
                result.peak_max = peak_max;

                xQueueSend(output_queue, &result, 0);

                // Slide window
                for (int i = 0; i < WINDOW_SIZE - STRIDE_SIZE; i++)
                    windowBuffer[i] = windowBuffer[i + STRIDE_SIZE];
                windowCount = WINDOW_SIZE - STRIDE_SIZE;
            }
        }

        // --- B. Drain tất cả PPG samples đang chờ (non-blocking) ---
        while (xQueueReceive(ppg_queue, &ppgSample, 0) == pdTRUE) {
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
    }
}

// -----------------------------------------------------------------------
// TASK 4: BLE STREAMER
// Nhận OutputResult → gửi BLE notification
// -----------------------------------------------------------------------
static void task_ble_streamer(void* arg) {
    OutputResult result;

    while (true) {
        // Blocking — task chỉ thức khi có data
        if (xQueueReceive(output_queue, &result, portMAX_DELAY) == pdTRUE) {

            // Format JSON đơn giản — dễ parse ở Web BLE dashboard
            char payload[96];
            snprintf(payload, sizeof(payload),
                     "{\"a\":%d,\"bpm\":%.1f,\"mean\":%.1f,\"std\":%.1f,\"pr\":%.2f,\"pm\":%.1f}",
                     result.activity_class,
                     result.bpm,
                     result.mean_mag,
                     result.std_mag,
                     result.peak_rel,
                     result.peak_max);

            if (pStreamChar != nullptr) {
                pStreamChar->setValue((uint8_t*)payload, strlen(payload));
                pStreamChar->notify();
            }

            // Serial stream cho Serial Plotter / debug
            Serial.printf(">activity:%d|bpm:%.2f|heap:%lu\n",
                          result.activity_class,
                          result.bpm,
                          (unsigned long)ESP.getFreeHeap());
        }
    }
}

// -----------------------------------------------------------------------
// SETUP BLE
// -----------------------------------------------------------------------
static void setupBLE() {
    NimBLEDevice::init(BLE_DEVICE_NAME);
    NimBLEServer*  pServer  = NimBLEDevice::createServer();
    NimBLEService* pService = pServer->createService(SVC_UUID);

    pStreamChar = pService->createCharacteristic(
        CHAR_STREAM_UUID,
        NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY
    );

    pService->start();

    NimBLEAdvertising* pAdv = NimBLEDevice::getAdvertising();
    pAdv->addServiceUUID(SVC_UUID);
    pAdv->setScanResponse(true);
    pAdv->start();

    Serial.println("[BLE] Advertising: " BLE_DEVICE_NAME);
}

// -----------------------------------------------------------------------
// SETUP — khởi tạo hardware, tạo queues, tạo tasks
// -----------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n=======================================================");
    Serial.println("   WEARABLE MONITOR — FreeRTOS v1");
    Serial.printf( "   CPU: %d MHz  |  Free heap: %.1f KB\n",
                   ESP.getCpuFreqMHz(), ESP.getFreeHeap() / 1024.0f);
    Serial.println("=======================================================");

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

    // Tạo mutex + queues
    i2c_mutex    = xSemaphoreCreateMutex();
    imu_queue    = xQueueCreate(IMU_Q_DEPTH, sizeof(ImuSample));
    ppg_queue    = xQueueCreate(PPG_Q_DEPTH, sizeof(PpgSample));
    output_queue = xQueueCreate(OUT_Q_DEPTH,  sizeof(OutputResult));
    Serial.println("[OK]  Queues created.");

    // BLE
    setupBLE();

    // Tạo 4 tasks
    //                         name           stack       arg  prio  handle
    xTaskCreate(task_imu_reader,    "imu_reader",    STACK_IMU, nullptr, 3, nullptr);
    xTaskCreate(task_ppg_reader,    "ppg_reader",    STACK_PPG, nullptr, 3, nullptr);
    xTaskCreate(task_classifier,    "classifier",    STACK_CLF, nullptr, 2, nullptr);
    xTaskCreate(task_ble_streamer,  "ble_streamer",  STACK_BLE, nullptr, 1, nullptr);
    xTaskCreate(task_session_buzzer,"session_buzzer",2048,      nullptr, 1, nullptr);

    Serial.println("[OK]  5 FreeRTOS tasks created.");
    Serial.printf( "[RAM] Free heap after init: %.1f KB\n\n",
                   ESP.getFreeHeap() / 1024.0f);
}

// -----------------------------------------------------------------------
// LOOP — không dùng trong FreeRTOS architecture
// Arduino loop() vẫn chạy như một task ưu tiên thấp — block nó lại
// -----------------------------------------------------------------------
void loop() {
    vTaskDelay(portMAX_DELAY);
}

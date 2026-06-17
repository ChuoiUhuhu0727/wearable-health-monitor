// =====================================================================
//  BASELINE MEASUREMENT FIRMWARE
//  Mục đích: đo Decision Tree classifier — latency, RAM, flash
//  Không có WiFi / Email / UDP — stripped-down hoàn toàn
//
//  HƯỚNG DẪN CHO TEAMMATE (Duy / Tùng):
//    1. Mở PlatformIO, chọn environment "baseline" ở thanh dưới
//    2. Nhấn Upload (mũi tên →)
//    3. Mở Serial Monitor, baud 115200
//    4. Chờ đúng 60 giây — báo cáo tự in ra sau mỗi 10 giây
//    5. Copy TOÀN BỘ text trong Serial Monitor, gửi lại cho Giang
//    * Nhớ để thiết bị đứng yên trên bàn khi đo *
// =====================================================================

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "MAX30105.h"
#include "classifier.h"

// --- PHẦN CỨNG (giữ nguyên từ production) ---
const int MPU_ADDR     = 0x68;
const int WINDOW_SIZE  = 60;
const int STRIDE_SIZE  = 10;
const int IMU_INTERVAL = 40;   // 25 Hz
const int PPG_INTERVAL = 10;   // 100 Hz

MAX30105      ppgSensor;
float         windowBuffer[WINDOW_SIZE];
int           windowCount  = 0;
float         globalAccMag = 2048.0f;
unsigned long lastIMUTime  = 0;
unsigned long lastPPGTime  = 0;

// --- STATE ĐO BASELINE ---
struct LatencyStats {
    uint32_t count    = 0;
    float    sum_us   = 0;
    float    min_us   = 1e9f;
    float    max_us   = 0;

    void record(float us) {
        sum_us += us; count++;
        if (us < min_us) min_us = us;
        if (us > max_us) max_us = us;
    }
    float mean() { return count ? sum_us / count : 0; }
};

LatencyStats featStats;   // thời gian trích xuất features (2 vòng lặp 60 phần tử)
LatencyStats infStats;    // thời gian classifySignal() thuần túy

uint32_t      setupEndHeap    = 0;
unsigned long lastReportTime  = 0;
int           reportNumber    = 0;

// --- KHỞI TẠO MPU6050 ---
void initMPU6050() {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x6B); Wire.write(0x00);  // wake up
    Wire.endTransmission(true);
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x1C); Wire.write(0x18);  // ±16g
    Wire.endTransmission(true);
}

// --- IN BÁO CÁO ---
void printReport(bool isFinal) {
    Serial.println();
    Serial.println("=======================================================");
    if (isFinal)
        Serial.printf("   [FINAL] BASELINE REPORT — %d samples collected\n", infStats.count);
    else
        Serial.printf("   [LIVE #%d] BASELINE REPORT — T=%lus\n", reportNumber, millis() / 1000UL);
    Serial.println("=======================================================");

    Serial.println("--- FLASH ---");
    Serial.printf("  Sketch used       : %7d bytes  (%6.1f KB)\n",
                  ESP.getSketchSize(), ESP.getSketchSize() / 1024.0f);
    Serial.printf("  Free sketch space : %7d bytes  (%6.1f KB)\n",
                  ESP.getFreeSketchSpace(), ESP.getFreeSketchSpace() / 1024.0f);

    Serial.println("--- RAM ---");
    Serial.printf("  Heap total        : %7d bytes  (%6.1f KB)\n",
                  ESP.getHeapSize(), ESP.getHeapSize() / 1024.0f);
    Serial.printf("  Free heap (now)   : %7d bytes  (%6.1f KB)\n",
                  ESP.getFreeHeap(), ESP.getFreeHeap() / 1024.0f);
    Serial.printf("  Free heap (min)   : %7d bytes  (%6.1f KB)\n",
                  ESP.getMinFreeHeap(), ESP.getMinFreeHeap() / 1024.0f);
    Serial.printf("  RAM used by fw    : %7.1f KB\n",
                  (ESP.getHeapSize() - setupEndHeap) / 1024.0f);

    int32_t leak = (int32_t)setupEndHeap - (int32_t)ESP.getFreeHeap();
    Serial.printf("  Heap drift        : %+.1f KB  (ideal = 0, leak > 0)\n",
                  leak / 1024.0f);

    if (featStats.count > 0) {
        Serial.println("--- LATENCY: Feature Extraction (2 vòng lặp 60 phần tử) ---");
        Serial.printf("  Samples : %u\n",          featStats.count);
        Serial.printf("  Mean    : %8.2f us  (%.4f ms)\n", featStats.mean(), featStats.mean() / 1000.0f);
        Serial.printf("  Min     : %8.2f us\n",    featStats.min_us);
        Serial.printf("  Max     : %8.2f us\n",    featStats.max_us);
    }

    if (infStats.count > 0) {
        Serial.println("--- LATENCY: classifySignal() — Decision Tree ---");
        Serial.printf("  Samples : %u\n",          infStats.count);
        Serial.printf("  Mean    : %8.2f us  (%.4f ms)\n", infStats.mean(), infStats.mean() / 1000.0f);
        Serial.printf("  Min     : %8.2f us\n",    infStats.min_us);
        Serial.printf("  Max     : %8.2f us\n",    infStats.max_us);
    }

    Serial.println("=======================================================");
    if (isFinal)
        Serial.println(">>> ĐO XONG — copy toàn bộ output này gửi cho Giang <<<");
    Serial.println();
}

// =====================================================================
void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 5000) { delay(10); }

    Serial.println("\n=======================================================");
    Serial.println("   BASELINE MODE — Decision Tree Classifier");
    Serial.println("   (Stripped: không WiFi, không Email)");
    Serial.println("=======================================================");
    Serial.printf("[INFO] CPU: %d MHz  |  Flash chip: %.0f KB\n",
                  ESP.getCpuFreqMHz(), ESP.getFlashChipSize() / 1024.0f);
    Serial.printf("[RAM]  Heap trước khi init sensor: %.1f KB\n",
                  ESP.getFreeHeap() / 1024.0f);

    Wire.begin(5, 6);
    Wire.setClock(100000);

    Serial.println("[SCAN] Scanning I2C bus...");
    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("[SCAN] Found device at 0x%02X\n", addr);
            found++;
        }
    }
    if (found == 0) Serial.println("[SCAN] No I2C devices found — check wiring");
    Serial.println("[SCAN] Done.");

    initMPU6050();

    if (!ppgSensor.begin(Wire, I2C_SPEED_FAST)) {
        Serial.println("[WARN] MAX30102 không tìm thấy — vẫn đo được IMU+classifier");
    } else {
        ppgSensor.setup(30, 1, 2, 100, 411, 4096);
        Serial.println("[OK]   MAX30102 init OK");
    }

    setupEndHeap = ESP.getFreeHeap();
    Serial.printf("[RAM]  Heap sau khi init sensor: %.1f KB\n\n", setupEndHeap / 1024.0f);
    Serial.println("[START] Đang đo... báo cáo mỗi 10s, final sau 60s.\n");

    lastReportTime = millis();
}

// =====================================================================
void loop() {
    unsigned long now = millis();

    // --- PPG 100 Hz (chỉ đọc để giữ sensor hoạt động bình thường) ---
    if (now - lastPPGTime >= PPG_INTERVAL) {
        lastPPGTime = now;
        ppgSensor.getIR();
    }

    // --- IMU 25 Hz + FEATURE EXTRACTION + INFERENCE ---
    if (now - lastIMUTime >= IMU_INTERVAL) {
        lastIMUTime = now;

        Wire.beginTransmission(MPU_ADDR);
        Wire.write(0x3B);
        Wire.endTransmission(false);
        Wire.requestFrom(MPU_ADDR, 6);
        if (Wire.available() < 6) return;

        int16_t ax = (Wire.read() << 8) | Wire.read();
        int16_t ay = (Wire.read() << 8) | Wire.read();
        int16_t az = (Wire.read() << 8) | Wire.read();

        globalAccMag = sqrtf((float)ax*ax + (float)ay*ay + (float)az*az);
        windowBuffer[windowCount++] = globalAccMag;

        if (windowCount >= WINDOW_SIZE) {

            // Đo latency FEATURE EXTRACTION
            uint32_t t0 = micros();
            float sumMag = 0, peak_max = 0;
            for (int i = 0; i < WINDOW_SIZE; i++) {
                sumMag += windowBuffer[i];
                if (windowBuffer[i] > peak_max) peak_max = windowBuffer[i];
            }
            float meanMag = sumMag / WINDOW_SIZE;
            float sumVar  = 0;
            for (int i = 0; i < WINDOW_SIZE; i++)
                sumVar += (windowBuffer[i] - meanMag) * (windowBuffer[i] - meanMag);
            float acc_std   = sqrtf(sumVar / WINDOW_SIZE);
            float peak_rel  = (meanMag > 0) ? (peak_max / meanMag) : 0;
            uint32_t t1 = micros();
            featStats.record((float)(t1 - t0));

            // Đo latency CLASSIFY
            uint32_t t2 = micros();
            volatile int result = classifySignal(peak_max, acc_std, peak_rel);
            uint32_t t3 = micros();
            infStats.record((float)(t3 - t2));
            (void)result;

            // Slide window
            for (int i = 0; i < WINDOW_SIZE - STRIDE_SIZE; i++)
                windowBuffer[i] = windowBuffer[i + STRIDE_SIZE];
            windowCount = WINDOW_SIZE - STRIDE_SIZE;
        }
    }

    // --- BÁO CÁO ---
    if (now - lastReportTime >= 10000) {
        lastReportTime = now;
        reportNumber++;
        bool isFinal = (now >= 60000);
        printReport(isFinal);

        if (isFinal) {
            // Reset để đo vòng tiếp nếu teammate muốn
            featStats = LatencyStats{};
            infStats  = LatencyStats{};
        }
    }
}

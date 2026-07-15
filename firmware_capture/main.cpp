// =====================================================================
//  WAVEFORM CAPTURE DEMO — standalone, NOT part of the FreeRTOS pipeline
//
//  Purpose: give a professor a quick look at the actual raw PPG (IR) and
//  accelerometer waveforms — the real dataset (firmware_ble/) never logs
//  these, only already-reduced features (bpm, mean_mag, std_mag, ...), so
//  there was no way to plot a real waveform from existing data.
//
//  Deliberately kept completely separate from firmware_ble/ — no
//  FreeRTOS, no queues, no session protocol. Just: wait 3s, sample both
//  sensors at 100Hz for CAPTURE_S seconds, print CSV lines over Serial,
//  then stop. capture_waveform.py (repo root) reads this and plots it.
//  Not meant to feed back into the real dataset or training pipeline.
// =====================================================================

#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"

#define IMU_ADDR      0x68
#define SAMPLE_HZ     100
#define CAPTURE_S     20     // seconds of waveform to capture

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

static bool readAccel(int16_t& ax, int16_t& ay, int16_t& az) {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom(IMU_ADDR, 6);
    if (Wire.available() < 6) return false;
    ax = (Wire.read() << 8) | Wire.read();
    ay = (Wire.read() << 8) | Wire.read();
    az = (Wire.read() << 8) | Wire.read();
    return true;
}

void setup() {
    Serial.begin(115200);
    delay(2000);
    Serial.println("\n===== WAVEFORM CAPTURE DEMO =====");

    Wire.begin(5, 6);
    Wire.setClock(100000);
    initMPU6050();

    ppgOK = ppgSensor.begin(Wire, I2C_SPEED_STANDARD);
    if (ppgOK) {
        ppgSensor.setup(30, 1, 2, 100, 411, 4096);
        Serial.println("[OK] MAX30105 found.");
    } else {
        Serial.println("[WARN] MAX30105 not found — IR column will read 0.");
    }

    Serial.println("[READY] Put the sensor on your wrist now.");
    Serial.printf("[PREP] Capturing in 3s, for %ds, at %dHz...\n", CAPTURE_S, SAMPLE_HZ);
    delay(3000);

    Serial.println("elapsed_ms,ax,ay,az,ir");

    unsigned long startMs = millis();
    const unsigned long periodMs = 1000UL / SAMPLE_HZ;
    unsigned long nextSampleMs = startMs;

    while (millis() - startMs < (unsigned long)CAPTURE_S * 1000UL) {
        if (millis() >= nextSampleMs) {
            nextSampleMs += periodMs;

            int16_t ax = 0, ay = 0, az = 0;
            readAccel(ax, ay, az);
            long ir = ppgOK ? ppgSensor.getIR() : 0;

            Serial.printf("%lu,%d,%d,%d,%ld\n", millis() - startMs, ax, ay, az, ir);
        }
    }

    Serial.println("===== CAPTURE DONE =====");
}

void loop() {
    delay(1000);   // nothing left to do — one capture per boot
}

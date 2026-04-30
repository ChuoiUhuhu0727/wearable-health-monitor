#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "MAX30105.h"
#include "classifier.h"

// --- CẤU HÌNH HỆ THỐNG ---
const int MPU_ADDR = 0x68;
const int WINDOW_SIZE = 60;
const int SAMPLE_INTERVAL = 40; // Đổi thành 40ms (25Hz) để khớp với dữ liệu Train

float windowBuffer[WINDOW_SIZE];
int windowCount = 0;
unsigned long lastSampleTime = 0;

void setup() {
  Serial.begin(115200);
  Wire.begin(8, 9); // Lolin S3 Mini Pins

  // Khởi tạo MPU6050 (Giữ nguyên code khởi tạo cũ của cậu)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); 
  Wire.write(0);    
  Wire.endTransmission(true);
  
  // Set Range +/- 16G (Quan trọng để không bị kịch trần khi đấm mạnh)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x1C); 
  Wire.write(0x18); 
  Wire.endTransmission(true);

  Serial.println("System Ready: AI Classification Mode");
}

void loop() {
  if (millis() - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = millis();

    // 1. ĐỌC DỮ LIỆU GIA TỐC
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, 6);

    if (Wire.available() >= 6) {
      int16_t ax = (Wire.read() << 8) | Wire.read();
      int16_t ay = (Wire.read() << 8) | Wire.read();
      int16_t az = (Wire.read() << 8) | Wire.read();

      // Tính Magnitude (Độ lớn tổng hợp)
      float accMag = sqrt((float)ax*ax + (float)ay*ay + (float)az*az);
      
      // Cho vào Buffer
      windowBuffer[windowCount] = accMag;
      windowCount++;

      // 2. KHI ĐỦ 60 MẪU (1 WINDOW) -> TÍNH FEATURE & PHÂN LOẠI
      if (windowCount >= WINDOW_SIZE) {
        float sum = 0, sumSq = 0, peakMax = 0;

        for (int i = 0; i < WINDOW_SIZE; i++) {
          float val = windowBuffer[i];
          sum += val;
          sumSq += val * val;
          if (val > peakMax) peakMax = val;
        }

        float mean = sum / WINDOW_SIZE;
        float variance = (sumSq / WINDOW_SIZE) - (mean * mean);
        float stdDev = sqrt(max(0.0f, variance));
        float peakRel = (mean != 0) ? (peakMax / mean) : 0;

        // 3. GỌI MÔ HÌNH AI
        int result = classifySignal(peakMax, stdDev, peakRel);

        // 4. XUẤT KẾT QUẢ
        Serial.print("Analysis: ");
        if (result == 1) {
          Serial.println(">>> [INTENSE PUNCH] <<<");
        } else {
          Serial.println("Normal movement");
        }

        // Reset để chờ Window tiếp theo
        windowCount = 0; 
      }
    }
  }
}
#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <WiFi.h>
#include <ESP_Mail_Client.h>
#include "MAX30105.h"
#include "classifier.h"

// --- CẤU HÌNH LOG & THỜI GIAN TEST ---
#define DEBUG_MODE true  
const unsigned long RECOVERY_TIME_MS = 60000; 

// --- CẤU HÌNH WI-FI & GMAIL ---
#define WIFI_SSID "TÊN_WIFI_NHÀ_CẬU"
#define WIFI_PASSWORD "MẬT_KHẨU_WIFI"
#define SMTP_HOST "smtp.gmail.com"
#define SMTP_PORT 465 
#define AUTHOR_EMAIL "gmail_cua_cau@gmail.com"
#define AUTHOR_PASSWORD "xxxx xxxx xxxx xxxx" 
#define RECIPIENT_EMAIL "gmail_nhan_bao_cao@gmail.com"

SMTPSession smtp;
void sendHeartRateReportEmail(float peak, float rest, float hrr, String evaluation, String sessionClass);
void initMPU6050(); 
void recoverI2CBus(); 

// --- CẤU HÌNH PHẦN CỨNG & AI ---
const int MPU_ADDR = 0x68;
const int WINDOW_SIZE = 60;
const int STRIDE_SIZE = 10;        
const int BASE_INTERVAL = 10;      // 100Hz
const int IMU_INTERVAL = 40;       // 25Hz

float windowBuffer[WINDOW_SIZE];
int windowCount = 0;
unsigned long lastBaseTime = 0;
unsigned long lastIMUTime = 0;

MAX30105 ppgSensor; 
long ppgBuffer[5] = {0, 0, 0, 0, 0};
long ppgFiltered = 0;
unsigned long lastBeatTime = 0; 
float globalAccMag = 2048.0; 

int totalWindowsInSession = 0;
int intenseWindowsInSession = 0;

enum SystemState { STATE_REST, STATE_PUNCHING, STATE_RECOVERY, STATE_DONE };
SystemState currentState = STATE_REST;

unsigned long punchingStart = 0;   
unsigned long peakBPMTime = 0;     
unsigned long quietPeriodStart = 0;
unsigned long recoveryStart = 0;
int lastPrintedSecond = -1;       

float peakBPM = 0.0;
float currentBPM = 75.0;          
const float PUNCH_THRESHOLD = 8192.0; 
const float ACTIVITY_GATE_THRESHOLD = 1500.0; 

// --- CƠ CHẾ BẢO VỆ CHỐNG VÒNG LẶP VÔ HẠN (ANTI-INFINITE LOOP CONFIG) ---
int consecutiveI2CFailures = 0;              // Bộ đếm số lần lỗi liên tiếp
const int MAX_CONSECUTIVE_FAILURES = 3;      // Giới hạn chịu đựng: 3 lần thử
bool hardwareFaultFlag = false;              // Cờ ngắt tử thần khi đứt hẳn dây

void initMPU6050() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); Wire.write(0);     
  Wire.endTransmission(true);
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x1C); Wire.write(0x18);  // Cấu hình cứng dải đo +/- 16G
  Wire.endTransmission(true);
}

// BỘ CỨU HỘ CÓ GIỚI HẠN: Ngăn chặn quá nhiệt CPU khi phần cứng đứt hẳn
void recoverI2CBus() {
  consecutiveI2CFailures++;
  
  if (consecutiveI2CFailures > MAX_CONSECUTIVE_FAILURES) {
    hardwareFaultFlag = true; // Kích hoạt cờ ngắt khẩn cấp
    Serial.println("\n=======================================================");
    Serial.println("🚨 [CRITICAL ERROR] THẤT BẠI KẾT NỐI PHẦN CỨNG LIÊN TIẾP!");
    Serial.println("=======================================================");
    Serial.println("-> Hệ thống đã thử tự động cứu hộ 3 lần nhưng bất thành.");
    Serial.println("-> Nguyên nhân: Dây SDA/SCL đã bị đứt hoặc tuột hoàn toàn khỏi chân D4/D5.");
    Serial.println("-> HẬU QUẢ: Đóng băng toàn bộ luồng loop để bảo vệ linh kiện.");
    Serial.println("👉 Hãy kiểm tra lại mối hàn, dây nối và bấm RESET nút cứng trên XIAO.");
    Serial.println("=======================================================");
    return;
  }

  Serial.printf("\n[⚠️ WATCHDOG] Phát hiện sập nghẽn Bus I2C (Thử sửa lần %d/%d)...", consecutiveI2CFailures, MAX_CONSECUTIVE_FAILURES);
  Wire.end(); 
  delay(20);
  
  Wire.begin(5, 6); 
  Wire.setClock(400000); 
  
  initMPU6050(); 
  if (ppgSensor.begin(Wire, I2C_SPEED_FAST)) {
    ppgSensor.setup(30, 1, 2, 100, 411, 4096);
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin(5, 6); 
  Wire.setClock(400000);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[HỆ THỐNG] Đang kết nối Wi-Fi");
  unsigned long startWifiTimeout = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startWifiTimeout < 4000) {
    delay(500); Serial.print(".");
  }
  if(WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[Wi-Fi] Đã kết nối!");
  } else {
    Serial.println("\n[Wi-Fi] Chạy Offline Mode...");
  }

  initMPU6050(); 

  if (!ppgSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[ERROR] Không tìm thấy MAX30102 trên chân D4/D5!");
    while (1);
  }
  ppgSensor.setup(30, 1, 2, 100, 411, 4096);

  Serial.println("\n=======================================================");
  Serial.println("   XIAO ESP32-S3 SAFE FAULT-TOLERANT WORKSPACE         ");
  Serial.println("=======================================================");
}

void loop() {
  // KHỐI CHẶN PHANH KHẨN CẤP: Nếu phần cứng hỏng hẳn, dừng ngay lập tức
  if (hardwareFaultFlag) {
    delay(1000); // Treo luồng an toàn, không tính toán, không xả log rác
    return; 
  }

  unsigned long currentTime = millis();

  // TẦNG 1: XỬ LÝ TIM MẠCH (100Hz)
  if (currentTime - lastBaseTime >= BASE_INTERVAL) {
    lastBaseTime = currentTime;
    long irValue = ppgSensor.getIR(); 
    
    if (irValue == 0 || irValue < 10000) return; 

    for (int i = 0; i < 4; i++) ppgBuffer[i] = ppgBuffer[i+1];
    ppgBuffer[4] = irValue;
    long sum = 0;
    for (int i = 0; i < 5; i++) sum += ppgBuffer[i];
    long currentFiltered = sum / 5;

    static float dcOffset = 0;
    dcOffset = (dcOffset * 0.99) + (currentFiltered * 0.01); 
    float acSignal = currentFiltered - dcOffset; 

    static float maxSignalInWave = 0;
    if (acSignal > 150) { 
      if (acSignal > maxSignalInWave) maxSignalInWave = acSignal; 
    } 
    else if (acSignal < -50 && maxSignalInWave > 150) {
      long timeBetweenBeats = currentTime - lastBeatTime;
      if (lastBeatTime == 0) {
        lastBeatTime = currentTime;
      } else {
        if (timeBetweenBeats > 375 && timeBetweenBeats < 1200) { 
          float calculatedBPM = 60000.0 / timeBetweenBeats;
          if (globalAccMag < 14000.0) {
            if (abs(calculatedBPM - currentBPM) < 35.0 || currentBPM == 75.0) {
              currentBPM = (currentBPM * 0.6) + (calculatedBPM * 0.4);
              lastBeatTime = currentTime; 
            }
          }
        } else if (timeBetweenBeats >= 1200) {
          lastBeatTime = currentTime;
        }
      }
      maxSignalInWave = 0; 
    }
    ppgFiltered = currentFiltered;
  }

  // TẦNG 2: PHÂN LOẠI AI VÀ ĐIỀU KHIỂN TRẠNG THÁI (25Hz)
  if (currentTime - lastIMUTime >= IMU_INTERVAL) {
    lastIMUTime = currentTime;

    Wire.beginTransmission(MPU_ADDR);
    if (Wire.endTransmission() != 0) {
      recoverI2CBus(); 
      return; 
    }

    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU_ADDR, 6);

    if (Wire.available() < 6) {
      recoverI2CBus();
      return;
    }

    // 👉 ĐIỂM CẢI TIẾN: Nếu đọc thành công trọn vẹn dữ liệu vật lý, lập tức xóa bộ đếm lỗi
    consecutiveI2CFailures = 0; 

    int16_t ax = (Wire.read() << 8) | Wire.read();
    int16_t ay = (Wire.read() << 8) | Wire.read();
    int16_t az = (Wire.read() << 8) | Wire.read();

    globalAccMag = sqrt((float)ax*ax + (float)ay*ay + (float)az*az);
    windowBuffer[windowCount] = globalAccMag;
    windowCount++;

    if (windowCount >= WINDOW_SIZE) {
      float sumMag = 0; float peak_max = 0;
      for (int i = 0; i < WINDOW_SIZE; i++) {
        sumMag += windowBuffer[i];
        if (windowBuffer[i] > peak_max) peak_max = windowBuffer[i];
      }
      float meanMag = sumMag / WINDOW_SIZE;
      float sumVariance = 0;
      for (int i = 0; i < WINDOW_SIZE; i++) {
        sumVariance += pow(windowBuffer[i] - meanMag, 2);
      }
      float acc_std = sqrt(sumVariance / WINDOW_SIZE);

      if (acc_std >= ACTIVITY_GATE_THRESHOLD) {
        float peak_relative = (meanMag > 0) ? (peak_max / meanMag) : 0;
        int punchClass = classifySignal(peak_max, acc_std, peak_relative);
        
        if (currentState == STATE_PUNCHING) {
          totalWindowsInSession++;
          if (punchClass == 1) intenseWindowsInSession++;

          Serial.printf("\n>>>>>>> [AI FEATURE METRICS] PEAK_MAX: %.1f | ACC_STD: %.1f | RELATIVE: %.2f <<<<<<<\n", peak_max, acc_std, peak_relative);
          Serial.print("[AI EVALUATION] Kết quả cửa sổ cuốn này: ");
          Serial.println((punchClass == 1) ? "🔥 CÚ ĐẤM MẠNH (INTENSE)" : "💤 ĐẤM THƯỜNG (NORMAL)");
        }
      }

      for (int i = 0; i < WINDOW_SIZE - STRIDE_SIZE; i++) {
        windowBuffer[i] = windowBuffer[i + STRIDE_SIZE];
      }
      windowCount = WINDOW_SIZE - STRIDE_SIZE; 
    }

    // --- MÁY TRẠNG THÁI FSM ---
    switch (currentState) {
      case STATE_REST:
        if (globalAccMag > PUNCH_THRESHOLD) {
          currentState = STATE_PUNCHING;
          punchingStart = millis(); peakBPM = currentBPM; peakBPMTime = 0;
          totalWindowsInSession = 0; intenseWindowsInSession = 0; 
          windowCount = 0; 
          Serial.println("\n[FSM] Bắt đầu bài đấm -> STATE_PUNCHING.");
        }
        break;

      case STATE_PUNCHING:
        if (currentBPM > peakBPM) {
          peakBPM = currentBPM;
          peakBPMTime = millis() - punchingStart; 
        }
        if (globalAccMag < PUNCH_THRESHOLD) {
          if (quietPeriodStart == 0) quietPeriodStart = millis(); 
          else if (millis() - quietPeriodStart >= 3000) {
            currentState = STATE_RECOVERY;
            recoveryStart = millis(); lastPrintedSecond = -1; 
            Serial.println("\n[FSM] Ngừng đấm quá 3s. Chuyển sang -> STATE_RECOVERY.");
          }
        } else { quietPeriodStart = 0; }
        break;

      case STATE_RECOVERY: {
        unsigned long elapsedRecovery = millis() - recoveryStart;
        
        if (elapsedRecovery <= 15000) {
          if (currentBPM > peakBPM) {
            peakBPM = currentBPM;
            peakBPMTime = millis() - punchingStart; 
          }
        }

        int currentSecond = elapsedRecovery / 1000;
        int targetSeconds = RECOVERY_TIME_MS / 1000;
        if (currentSecond != lastPrintedSecond && currentSecond <= targetSeconds) {
          lastPrintedSecond = currentSecond;
          Serial.printf("[RECOVERY] Tiến trình nghỉ: %d/%d giây... (Nhịp tim: %.2f BPM)\n", currentSecond, targetSeconds, currentBPM);
        }

        if (elapsedRecovery >= RECOVERY_TIME_MS) {
          float hrrScore = peakBPM - currentBPM;
          currentState = STATE_DONE;
          
          String sessionClass = "💤 ĐẤM THƯỜNG / KHỞI ĐỘNG (NORMAL SESSION)";
          if (totalWindowsInSession > 0) {
            float intenseRatio = (float)intenseWindowsInSession / totalWindowsInSession;
            if (intenseRatio >= 0.3) { 
              sessionClass = "🔥 HIỆP ĐẤM CƯỜNG ĐỘ CAO (INTENSE SESSION)";
            }
          }

          String evalStr = "";
          if (hrrScore < 12)       evalStr = "XAU (He tim mach phuc hoi kem)";
          else if (hrrScore <= 20) evalStr = "TRUNG BINH (The trang binh thuong)";
          else                     evalStr = "TOT (He tim mach xuat sac)";

          Serial.println("\n=======================================================");
          Serial.println("          BÁO CÁO KẾT QUẢ TOÀN HIỆP ĐẤM & HRR          ");
          Serial.println("=======================================================");
          Serial.print("  => CƯỜNG ĐỘ TOÀN HIỆP : "); Serial.println(sessionClass);
          Serial.printf("  => Nhịp tim đỉnh thực  : %.2f BPM (Giây thứ %d)\n", peakBPM, (int)(peakBPMTime / 1000));
          Serial.printf("  => Nhịp tim hồi phục   : %.2f BPM\n", currentBPM);
          Serial.printf("  => Chỉ số HRR đạt được : %.2f BPM\n", hrrScore);
          Serial.println("  -----------------------------------------------------");
          Serial.print("  => ĐÁNH GIÁ SỨC KHỎE   : "); Serial.println(evalStr);
          Serial.println("=======================================================");
          Serial.println("Nhấn phím 'r' trên Serial Monitor gửi xuống để RESET mạch.");

          sendHeartRateReportEmail(peakBPM, currentBPM, hrrScore, evalStr, sessionClass);
        }
        break;
      }

      case STATE_DONE:
        if (Serial.available() > 0 && Serial.read() == 'r') {
          currentState = STATE_REST; peakBPM = 0; quietPeriodStart = 0; windowCount = 0;
          Serial.println("\n[HỆ THỐNG] Đã reset về trạng thái Rest thủ thế.");
        }
        break;
    }

    if (DEBUG_MODE && currentState != STATE_DONE) {
      Serial.printf(">Acc_Mag:%d|Current_BPM:%.2f\n", (int)globalAccMag, currentBPM);
    }
  }
}

void sendHeartRateReportEmail(float peak, float rest, float hrr, String evaluation, String sessionClass) {
  if (WiFi.status() != WL_CONNECTED) return;
  Session_Config config;
  config.server.host_name = SMTP_HOST; config.server.port = SMTP_PORT;
  config.login.email = AUTHOR_EMAIL;   config.login.password = AUTHOR_PASSWORD;
  
  SMTP_Message message;
  message.sender.name = "Aikido Embedded AI"; message.sender.email = AUTHOR_EMAIL;
  message.subject = "Bao cao Tap luyen Aikido"; message.addRecipient("User", RECIPIENT_EMAIL);

  String textMsg = "BÁO CÁO TOÀN HIỆP ĐẤM\n\n";
  textMsg += "Cường độ tổng thể: " + sessionClass + "\n";
  textMsg += "- Peak BPM: " + String(peak, 2) + "\n";
  textMsg += "- Rest BPM: " + String(rest, 2) + "\n";
  textMsg += "- HRR Score: " + String(hrr, 2) + "\n";
  textMsg += "=> Đánh giá: " + evaluation;
  message.text.content = textMsg.c_str();

  if (smtp.connect(&config)) {
    MailClient.sendMail(&smtp, &message);
    Serial.println("[EMAIL] Đã tự động gửi báo cáo tổng hợp.");
  }
}
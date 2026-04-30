# 🥋 Aikido Punch Intensity Tracker (Member 2: Data Collection & Preprocessing)

Dự án này tập trung vào việc thu thập và xử lý dữ liệu đa cảm biến (IMU + PPG) để nhận diện cường độ đòn đánh trong Aikido. Hệ thống sử dụng ESP32 S3 để ghi nhận dữ liệu thời gian thực với tần số 100Hz.

## 🛠 Hardware Configuration
- **MCU:** ESP32 S3 (Lolin S3 Mini).
- **IMU:** MPU6050 - Cấu hình dải đo **±16g** để tránh hiện tượng Clipping khi đấm mạnh.
- **PPG:** MAX30102 - Điều chỉnh LED Brightness để duy trì IR Value trong dải **100k - 200k**, ngăn chặn bão hòa tín hiệu (Saturation).

## 📂 Project Structure
Dự án được tổ chức theo cấu trúc chuẩn để dễ dàng bàn giao và mở rộng:
```text
Aikido_Project/
├── data/
│   ├── raw/             # Chứa 17+ file CSV dữ liệu thô từ các hiệp thu
│   └── processed/       # File master_dataset_aikido.csv sau khi đã gộp và xử lý
├── firmware/
│   └── main.cpp         # Code C++ nạp cho ESP32
├── scripts/
│   └── collect_data.py  # Script Python thu thập dữ liệu qua Serial (Relative Path ready)
├── notebooks/
│   ├── 5th_analyze_data.ipynb    # Phân tích QC (Clipping, Saturation check)
│   └── 6th_master_processing.ipynb # Gộp file và trích xuất đặc trưng (Feature Engineering)
├── docs/
│   └── visual_qc/       # Kho lưu trữ ảnh Plot của các hiệp thu chuẩn (Clean)
└── README.md```

## Data Dictionary (For master_dataset.csv)
Column,Unit,Description
Timestamp,Seconds,Thời gian tương đối tính từ 0s của mỗi hiệp.
"AccX, Y, Z",Raw LSB,Gia tốc thô 3 trục. Trục Z là trục lực đấm chính.
Acc_Mag,Raw LSB,Độ lớn gia tốc tổng hợp AccX2+AccY2+AccZ2​.
Heart_IR,Raw Value,Tín hiệu hồng ngoại thô (PPG) để tính nhịp tim.
Phase,Label,"0: Rest, 1: Punching, 2: Recovery."
Intensity_Label,Label,"1: Light, 2: Medium, 3: Intense/Fatigue."

## 🧪 Collection Protocols
Dữ liệu được thu thập dựa trên các kịch bản thời gian nghiêm ngặt:

LIGHT: 20s Nghỉ - 20s Đấm - 40s Hồi phục.

MEDIUM: 15s Nghỉ - 30s Đấm - 45s Hồi phục.

INTENSE/FATIGUE: 15s Nghỉ - 45s Đấm - 60s Hồi phục.

## 📈 Quality Control Examples
Dữ liệu được dán nhãn CLEAN khi và chỉ khi:

Không bị Clipping gia tốc (Magnitude < 32,767).

Tín hiệu PPG ổn định, không bị rơi về 0 trong suốt quá trình đấm (Motion Artifacts được kiểm soát).
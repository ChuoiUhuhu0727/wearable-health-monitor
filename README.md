# 🥋 Punch Intensity Tracker

Dự án thu thập và xử lý dữ liệu đa cảm biến (IMU + PPG) phục vụ nhận diện cường độ đòn đánh Aikido. Hệ thống chạy trên ESP32 S3 với tần số 100Hz.

## 🛠 Hardware Configuration
- **MCU:** ESP32 S3 (Lolin S3 Mini).
- **IMU:** MPU6050 - Cấu hình dải đo **±16g**.
- **PPG:** MAX30102 - IR ổn định ở mức **100k - 200k**.

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
└── README.md

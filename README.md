# Wearable Activity & Health Monitor

Thiết bị đeo cổ tay nhận diện hoạt động thể chất và đo nhịp tim theo thời gian thực, xử lý hoàn toàn trên chip — không cần internet, không cần cloud.

**Team:** Hoàng Nguyễn Ngọc Giang · Phan Ngọc Quốc Duy · Trần Thanh Tùng  
**Thời gian:** 13 tuần · 2 tháng 6 – 1 tháng 9, 2026

---

## Hardware

| Linh kiện | Vai trò | Thông số |
| :--- | :--- | :--- |
| Seeed XIAO ESP32-S3 | Vi điều khiển chính | 240 MHz, 512 KB SRAM |
| MPU6050 | Cảm biến chuyển động (IMU) | Gia tốc + Con quay hồi chuyển, ±16g |
| MAX30102 | Cảm biến quang học (PPG) | IR 940nm + Red 660nm |

Kết nối I2C: SDA = D4 (pin 5), SCL = D5 (pin 6), 400 kHz.

---

## Output

| Đầu ra | Tần suất cập nhật |
| :--- | :--- |
| Hoạt động: Walk / Run / Sit / Stand / Lying Down | Mỗi 2–3 giây |
| Nhịp tim (BPM) | Mỗi 5 giây |
| SpO2 (%) | Tùy chọn — Phase 3 |

Tất cả kết quả phát qua **BLE GATT notify** → Web dashboard trên Chrome. Không cần cài app.

---

## Kiến trúc phần mềm (FreeRTOS)

```
┌─────────────────┐    imu_queue     ┌──────────────────┐    output_queue    ┌──────────────────┐
│ task_imu_reader │ ───────────────► │                  │ ─────────────────► │ task_ble_streamer│
│  priority: 3    │                  │  task_classifier │                    │   priority: 1    │
│  rate: 25 Hz    │    ppg_queue     │   priority: 2    │                    │   BLE GATT notify│
├─────────────────┤ ───────────────► │                  │                    └──────────────────┘
│ task_ppg_reader │                  └──────────────────┘
│  priority: 3    │
│  rate: 100 Hz   │
└─────────────────┘

Tất cả data đi qua queue. Không có global variable chứa data giữa các task.
I2C dùng chung mutex để tránh xung đột giữa 2 reader tasks.
```

**Pipeline xử lý tín hiệu:**
- IMU → sliding window 60 mẫu, stride 10 → trích xuất features → AI classifier
- PPG → lọc DC offset → phát hiện đỉnh → tính BPM

---

## Cấu trúc project

```
.
├── firmware/                  # Production cũ (Aikido punch tracker — giữ lại để tham khảo)
├── firmware_baseline/         # Firmware đo baseline Decision Tree (Week 1)
│   └── main.cpp
├── firmware_freertos/         # Firmware FreeRTOS 4-task + BLE (Week 2+)
│   └── main.cpp
├── data/
│   ├── raw/                   # CSV thô từ các hiệp thu thập
│   └── processed/
│       └── master_dataset_aikido.csv   # 39k mẫu đã gán nhãn
├── notebooks/
│   ├── 8th_Draft_Signal_Final_Project.ipynb   # Training Decision Tree + xuất classifier.h
│   └── ...
├── scripts/
│   └── collect_data.py        # Thu thập dữ liệu qua Serial
├── docs/visual_qc/            # QC plots các hiệp thu
├── platformio.ini
└── README.md
```

---

## PlatformIO Environments

| Environment | Dùng khi nào | Firmware |
| :--- | :--- | :--- |
| `seeed_xiao_esp32s3` | Production cũ (Aikido) | `firmware/` |
| `baseline` | **Đo latency + RAM + flash của Decision Tree** | `firmware_baseline/` |
| `freertos_v1` | **Kiến trúc FreeRTOS mới + BLE** | `firmware_freertos/` |

---

## Quick Start

### Build và Flash

```bash
# Yêu cầu: PlatformIO Core hoặc VS Code + PlatformIO extension

# Flash firmware baseline (đo baseline)
pio run -e baseline -t upload

# Flash firmware FreeRTOS (kiến trúc mới)
pio run -e freertos_v1 -t upload

# Mở Serial Monitor
pio device monitor
```

### Verify BLE (cho firmware FreeRTOS)

1. Cài **nRF Connect** trên điện thoại (iOS hoặc Android)
2. Scan → tìm device tên `WearableMonitor`
3. Connect → thấy service UUID `AA10D001-...`
4. Subscribe characteristic `AA10D002-...` → nhận JSON `{"a":0,"bpm":75.0,...}`

---

## AI Model

| Model | Accuracy (LOGO-CV) | Latency | RAM |
| :--- | :--- | :--- | :--- |
| Decision Tree (depth=3) | 89.9% | < 5 µs (dự đoán) | ~0 KB thêm |
| TFLite Micro int8 (Week 6+) | TBD | < 50 ms (target) | ≤ 100 KB |

Model hiện tại phân loại nhị phân: **normal** vs **intense** dựa trên 3 features từ cửa sổ Acc_Mag 60 mẫu.
Roadmap: chuyển sang TFLite Micro với 5 class (Walk/Run/Sit/Stand/Lying Down).

---

## Milestones

| Milestone | Tuần | Trạng thái |
| :--- | :--- | :--- |
| M1: FreeRTOS 4-task + BLE advertising | Cuối tuần 2 | Đang làm |
| M2: BLE streaming + dataset ≥10 người | Cuối tuần 4 | Chưa bắt đầu |
| M3: TFLite Micro int8 deployed | Cuối tuần 7 | Chưa bắt đầu |
| M4: PCB assembled | Cuối tuần 7 | Chưa bắt đầu |
| M5: Full integration | Cuối tuần 8 | Chưa bắt đầu |
| M6: 60-minute stability test | Cuối tuần 11 | Chưa bắt đầu |
| M7: Final demo | Cuối tuần 13 | Chưa bắt đầu |

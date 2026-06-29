# Wearable Activity & Health Monitor

A wrist-worn device that recognizes physical activity and measures heart rate in real time — all processed on-chip, no internet, no cloud required.

**Team:** Hoàng Nguyễn Ngọc Giang · Phan Ngọc Quốc Duy · Trần Thanh Tùng
**Duration:** 13 weeks · June 2 – September 1, 2026

---

## Hardware

| Component | Role | Specs |
| :--- | :--- | :--- |
| Seeed XIAO ESP32-S3 | Main MCU | 240 MHz, 512 KB SRAM |
| MPU6050 | Motion sensor (IMU) | Accelerometer + Gyroscope, ±16g |
| MAX30102 | Optical sensor (PPG) | IR 940nm + Red 660nm |

I2C bus: SDA = D4 (pin 5), SCL = D5 (pin 6), 100 kHz.

### Sensor Placement

MAX30102 is worn on the **dorsal (outer) wrist** — the same position as a commercial smartwatch. This uses **reflective PPG**: the LED and photodetector face the skin on the same side, and the photodetector reads light scattered back from blood vessels beneath the skin.

Wrist PPG produces weaker signal and more motion artifacts than fingertip placement. This is addressed by an **IMU-based adaptive filter** (see Signal Processing below).

---

## Output

| Output | Update rate |
| :--- | :--- |
| Activity class: Walk / Run / Sit / Stand / Lying Down | Every 2–3 seconds |
| Heart rate (BPM) | Every 5 seconds |
| SpO2 (%) | Optional — Phase 3 only |

All outputs stream via **BLE GATT notify** → Web dashboard in Chrome. No app installation required.

---

## Software Architecture (FreeRTOS)

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

All data flows through queues. No global variables shared between tasks.
I2C shared via mutex — prevents bus contention between the two reader tasks.
```

### Signal Processing Pipeline

**IMU path:**
```
Raw accelerometer → sliding window (60 samples, stride 10) → feature extraction → classifier
```

**PPG path:**
```
Raw IR signal → IMU-based LMS adaptive filter (motion artifact removal) → DC offset removal → peak detection → BPM
```

The **LMS (Least Mean Squares) adaptive filter** uses real-time IMU magnitude as a reference signal to estimate and subtract motion-induced noise from the PPG signal. Filter strength adapts sample-by-sample — high wrist movement automatically triggers stronger artifact suppression without relying on activity labels.

---

## Repository Structure

```
.
├── firmware/                  # Main FreeRTOS codebase (4-task + BLE)
│   ├── main.cpp
│   └── classifier.h
├── firmware_baseline/         # Baseline firmware — Decision Tree, Week 1 reference
│   └── main.cpp
├── experiments/
│   ├── fingertip/             # Research data: MAX30102 on fingertip (higher signal quality)
│   └── wrist/                 # Competition data: MAX30102 on dorsal wrist
├── dashboard/                 # Web BLE dashboard (HTML/JS)
├── paper/                     # Research writeup — Q3 journal target
├── platformio.ini
└── README.md
```

---

## PlatformIO Environments

| Environment | Purpose | Source |
| :--- | :--- | :--- |
| `baseline` | Baseline Decision Tree — latency + RAM reference | `firmware_baseline/` |
| `freertos_v1` | FreeRTOS 4-task architecture + BLE | `firmware/` |

```bash
# Flash baseline firmware
pio run -e baseline -t upload

# Flash FreeRTOS firmware
pio run -e freertos_v1 -t upload

# Open Serial Monitor
pio device monitor
```

### Verify BLE

1. Install **nRF Connect** on iOS or Android
2. Scan → find device named `WearableMonitor`
3. Connect → locate service UUID `AA10D001-...`
4. Subscribe to characteristic `AA10D002-...` → receive JSON `{"a":0,"bpm":75.0,...}`

---

## AI Model

| Model | Accuracy (LOGO-CV) | Inference latency | RAM overhead |
| :--- | :--- | :--- | :--- |
| Decision Tree (depth=3) | 89.9% | < 5 µs | ~0 KB |
| TFLite Micro INT8 (Week 6+) | TBD | < 50 ms target | ≤ 100 KB |

Current model: binary classifier (**normal** vs **intense**) using 3 features from a 60-sample Acc_Mag window.
Roadmap: 5-class TFLite Micro model (Walk / Run / Sit / Stand / Lying Down).

---

## Research Track

**Question:** On ESP32-class hardware under FreeRTOS memory and CPU constraints, which adaptive filter algorithm (LMS, RLS, or Wiener) best removes motion artifacts from wrist-worn PPG — and does it achieve clinically usable heart rate accuracy?

**Why this matters:** Most wrist PPG research tests on commercial hardware (Apple Watch, Empatica, Garmin). No published work benchmarks these algorithms on microcontroller-class devices with RTOS constraints.

**Experiment design:**
- `experiments/fingertip/` — ground truth: MAX30102 on fingertip, known to give clean signal
- `experiments/wrist/` — test condition: same sensor on dorsal wrist with motion artifact removal
- Metric: BPM error vs fingertip reference across activity classes

**Target:** Q3-indexed journal submission.

---

## Competition Track

This project is submitted to the **Convergence Innovation Competition (CIC)** organized by Georgia Tech, under the **Global Health and Wellbeing** track.

**Business case:** Cardiovascular disease causes 19.8 million deaths per year (WHO, 2022) — 79.6% attributable to modifiable risk factors. Continuous monitoring enables early intervention. However, commercial wearables cost $300–500 and lock raw sensor data behind proprietary APIs. Research-grade alternatives (ActiGraph: $325–$1,016/unit; Empatica E4: ~$1,690/unit) are prohibitively expensive for large-cohort studies.

This device delivers comparable monitoring capability at ~$20–30 in components, with open BLE data access and fully customizable firmware — directly addressing the cost and data-access barriers faced by clinical researchers in low- and middle-income countries.

**SDG alignment:** SDG 3 — Good Health and Well-Being.

---

## Milestones

| Milestone | Week | Status |
| :--- | :--- | :--- |
| M1: FreeRTOS 4-task + BLE advertising | End of week 2 | In progress |
| M2: BLE streaming + dataset ≥ 10 subjects | End of week 4 | Not started |
| M3: TFLite Micro INT8 deployed | End of week 7 | Not started |
| M4: LMS adaptive filter implemented + benchmarked | End of week 7 | Not started |
| M5: Fingertip vs wrist experiment complete | End of week 8 | Not started |
| M6: Full integration test | End of week 8 | Not started |
| M7: 60-minute stability test | End of week 11 | Not started |
| M8: CIC submission + paper draft | End of week 12 | Not started |
| M9: Final demo | End of week 13 | Not started |

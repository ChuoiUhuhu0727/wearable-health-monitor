# Wearable Activity & Health Monitor

**A $25 wrist-worn device that classifies physical activity on-chip — and a root-cause
analysis of why its heart-rate subsystem could not work.**

`ESP32-S3` · `FreeRTOS` · `C++` · `Python` · `scikit-learn` · `Embedded signal processing`

🇻🇳 [Đọc bản tiếng Việt](README.vi.md)

---

## What this is

A wrist-worn health monitor built from ~25 USD of parts, against 325–1690 USD for the
research-grade devices it substitutes for. Everything runs on the microcontroller: no
phone app, no cloud, no internet.

It has two independent subsystems:

- **Subsystem A — activity recognition.** Classifies Lying / Sitting / Standing / Walking
  / Running from a wrist accelerometer, in real time, on-chip.
- **Subsystem B — heart rate.** Removes motion artifacts from wrist PPG using the
  accelerometer as a noise reference (NLMS / RLS / Wiener), to extract heart rate.

Subsystem A works and is deployed. Subsystem B does not, and **the interesting part of
this project is the evidence trail proving why** — traced to the sensor hardware, not to
the algorithms.

📄 Full write-up: **[paper/THESIS_EN.md](paper/THESIS_EN.md)** — 7 chapters, methodology
through root-cause analysis. Every number in it is reproducible from
[paper/EVIDENCE_GUIDE.md](paper/EVIDENCE_GUIDE.md).

---

## Headline results

| | Result | Measured how |
| :--- | :--- | :--- |
| Activity classification (3-class) | **85.3%** on unseen users | LOGO-CV, 18 participants, 16,880 windows |
| Activity classification (5-class) | **54.8%** on unseen users | Same protocol — error is structural, see below |
| On-device live accuracy | running 98.4% · standing 96.8% · walking 83.4% | Real hardware session, model running on the ESP32 |
| Firmware footprint | **11.4% RAM** (37 KB / 320 KB) · **18.1% flash** | `pio run -e ble`, 7 FreeRTOS tasks + BLE + LittleFS |
| Dataset | **18 participants**, 5 activities, 20,258 labelled windows | Self-collected, untethered, logged to on-chip flash |
| Wrist PPG signal yield | **9.6%** of windows usable (vs 35.0% at fingertip) | After rebuilding the reference estimator |

LOGO-CV = Leave-One-Group-Out cross-validation: train on 17 people, test on the 18th,
repeat 18 times. It measures generalisation to a **new user**, not to new windows from
people the model has already seen.

---

## Two engineering findings

### 1. Proving a feature set was mathematically incapable of the task

The 5-class classifier plateaued at 54.8%. The confusion matrix showed the error was not
spread out — it sat **entirely** inside one 3×3 block: lying, sitting and standing were
confused with each other, while the static/moving boundary was clean.

All four features were functions of acceleration magnitude `√(ax² + ay² + az²)`, and
magnitude is **invariant to rotation**. The only thing that separates the three static
postures *is* wrist orientation. The information was destroyed at feature extraction,
before any model saw it — so no model, and no amount of tuning, could recover it.

Three attempted fixes (per-axis means; per-axis means relative to each person's own
baseline; both re-tested at larger N) each worked for some participants and broke others,
because wearing angle was never calibrated. After the third attempt the effort was stopped
deliberately, the limit was reported as a root-caused finding, and the problem was
**redefined to match what the sensor can physically measure** — 3 classes, 85.3%.

The honest footnote, computed rather than glossed over: the majority-class baseline is
0.201 for the 5-class problem but 0.599 for the 3-class one (`stationary` absorbs 3 of 5
classes). So the fair comparison is each model's margin over *its own* baseline — **+0.347
vs +0.254** — not the raw 0.548 → 0.853 jump, which overstates the gain.

### 2. Finding a 2× error hidden inside the reference measurement

The first filter comparison returned 26.95–29.96 bpm MAE — 5–6× worse than the
ANSI/AAMI EC13 clinical limit of ±5 bpm, with every adaptive filter performing *worse*
than no filtering at all.

Before concluding the algorithms were useless, the **reference channel itself** was tested
against a physiological rule: *running heart rate must exceed lying heart rate.* It failed
for 3 of 5 participants. P17 read 76.0 bpm lying and 77.0 bpm running.

Root cause: an **octave error** — the FFT-based estimator was locking onto half or double
the true rate. It had survived for weeks because a continuity constraint
(`MAX_JUMP_BPM = 25`) belonging to the *smoothing* layer was silently protecting an error
in the *measurement* layer: a steady sequence of [77, 77, 77, …] looked trustworthy, and the
occasional correct 156 bpm was rejected as an impossible jump.

The rebuilt estimator works in the time domain (`HR = 60 / median(RR intervals)`), carries
a signal-quality index (`CV = σ_RR / μ_RR`), and is allowed to return **"unknown"** rather
than guess. Validated against hand-counted peaks, it corrected errors in **both**
directions (P17 77.0 → 156.9; P16 155.8 → 118.9), and participants passing the
physiological check went from 40% to 80%.

With a trustworthy ruler, the real result appeared: the wrist channel yields a usable
heart rate in only **9.6%** of windows. The cause is the optical front end — the MAX30102
is a pulse-oximetry part emitting 660 nm red / 880 nm infrared, while wrist reflectance
heart rate needs ~525 nm green. The benchmark this project was measured against (TROIKA,
~2 bpm) used the same site, window length and metric — with green LEDs.

**Conclusion: a software problem that was never a software problem.** No filter can
separate a signal that the acquisition layer never captured.

---

## System architecture

```
[MPU6050 25 Hz]   [MAX30102 wrist 100 Hz]   [MAX30102 fingertip 100 Hz]
       |                    |                          |
       +--- 3 reader tasks (highest priority, fixed clock) ---+
       |                    |                          |
    imu_queue          ppg_queue                  raw_ppg2_queue
       |                    |                          |
  [task_classifier] -> features -> decision tree -> activity class
       |                    |
  [task_flash_writer] -> session_N.csv + raw_ppg / raw_ppg2 / raw_accel  (LittleFS)
       |
  [task_ble_streamer] -> live JSON rows (convenience only, never required)
```

Three architectural decisions that held up for the whole build:

1. **Seven FreeRTOS tasks share nothing but queues.** No globals across tasks. Sensor
   readers hold the highest priority and are the only tasks tied to a fixed clock;
   classification, flash writes and BLE are allowed to be late without ever disturbing the
   sampling rate.
2. **Flash is the source of truth; wireless is best-effort.** Every row is written to
   on-chip flash unconditionally. This replaced a WiFi/UDP transport and then a
   BLE-primary transport, both of which dropped data exactly when participants moved.
3. **The device owns the clock and the labels.** Full rows (label, `elapsed_ms`,
   transition flag) are assembled on-device, so the host can never disagree about when
   something happened.

The trained tree is exported to **nested if/else C** (`scripts/train/export_classifier_to_c.py`)
— no TFLite runtime, no heap allocation, a handful of float comparisons per window.

---

## Repository layout

```
firmware/               PlatformIO sources (src_dir)
  ble/                  Main firmware: 7 FreeRTOS tasks, BLE, LittleFS, deployed classifier
  baseline/             Single-loop reference build (latency/RAM comparison)
  capture/              Standalone raw-waveform capture tool
scripts/
  collect/              Session retrieval from device flash, BLE live view, waveform capture
  dataset/              Raw sessions -> data/processed/master_dataset.csv, readiness checks
  train/                LOGO-CV training, evaluation, export to C header
  analysis/             Subsystem B pipeline (NLMS/RLS/Wiener, HR estimator v2, sanity
                        checks) and the figure scripts that import it — one coupled cluster
  report/               Standalone report tooling: diagram generators, markdown -> docx
  viz/                  Session plots, raw waveform plots, live serial viewers
experiments/            Raw captured sessions, as collected (wrist/, fingertip/)
data/processed/         Derived dataset built by scripts/dataset/
models/                 Trained model artifact (.pkl)
paper/                  Reports, per-week progress reports, figures
docs/                   Data-collection setup guide for collaborators
archived/               Parked work kept for the record (WiFi/UDP firmware, Jetson server, old README)
```

`experiments/` (raw, immutable, exactly as captured) is kept separate from
`data/processed/` (derived, regenerable) on purpose — and the raw paths are deliberately
left unrenamed so the reproduction steps published in the report stay valid.

---

## Build and run

**Firmware** (PlatformIO, Seeed XIAO ESP32-S3):

```bash
pio run -e ble                 # main firmware  (verified: RAM 11.4%, flash 18.1%)
pio run -e ble -t upload
pio device monitor             # 115200 baud
```

**Host-side tooling** — every script is run from the repository root:

```bash
pip install -r requirements.txt

python scripts/collect/log_serial.py COM3          # pull sessions off device flash
python scripts/dataset/build_processed_dataset.py  # -> data/processed/master_dataset.csv
python scripts/train/train_activity_classifier.py  # LOGO-CV + train + save .pkl
python scripts/train/export_classifier_to_c.py     # -> firmware/ble/activity_classifier_5class.h
python scripts/analysis/lms_denoise_mvp.py         # NLMS / RLS / Wiener comparison
```

---

## Results in context

| Quantity | This project | Closest published comparison | What explains the gap |
| :--- | :--- | :--- | :--- |
| 3-class HAR, user-independent | 0.853 (n=18) | In line with single-wrist-accelerometer literature | — |
| 5-class HAR, user-independent | 0.548 (n=18) | Bao & Intille (2004): ~84% | They used **5** sensor sites incl. thigh and hip; no orientation channel here |
| Wrist PPG heart rate | MAE 27–30 bpm, 9.6% yield | TROIKA (Zhang 2015): ~2 bpm | Same site, window and metric — **515 nm green vs 880 nm infrared** |

Neither result is anomalous. Both land where the literature predicts, which is the point:
the shortfalls were traced to specific, named causes rather than left as mysteries.

---

## Honest limitations

- No working wrist heart rate monitor, and **no further software work on this hardware
  would produce one** — it needs a green-wavelength front end.
- The MPU6050's gyroscope channel was never read; the Subsystem A analysis shows that is
  exactly the missing channel blocking the 5-class target.
- One session per participant, fixed activity order, no wearing-angle calibration and no
  controlled contact pressure — so test-retest reliability is unknown.
- Ground truth was a second PPG sensor, not an ECG.

---

## Documentation

| Document | What it covers |
| :--- | :--- |
| [CHANGELOG.md](CHANGELOG.md) | Every boundary/interface decision with its reasoning, dated |
| [paper/THESIS_EN.md](paper/THESIS_EN.md) | **Full report** — 7 chapters: methodology, both subsystems, root-cause analysis, limitations |
| [paper/EVIDENCE_GUIDE.md](paper/EVIDENCE_GUIDE.md) | How to re-run every number in the report, command by command |
| [paper/activity_classifier_REPORT.md](paper/activity_classifier_REPORT.md) | Subsystem A finding, root cause and fair-baseline analysis |
| [paper/adaptive_filter_comparison_REPORT.md](paper/adaptive_filter_comparison_REPORT.md) | Subsystem B methodology, octave error and results |
| [paper/proposal_vs_reality.md](paper/proposal_vs_reality.md) | 14-item comparison of what was promised against what was delivered |
| [paper/weekly_reports/](paper/weekly_reports/) | Week-by-week record of what was built and what the results meant |
| [docs/TEAMMATE_SETUP.md](docs/TEAMMATE_SETUP.md) | Data-collection guide written for non-developer collaborators |
| [archived/README_original_2026-08-13.md](archived/README_original_2026-08-13.md) | The original development README, kept as-is |

---

## Team and scope

Three-person university project, 13 weeks (June–September 2026).

- **Hoàng Nguyễn Ngọc Giang** — firmware and FreeRTOS architecture, signal processing,
  model training and deployment, data pipeline, analysis. Everything in this repository.
- **Phan Ngọc Quốc Duy** — PCB and electrical design.
- **Trần Thanh Tùng** — mechanical/enclosure design, sensor placement.

Submitted to the Convergence Innovation Competition (Georgia Tech), Global Health and
Wellbeing track.

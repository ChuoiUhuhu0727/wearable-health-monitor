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
│   └── wrist/                 # Research data: MAX30102 on dorsal wrist
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


## Milestones

| Milestone | Week | Status |
| :--- | :--- | :--- |
| M1: FreeRTOS 4-task + BLE advertising | End of week 2 | In progress (not touched this session, leaving as-is) |
| M2: BLE streaming + dataset ≥ 10 subjects | End of week 4 | Done (N=17, see `data/processed/master_dataset.csv`) |
| M3: 5-class classifier trained + exported to firmware-ready C | End of week 7 | Done (`train_activity_classifier.py` → `export_classifier_to_c.py`; not TFLite Micro -- this project exports sklearn trees to nested if/else C directly, matching the existing `classifier.h` pattern; firmware integration still needs a human to swap it in) |
| M4: LMS adaptive filter implemented + benchmarked | End of week 7 | Done, plus RLS + Wiener also implemented for the 3-way comparison (`lms_denoise_mvp.py`) -- result: no filter beats no-filtering consistently at N=5 (pooled MAE ~27-30bpm), see CHANGELOG.md 2026-07-28 |
| M5: Fingertip vs wrist experiment complete | End of week 8 | Done -- this is what M4's `lms_denoise_mvp.py` run across all 5 dual-PPG participants answers |
| M6: Full integration test | End of week 8 | Not started |
| M7: 60-minute stability test | End of week 11 | Not started |
| M8: Technical report + paper draft | End of week 12 | In progress — both report outlines (`paper/activity_classifier_report_OUTLINE.md`, `paper/adaptive_filter_comparison_OUTLINE.md`) fully filled in, not yet submitted anywhere |
| M9: Final demo | End of week 13 | Not started |

---

## Progress Log

### 2026-07-23 — Participant log done; LOGO-CV check on the bug-1 fix (lying/sitting/standing overlap)

- Built `experiments/wrist/participant_log.csv` — all 15 valid sessions confirmed as **15 distinct participants** (protocol_version `v1_fixed_order` for all of them, activity order not yet randomized).
- Tested the proposed fix for bug 1 (mean_mag/std_mag can't separate lying/sitting/standing — confirmed with real overlapping ranges) by adding `mean_ax/mean_ay/mean_az` as features, reconstructed from `raw_accel_N.csv` using a time-based window (`logo_cv_activity_features.py`) — only possible for the 4 sessions that have raw accel capture (P01-P04).
- **LOGO-CV (leave-one-participant-out, N=4) result:** mean accuracy improves from 48.2% (baseline) to 68.2% (raw per-axis mean) or 66.1% (per-axis mean relative to each participant's own lying baseline) — confirms the orientation-feature direction is right, but **neither variant generalizes to all 4 participants**: raw absolute values fail on P03 (46.8%, no better than baseline) because P03's wearing orientation shifts their per-axis values into a different range than the other 3; the relative-to-own-baseline version fixes P03 (69.7%) but breaks P01 (45.5%, worse than baseline) by erasing the exact signal P01's raw values were exploiting well.

**Open question, not yet resolved — carrying into next session:** with only 4 raw-capture participants, there isn't enough data to tell whether raw or relative per-axis features (or some other calibration) generalizes best across wearing orientations. Is bug 1 (lying/sitting/standing separability) actually fixable with the current feature set, or does it need either (a) more raw-capture participants before picking a normalization approach, or (b) a different feature entirely (e.g., tilt angle instead of raw axis)? Don't lock in either variant yet.

**Next session:**
1. Decide: collect more raw-capture sessions before choosing an orientation-feature normalization, or explore tilt-angle features on the current 4.
2. `data/processed/` master dataset script (raw→clean from `valid_sessions/`) still not built.
3. Decide on randomizing activity order for future collection (open question from 2026-07-22, not yet resolved either way).

### 2026-07-28 — Pipeline automation, P16/P17 added (N=17), bug-1 rabbit hole closed, decided: keep 5-class

**Built:**
- `build_processed_dataset.py` — builds `data/processed/master_dataset.csv` from `valid_sessions/` + `participant_log.csv`. Adds `activity_group` (lying/sitting/standing → `stationary`, else unchanged) so either a 3-class or 5-class model can be trained without re-running this script. Outlier motion-spikes are flagged (`is_outlier_spike`) but never dropped (robust-real-world decision, 2026-07-22).
- `log_serial.py` now auto-categorizes every retrieved session right after the quality check: dry-run → `firmware_test_fixtures/`, complete+real → `valid_sessions/` with an auto-appended `participant_log.csv` row (participant_id guessed as the next sequential P-number, assuming a new participant — verify/correct by hand if it was actually a repeat visitor). Incomplete-but-real sessions (e.g. brownout-cut) are deliberately left unfiled for manual salvage/discard review. `build_processed_dataset.py` can now run immediately after `log_serial.py` with no manual step in between.
- `realtime_waveform_viewer.py` / `realtime_fft_viewer.py` — live Serial plotting (waveform + FFT) for a teammate's investigation, reusing the existing `firmware_capture/` protocol, no firmware changes.
- Repo cleanup: moved deprecated/unused files to `archived/` (not deleted), removed genuinely empty build artifacts.

**P16 and P17 added** (verified by hand — dry-run ratio 13.26/12.49, full fingertip PPG ~34k rows each, no BROWNOUT — not just trusted from the auto-tag) — `master_dataset.csv` now **N=17 participants**, and the LMS research track now has **5 participants with complete dual-PPG** (P02, P03, P04, P16, P17; P01's fingertip channel is empty, see 2026-07-17 note above) instead of 3.

**Bug-1 re-check at N=6 (added P16/P17 to the raw-capture LOGO-CV pool) — result complicated the picture, didn't resolve it:** adding these 2 participants to the training pool made P04's accuracy *worse* under the raw-enhanced feature (62.2% → 35.0%), and P16 was the worst performer under the relative-baseline variant (29.6%, worse than plain baseline). This is evidence the wearing-orientation issue may need a genuinely different feature (tilt angle) or a calibration-step protocol change, not more attempts at re-deriving orientation from already-collected, uncalibrated data.

**Advisor suggested an alternative:** train an AI model (PPG+IMU → HR end-to-end, or a PPG denoising/reconstruction model) deployed to the ESP32, instead of the classical LMS/RLS/Wiener comparison. Assessment: promising idea, but end-to-end learned models for PPG→HR typically need far more participants to generalize than classical adaptive filters do (literature benchmarks like PPG-DaLiA use ~15 participants; this project has 5 with usable dual-PPG) — recommended keeping the classical-filter comparison as the main plan (fits current data) and treating the AI-model idea as an added comparison point for later, not a replacement, given the project's current data constraints.

**Decision reached — closing the bug-1 rabbit hole:** after 3 feature variants tried across growing N (4→6) with no clean generalizing winner, further feature-engineering attempts on the *existing* data were recognized as an open-ended rabbit hole and deliberately stopped. **Keeping 5-class** (not collapsing to 3-class) — but bug 1 is no longer a blocker: train the 5-class classifier now with the current feature set, report the lying/sitting/standing confusion matrix honestly as a discussed, root-caused finding (magnitude-based features structurally can't carry orientation information), not something to keep patching before moving forward. The calibration-step protocol idea is parked as a future firmware/protocol change for *new* data collection only — it doesn't apply retroactively to the 17 already-collected sessions.

**Next session:**
1. Actually train the 5-class classifier on `master_dataset.csv` (LOGO-CV, N=17) — first real trained model, not just a feature-validity check. Report the confusion matrix as-is.
2. Proceed with the LMS/RLS/Wiener research track using the 5 dual-PPG participants — separate effort from the activity classifier.
3. AI-model idea (advisor's suggestion) — parked, revisit only if there's time/data left after the above.
4. Still open, not urgent: randomizing activity order for future collection (2026-07-22); calibration-step protocol change (2026-07-28) — both are *future data collection* changes, neither blocks current work.

### 2026-07-30 — Both tracks executed end-to-end: classifier trained+deployed+hardware-tested, LMS/RLS/Wiener compared, N=18

**Subsystem A — activity classifier, full pipeline train→export→firmware→hardware:**
- `train_activity_classifier.py` (+ `.ipynb` twin, executes cleanly, output baked in): 5-class LOGO-CV mean accuracy **0.548** (N=18). Per-class recall: lying 0.283, sitting 0.490, standing 0.548, walking 0.639, running 0.771 — lying/sitting/standing confusion confirmed as the expected bug-1 root cause (magnitude-only features are mathematically invariant to orientation; see reasoning captured in `paper/activity_classifier_report_OUTLINE.md` section 2).
- **New finding, same model/features/data, different evaluation scope:** regrouping lying/sitting/standing into one `stationary` class (via the already-existing `activity_group` column) gives **0.853** mean LOGO-CV accuracy (recall: stationary 0.951, walking 0.632, running 0.777). Not a fix to bug-1 — a demonstration that the *right-scoped* claim (movement state, not fine posture) is well supported by this feature set. Reported honestly as a secondary finding alongside the 5-class number, not a replacement (Giang's explicit decision, 2026-07-30: keep 5-class as the primary reported result).
- `export_classifier_to_c.py` → `activity_classifier_5class.h` (nested if/else, same pattern as the existing `classifier.h` — this project does NOT use TFLite Micro despite the old README roadmap wording, now corrected).
- **Wired into `firmware_ble/main.cpp`** (previously exported but never actually included/called — caught by Giang trying to flash it): swapped `#include`, changed the call site to `classifyActivity5class(meanMag, acc_std, peak_rel, peak_max)`, and **removed `ACTIVITY_GATE`** (a 150.0f threshold that forced `activity_class=0` on any quiet window — correct for the old binary model, silently wrong for a 5-class model where quiet windows are exactly when it needs to distinguish lying/sitting/standing).
- **Hardware-tested twice.** First test: walking segment invalid (participant was still attaching the fingertip sensor, not walking) — session excluded from dataset, moved to `firmware_test_fixtures/`, dropped from `participant_log.csv` (was auto-tagged P18). Second test (redone properly): all 5 activities valid, live accuracy — running 98.4%, standing 96.8%, walking 83.4%, sitting 70.2%, lying 15.5% (confused mostly with standing, 61% — same direction as the offline confusion matrix, confirms this is bug-1, not a new integration bug). This session's participant confirmed genuinely new → kept as **P18**, `master_dataset.csv` rebuilt to **N=18**. P18's fingertip channel is empty (like P01) — not usable for the LMS/RLS/Wiener track.

**Subsystem B — LMS/RLS/Wiener, built from scratch, full comparison across 5 dual-PPG participants:**
- `lms_denoise_mvp.py`: ground-truth BPM extraction went through 3 iterations before being trustworthy (naive peak-counting → implausible BPM swings → per-window spectral/FFT dominant-frequency → sometimes locked onto the PPG's own 2nd harmonic → added continuity tracking with a median-seeded burn-in to fix that). All 3 classical filters implemented: NLMS, RLS (first version diverged numerically — residual std exploded ~7e3→2e7 — from unbounded covariance growth during low-motion stretches, i.e. RLS "windup"; fixed with a covariance-reset safeguard), and batch Wiener.
- **Final pooled result (magnitude reference, N=5): baseline=26.95, NLMS=26.96, RLS=29.83, Wiener=29.96 bpm MAE. No filter beats no-filtering consistently** — the honest answer to the research question at this stage, not a pipeline failure (pipeline is bug-checked and validated).
- Two bounded follow-up experiments: (1) triaxial reference (ax/ay/az separately, 24 taps) instead of magnitude (8 taps) — made every filter substantially **worse** (likely overfitting ~45k noisy samples/session with 3x the parameters); kept magnitude as the reference. (2) investigated why RLS/Wiener fail badly on P04 specifically (46-47bpm vs 18-22bpm for baseline/NLMS) — found P04 has the highest wrist-accel correlation (r=-0.72) of any participant, a plausible but not confirmed explanation (P03 has similar correlation without failing as badly).
- Write-up: `paper/adaptive_filter_comparison_2026-07-28.md` — full methods/results/limitations, ready for the Q3 draft.

**Process note:** the 5-class vs 3-class comparison was initially run ad hoc in-chat with no saved script — Giang caught this (no file to show an advisor = not reproducible/defensible) and it was folded into `train_activity_classifier.py`/`.ipynb` properly. Lesson: every reported number needs a checked-in, re-runnable script, no exceptions, even for a "quick check".

**Next session:**
1. PR #25 (firmware wiring + hardware test cleanup) is open, **not yet merged** — review before continuing firmware work.
2. Giang to fill in `paper/activity_classifier_report_OUTLINE.md` themselves (Claude provided the skeleton + verified numbers only, not the analysis prose — explicit academic-integrity request).
3. LMS/RLS/Wiener: decide between (a) accept the null/mixed result and move to paper framing, (b) richer-reference experiment already tried and failed (don't retry triaxial without more data/session-length first), (c) investigate P04 correlation further (not blocking).
4. Activity classifier: if pursuing >85.3%/>0.548, next real lever is gyroscope + a calibration-step protocol change for *future* data collection (can't retrofit onto the 18 already-collected participants) — not another feature-engineering pass on existing data.
5. Still open, not urgent: randomizing activity order (2026-07-22).

### 2026-08-12 — Both report outlines completed; project docs restructured into per-week files

**Subsystem A (`paper/activity_classifier_report_OUTLINE.md`) — all 5 sections filled in.**
Section 1 (LOGO-CV definition + why per-class recall matters more than the 0.548 average)
written entirely by Giang, derived through Socratic Q&A. Section 2 (what the 4 features
measure, why magnitude is rotation-invariant, why the 3 earlier per-axis attempts didn't
generalize) is a mix — Giang wrote the feature redefinitions and the 3-alternatives
narrative, Claude fixed a scope error (features are computed per 2.4s window, not per
90s activity segment — `WINDOW_SIZE=60` @ `IMU_HZ=25`) and filled two flagged gaps
(rotation-invariance formula; disproving the "wrist-flip" hypothesis for Alternative 1
using the real 68.2%/P03-46.8% numbers, since the hypothesis can't explain why only P03
failed). Sections 3-5 written directly by Claude at Giang's explicit request (not
Socratic this time) — added a real majority-class baseline computed via new script
`check_majority_baseline.py` (5-class baseline 0.201 ≈ random; 3-class baseline 0.599,
since `stationary` absorbs 3/5 original classes) showing the raw 0.548→0.853 comparison
overstates the improvement; Giang's own two-layer model idea (gyro for the static
classes, keep the existing decision tree for walking/running) captured as a cheaper
alternative to the gyro+calibration proposal.

**Subsystem B (`paper/adaptive_filter_comparison_2026-07-28.md`) converted to an
outline**, same academic-integrity treatment as subsystem A (Giang confirmed subsystem
B's report is also graded, not just a free-standing writeup as originally assumed). Old
full Claude-written draft renamed to `..._CLAUDE_REFERENCE.md`, marked NOT FOR
SUBMISSION, kept only as a numbers/methodology reference. New
`paper/adaptive_filter_comparison_OUTLINE.md` has the same tables/numbers, prompts
instead of analysis.

**Docs restructured — split by week, doesn't affect code:**
- New `paper/weekly_reports/week_05.md`…`week_13.md` — retrospective "what was actually
  done, what the results mean" reports (not plans), reconstructed from git log +
  `CHANGELOG.md` + this Progress Log, compressed by content into the 9 week-labels since
  real commit activity only spans ~5 calendar weeks (2026-06-27 → 2026-08-01) against the
  original 9-week span. Written for a non-technical advisor — each bullet has a plain-
  language "Ý nghĩa" (significance) explanation alongside the technical one.

**Next session:**
1. PR #25 still needs checking (see 2026-07-30 entry) — may already be merged, verify.
2. Giang to do a final read-through of `activity_classifier_report_OUTLINE.md` sections
   3-5 (Claude-authored) before submitting — confirm understanding well enough to explain
   to the advisor, per the outline's own reproducibility checklist.
3. Pending fact-check from 2026-08-12 session (not yet confirmed): does every participant
   wear the watch in the same fixed orientation? If true, may reopen part of the bug-1
   wearing-angle-confound explanation — do not act on this until Giang confirms.

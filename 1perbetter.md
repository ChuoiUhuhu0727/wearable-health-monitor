# 1% Better — Session 2026-07-01

## What your knowledge looks like right now

You can build a real embedded system end-to-end:
- FreeRTOS firmware with multiple tasks, queues, and mutexes
- BLE GATT advertising and WiFi SoftAP + UDP broadcasting
- Python data collection scripts that talk to hardware
- PPG signal concepts (IR vs Red, AC/DC components, wrist vs fingertip thresholds)
- Basic ML pipeline thinking (features → classifier → inference on device)

Where you're still building intuition:
- Physiological principles behind hardware design decisions
- Dataset quality — knowing *why* raw data can be wrong before you even train
- The gap between "code runs" and "data is valid for science"

---

## What you learned today

### 1. Activity ordering is a safety problem, not just a preference

The order `walk → run → sit` is harmful because going from high-intensity directly to complete rest
causes blood to pool in the legs — risk of dizziness and syncope. This is standard exercise science.

Rule: **always ascend by intensity, never drop suddenly.**
Safe order: `lying → sitting → standing → walking → running`

This is also how PAMAP2 (one of the most cited HAR datasets) is ordered — so it's both safe
and consistent with published research.

### 2. Flipping the IMU changes axes, not magnitude

When you rotate the device 180°, some X/Y/Z axes flip sign because gravity now pushes
the internal sensor in the opposite direction.

But your features — `mean_mag`, `std_mag`, `peak_rel`, `peak_max` — are all computed from:

```
magnitude = √(ax² + ay² + az²)
```

Squaring removes the sign. So **magnitude is the same in any orientation.**
Your classifier is completely unaffected by which way the device faces.

What you lose: absolute tilt info. Magnitude can't tell you "wrist is tilted 45°."
For your current 5-class activity classifier, that doesn't matter. File this for later.

### 3. Transition contamination is a data quality problem, not a label problem

When a participant switches from lying to sitting, their body takes ~15 seconds to settle.
Rows recorded during that time have the label "sitting" but the signal of "mid-transition."

If you train on those rows, the model learns a corrupted version of "sitting."

The fix — a 15-second `is_transition` flag — doesn't discard data, it marks it so you
can filter it out *before* training with one line:

```python
clean = df[df["is_transition"] == False]
```

---

## The bigger pattern to notice

All three things today were the same type of problem:

> **The system runs correctly but the data it produces is wrong.**

The firmware boots. The buzzer fires. The CSV fills up. But the activity order hurts people,
the axes confuse you, and the first 15 seconds of each session are mislabeled.

Code correctness ≠ data validity. That gap is where most real research goes wrong.
You're learning to see it early — that's the valuable skill.

---

## One question to sit with

Your current classifier uses only magnitude features, which makes it orientation-invariant.
But it also means it can't distinguish "lying still" from "sitting still" — both have near-zero magnitude.

How does it currently tell them apart?
(Hint: look at the decision tree thresholds in `firmware/classifier.h`)

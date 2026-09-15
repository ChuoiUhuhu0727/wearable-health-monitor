# scripts/

Host-side tooling. **Run every script from the repository root**, not from inside these
folders — paths inside the scripts (`experiments/wrist`, `data/processed/…`,
`models/…`) are relative to the working directory:

```bash
python scripts/dataset/build_processed_dataset.py     # correct
cd scripts/dataset && python build_processed_dataset.py   # will not find the data
```

## Grouping rule

Scripts are grouped by **what they depend on**, not by what they produce.

| Folder | Contents | Notes |
| :--- | :--- | :--- |
| `collect/` | Pull sessions off device flash, BLE live view, one-off waveform capture | Needs the device connected |
| `dataset/` | Raw sessions → `data/processed/master_dataset.csv`, readiness checks | Run after every collection round |
| `train/` | LOGO-CV training and evaluation, export to a C header | `export_classifier_to_c.py` writes straight into `firmware/ble/` |
| `analysis/` | Subsystem B pipeline and everything that imports it | **One coupled cluster — do not split** |
| `report/` | Diagram generators and markdown → docx conversion | No dependency on the analysis cluster |
| `viz/` | Session plots, raw waveform plots, live serial viewers | Standalone |

## Why `analysis/` must stay in one folder

These modules import each other as siblings, which only works while they share a
directory:

```
lms_denoise_mvp.py            (base: constants, loading, filters, pipeline)
   ├── hr_estimator_v2.py         imports it  ──┐
   ├── check_ground_truth_sanity.py             │
   ├── check_hr_information_baseline.py         │
   └── lms_denoise_v2.py          imports both ─┘
          └── plot_figures_en.py, plot_filter_results_v2.py,
              plot_input_signals.py, plot_waveform_to_features.py
```

Moving any one of them into another folder breaks the import chain. The figure scripts
live here rather than in `report/` for exactly that reason — they re-run the pipeline to
produce their plots.

## Typical order

```bash
python scripts/collect/log_serial.py COM3          # 1. retrieve sessions
python scripts/dataset/build_processed_dataset.py  # 2. build the dataset
python scripts/train/train_activity_classifier.py  # 3. LOGO-CV + train
python scripts/train/export_classifier_to_c.py     # 4. -> firmware/ble/activity_classifier_5class.h
python scripts/analysis/lms_denoise_mvp.py         # Subsystem B: first comparison
python scripts/analysis/check_ground_truth_sanity.py   #   is the reference trustworthy?
python scripts/analysis/lms_denoise_v2.py          #   re-measure with the fixed estimator
```

See [paper/EVIDENCE_GUIDE.md](../paper/EVIDENCE_GUIDE.md) for what each command should print.

"""
Does the wrist PPG signal carry ANY recoverable heart-rate information at all?

WHY THIS SCRIPT EXISTS
    lms_denoise_mvp.py establishes that no adaptive filter (NLMS/RLS/Wiener) beats
    doing nothing. That result has two competing explanations, and they lead to
    completely different conclusions:

      (a) The three filters are the wrong tool -- the information is present in the
          wrist signal, but these algorithms fail to recover it.
      (b) There is almost nothing to recover -- the wrist channel barely encodes
          heart rate under these conditions, so no filter could have succeeded.

    Comparing the filters against each other cannot distinguish (a) from (b), because
    every one of those estimators reads the wrist sensor. To separate them we need a
    reference point that ignores the wrist sensor entirely.

THE TEST
    Compare the unfiltered wrist estimate against estimators that never look at the
    wrist at all:

      Global constant     always predict the median heart rate of the whole dataset.
                          Knows nothing -- not the sensor, not the person.
      Per-person constant always predict that participant's own median heart rate.
                          Knows the person's typical rate, still ignores the sensor.
      Random guess        uniform draw from the 42-210 bpm search band the estimator
                          itself uses. The floor of "no information whatsoever".

    If the wrist estimate cannot clearly beat a constant that ignores the sensor,
    then explanation (b) holds and the negative filter result is a property of the
    measurement, not of the algorithms.

    This mirrors check_majority_baseline.py in the activity-classifier track: an
    error figure means nothing until compared against what a model that ignores the
    input would score.

INPUT
    Reuses run_pipeline() from lms_denoise_mvp.py (magnitude reference mode), so the
    ground-truth BPM series is identical to the one the filter comparison uses --
    no re-derivation, no chance of the two scripts disagreeing.

USAGE
    python scripts/analysis/check_hr_information_baseline.py
"""
import numpy as np
import pandas as pd

from lms_denoise_mvp import PARTICIPANTS, run_pipeline

RNG_SEED = 0
BAND_LO_BPM, BAND_HI_BPM = 42.0, 210.0  # same search band as spectral_bpm()


def main():
    df = pd.concat([run_pipeline(pid, files, "magnitude")
                    for pid, files in PARTICIPANTS.items()], ignore_index=True)
    df = df.dropna(subset=["gt_bpm", "base_bpm"])

    gt = df["gt_bpm"].to_numpy()
    print("\n" + "=" * 68)
    print("DOES THE WRIST SIGNAL CARRY HEART-RATE INFORMATION?")
    print("=" * 68)
    print(f"\nWindows: {len(df)} | participants: {df['participant_id'].nunique()}")
    print(f"Ground-truth BPM (fingertip): median {np.median(gt):.1f}, "
          f"range {gt.min():.1f}-{gt.max():.1f}, IQR "
          f"{np.percentile(gt, 25):.1f}-{np.percentile(gt, 75):.1f}")

    # --- estimators that DO read the wrist sensor ---
    mae_wrist = df["base_err"].mean()
    mae_nlms = df["lms_err"].mean()

    # --- estimators that DO NOT read the wrist sensor ---
    mae_global_const = np.abs(gt - np.median(gt)).mean()

    per_person = df.groupby("participant_id")["gt_bpm"].transform("median")
    mae_person_const = (gt - per_person).abs().mean()

    rng = np.random.default_rng(RNG_SEED)
    mae_random = np.abs(gt - rng.uniform(BAND_LO_BPM, BAND_HI_BPM, size=len(gt))).mean()

    rows = [
        ("Random guess in 42-210 bpm band", mae_random, "không"),
        ("Global constant (median of all)", mae_global_const, "không"),
        ("Per-person constant (own median)", mae_person_const, "không"),
        ("Wrist PPG, unfiltered", mae_wrist, "CÓ"),
        ("Wrist PPG + NLMS filter", mae_nlms, "CÓ"),
    ]
    print(f"\n{'Estimator':<34}{'MAE (bpm)':>11}   {'Đọc cảm biến cổ tay?':>20}")
    print("-" * 68)
    for name, mae, reads in sorted(rows, key=lambda r: -r[1]):
        print(f"{name:<34}{mae:>11.2f}   {reads:>20}")

    print("\n--- Kết luận ---")
    gap_const = mae_global_const - mae_wrist
    gap_person = mae_person_const - mae_wrist
    print(f"Cổ tay so với hằng số toàn cục : {gap_const:+.2f} bpm "
          f"({'tốt hơn' if gap_const > 0 else 'TỆ HƠN'})")
    print(f"Cổ tay so với hằng số từng người: {gap_person:+.2f} bpm "
          f"({'tốt hơn' if gap_person > 0 else 'TỆ HƠN'})")

    if gap_person <= 0:
        print("\n=> Ước lượng từ cổ tay KHÔNG thắng nổi một hằng số bỏ qua hoàn toàn")
        print("   cảm biến. Kết luận (b): tín hiệu gần như không mang thông tin nhịp")
        print("   tim để khôi phục — đây là giới hạn của phép đo, không phải của")
        print("   thuật toán lọc.")
    else:
        print("\n=> Ước lượng từ cổ tay CÓ thắng hằng số, nghĩa là tín hiệu vẫn mang")
        print("   một phần thông tin nhịp tim. Chưa loại trừ được kết luận (a).")

    # A constant predictor looks good partly because 3 of the 5 activities are at rest,
    # where heart rate genuinely barely moves. The demanding case is running, where the
    # true rate climbs far away from any constant. If the wrist signal carries usable
    # information anywhere, it should show up there -- so check that separately rather
    # than letting the pooled figure settle the question.
    print("\n=== Kiểm tra ngược: liệu cổ tay có thắng ở hoạt động mạnh không? ===")
    per_act = df.groupby("label").apply(
        lambda g: pd.Series({
            "gt_median": g["gt_bpm"].median(),
            "gt_max": g["gt_bpm"].max(),
            "wrist_mae": g["base_err"].mean(),
            "const_mae": (g["gt_bpm"] - np.median(gt)).abs().mean(),
        }), include_groups=False)
    per_act["cổ tay tốt hơn?"] = np.where(
        per_act["wrist_mae"] < per_act["const_mae"], "CÓ", "không")
    order = [a for a in ["lying", "sitting", "standing", "walking", "running"]
             if a in per_act.index]
    print(per_act.reindex(order).to_string(float_format=lambda v: f"{v:.2f}"))

    won = per_act.loc[per_act["cổ tay tốt hơn?"] == "CÓ"].index.tolist()
    if won:
        print(f"\n   Cổ tay thắng hằng số ở: {', '.join(won)} — tức là tín hiệu KHÔNG")
        print("   hoàn toàn rỗng, nó còn thông tin ở đúng vùng vận động mạnh.")
    else:
        print("\n   Cổ tay thua hằng số ở TẤT CẢ hoạt động, kể cả chạy — nơi nhịp tim")
        print("   lệch xa nhất khỏi hằng số. Không còn vùng nào để bào chữa.")

    print("\n=== Chi tiết theo từng participant ===")
    per_p = df.groupby("participant_id").apply(
        lambda g: pd.Series({
            "gt_median": g["gt_bpm"].median(),
            "wrist_mae": g["base_err"].mean(),
            "const_mae": (g["gt_bpm"] - g["gt_bpm"].median()).abs().mean(),
        }), include_groups=False)
    per_p["cổ tay tốt hơn?"] = np.where(per_p["wrist_mae"] < per_p["const_mae"], "có", "KHÔNG")
    print(per_p.to_string(float_format=lambda v: f"{v:.2f}"))


if __name__ == "__main__":
    main()

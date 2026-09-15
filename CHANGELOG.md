# Changelog — quyết định ở mức boundary/interface

## 2026-09-15 — Export model ghi thẳng vào firmware/ble/, bỏ bản copy ở repo root
`export_classifier_to_c.py` đổi OUT_PATH từ `activity_classifier_5class.h` (root) sang
`firmware/ble/activity_classifier_5class.h` — trước đây sinh ra ở root rồi copy tay sang
firmware, 2 bản dễ trôi lệch mà không ai biết. Giờ chỉ còn 1 bản, nằm đúng chỗ build đọc.

## 2026-09-15 — Sắp xếp lại cây thư mục: firmware/, scripts/, docs/ + README mới cho nhà tuyển dụng
Firmware gom vào `firmware/{ble,baseline,capture}` (platformio `src_dir = firmware`, `default_envs`
baseline → ble); 25 script Python ở root gom vào `scripts/{collect,dataset,train,analysis,report,viz}`
— **mọi lệnh gọi script đổi đường dẫn**, đã cập nhật lại trong `paper/*.md` + `docs/TEAMMATE_SETUP.md`,
vẫn phải chạy từ gốc repo vì path trong script là relative theo CWD. Cụm `lms_denoise_mvp` /
`hr_estimator_v2` / `lms_denoise_v2` / `check_*` / 4 `plot_*` import lẫn nhau kiểu sibling nên buộc
phải nằm chung `scripts/analysis/` — tách ra là vỡ import (ghi rõ trong `scripts/README.md`).
`experiments/` và `data/processed/` giữ nguyên chỗ cũ có chủ đích, để phần tái lập kết quả trong
thesis/EVIDENCE_GUIDE không sai. `firmware_main/` + `jetson_server/` vào `archived/`; README cũ
thành `archived/README_original_2026-08-13.md`, README mới có bản EN (mặc định) + `README.vi.md`.
Verify: 3 env firmware build PASS, toàn bộ script compile, path constant + link doc trỏ đúng file thật.

## 2026-08-15 — Ground truth nhịp tim bị bác bỏ và thay bằng estimator v2
`spectral_bpm()` trong `lms_denoise_mvp.py` bám vào subharmonic (P17 lúc chạy: báo 77 bpm
trong khi đếm tay ra 156), rồi `MAX_JUMP_BPM=25` khoá cứng sai số đó lại — nên **mọi con số
MAE của research track đều đo bằng thước hỏng**. Thay bằng `hr_estimator_v2.py`: đo trung vị
khoảng cách đỉnh trong miền thời gian, trả về NaN khi nhịp quá không đều, bỏ ràng buộc liên
tục. Đây là đổi hợp đồng dữ liệu: ground truth giờ **có thể vắng mặt**, mọi script tiêu thụ
nó phải xử lý NaN thay vì giả định luôn có giá trị.

## 2026-08-14 — check_majority_baseline.py tính baseline trên sai tập dòng
Script này tính baseline trên toàn bộ 20.258 dòng, trong khi `train_activity_classifier.py`
train/eval trên 16.880 dòng đã lọc `is_transition == 1` — hai con số đem so với nhau nhưng
mô tả hai tập dữ liệu khác nhau. Đã thêm bộ lọc cho khớp; kết luận không đổi (baseline
0.2007→0.2006 và 0.5991→0.5995, biên vượt baseline vẫn +0.347 / +0.254).

## 2026-07-29 — Test firmware_ble model 5-class trên hardware thật + loại session test khỏi dataset
Flash `firmware_ble` (đã sửa 2026-07-28) lên board thật, thu 1 session để kiểm tra
`activity_class` có hoạt động đúng không. Kết quả: running (99%) và standing (76%) live
chính xác, thậm chí tốt hơn LOGO-CV offline; lying/sitting vẫn bị nhầm nặng sang standing —
**đúng hướng nhầm đã thấy trong confusion matrix lúc train** (không phải bug integration
mới, confirm đúng bug-1 đã root-cause). Riêng đoạn "walking" bị đoán thành standing 95% —
điều tra ra không phải bug: participant thực ra đứng yên đeo lại sensor lúc đó, không đi bộ
thật (std_mag đo được ~23, thấp hơn 10 lần so với walking lúc train ~265) — không phải finding
thật, do lỗi thực hiện protocol.
**Loại session này khỏi dataset**: chuyển 4 file (`session_2_20260729_112314.csv` +
raw_accel/raw_ppg/raw_ppg2 đi kèm) từ `valid_sessions/` sang `firmware_test_fixtures/`, xoá
dòng `P18` khỏi `participant_log.csv` — vì mục đích thu là test firmware, không phải data
thật, và đoạn walking không hợp lệ. **Gap phát hiện**: `log_serial.py` auto-file hiện không
phân biệt được "session thu thật" với "session thu để test code" — session hoàn chỉnh nào
cũng bị tự gán participant_id mới. Chưa sửa auto-filer (ngoài phạm vi hôm nay), chỉ dọn tay
lần này — nếu việc này lặp lại thường xuyên, cân nhắc thêm 1 flag thủ công lúc thu.

## 2026-07-28 — `firmware_ble` chuyển sang model 5-class thật (đổi ý nghĩa field `activity_class`)
Trước đó chỉ export `activity_classifier_5class.h` ra chứ chưa gắn vào firmware nào — vịt
flash thử mới phát hiện `main.cpp` vẫn gọi `classifySignal()` (model binary cũ) không đổi gì.
Giờ sửa `firmware_ble/main.cpp`: đổi `#include "classifier.h"` → `#include "activity_classifier_5class.h"`
(copy file vào `firmware_ble/` vì PlatformIO include theo thư mục cục bộ, không phải path chung),
đổi call site sang `classifyActivity5class(meanMag, acc_std, peak_rel, peak_max)`. **Field
`activity_class` trong BLE JSON payload + session CSV đổi ý nghĩa: trước là binary (0=normal,
1=intense), giờ là 0=lying/1=running/2=sitting/3=standing/4=walking** — đã check `log_ble.py`/
`log_serial.py`/`visualize_session.py`, không ai diễn giải giá trị này theo nghĩa binary (chỉ
pass-through), nên không cần sửa gì phía Python. Cũng **xoá bỏ `ACTIVITY_GATE`** (150.0f
threshold ép activity_class=0 khi acc_std thấp) — logic này đúng cho model binary cũ ("đứng
yên = normal") nhưng SAI cho model 5-class (đứng yên chính là lúc cần phân biệt lying/sitting/
standing, ép về 0 sẽ luôn báo "lying" bất kể tư thế thật). Model cũ (`classifier.h`) vẫn còn
file trong `firmware_ble/` nhưng không còn được include — giữ lại làm tham chiếu, không xoá.
Chỉ áp dụng cho `firmware_ble` — `firmware_main`/`firmware_baseline_evaluate` chưa đụng tới,
vẫn dùng model binary cũ.

## 2026-07-28 — Export model 5-class sang C (`activity_classifier_5class.h`) + cập nhật milestone README
`export_classifier_to_c.py` đọc `models/activity_classifier.pkl`, sinh code C if/else lồng
nhau y hệt pattern đã có sẵn ở `classifier.h` (3 firmware hiện tại dùng cách này, KHÔNG phải
TFLite Micro như README roadmap cũ ghi — sự thật đã lệch khỏi roadmap, cập nhật lại cho đúng).
File mới **không đụng** `classifier.h` cũ (model binary 3-feature, đang chạy thật trên 3
firmware) — việc tích hợp model 5-class mới vào firmware nào, khi nào, là quyết định của vịt,
chưa tự động làm. Cũng cập nhật bảng Milestones trong README: M2 (dataset ≥10 subjects), M4
(LMS benchmarked — giờ có cả RLS/Wiener), M5 (fingertip vs wrist experiment) đánh dấu Done vì
đã hoàn thành trong session hôm nay/trước đó nhưng chưa từng update bảng; M3 đổi mô tả từ
"TFLite Micro" sang đúng thực tế (C export), đánh dấu Done phần train+export, còn chờ tích hợp
firmware. M1 giữ nguyên "In progress" — không đụng tới trong session này.

## 2026-07-28 — 2 thử nghiệm bounded cuối cho research track: reference 3-trục (thất bại) + manh mối P04 (chưa trọn vẹn)
Refactor `nlms_filter`/`rls_filter`/`wiener_filter` nhận chung 1 "lagged design matrix"
(`build_lagged()`, trước đó Wiener đã tự làm việc này) thay vì tự quản buffer riêng — cho
phép cả 3 filter dùng chung interface bất kể reference là 1 kênh (magnitude) hay nhiều kênh.
**Thử nghiệm 1 — reference 3 trục (ax/ay/az riêng thay vì magnitude gộp):** giả thuyết "gộp
magnitude mất thông tin hướng" — kết quả NGƯỢC LẠI, pooled MAE mọi filter đều tệ hơn hẳn
(LMS 26.96→37.44, RLS 29.83→37.65, Wiener 29.96→35.41; baseline không đổi 26.95 vì không phụ
thuộc reference). Root cause suy đoán: 24 tap thay vì 8 tap, quá nhiều tham số so với lượng
data 1 session (~45k mẫu, SNR thấp) → overfit nhiễu. Kết luận: giữ magnitude, không dùng
triaxial. **Thử nghiệm 2 — vì sao P04 làm RLS/Wiener tệ hẳn (46-47bpm) trong khi baseline/LMS
ổn (18-22bpm):** đo correlation(wrist_bp, accel_bp) mỗi participant — P04 cao nhất (-0.72),
gợi ý RLS/Wiener (fit khít gần chính xác) có thể đang "ăn" cả tín hiệu tim thật lẫn artifact
khi 2 tín hiệu tương quan mạnh, trong khi NLMS (điều chỉnh lỏng, dần dần) ít hại hơn. **Nhưng
P03 có correlation gần tương đương (-0.47) mà không sập nặng như P04** — giả thuyết có cơ sở
nhưng chưa giải thích trọn vẹn, dừng lại ở đây, không đào thêm. Research track coi như hoàn
tất pha MVP cho hôm nay — [[project-next-session]].

## 2026-07-28 — Thêm Wiener, hoàn tất so sánh 4 nhánh (baseline/LMS/RLS/Wiener) trên 5 participant — KHÔNG có thuật toán nào thắng rõ ràng
`wiener_filter()` — batch Wiener-Hopf (giải normal equations 1 lần trên toàn bộ recording,
KHÔNG online/adaptive như LMS/RLS), cùng n_taps=8 để so sánh công bằng, có regularization
ridge (cùng rủi ro ill-conditioned như bug RLS windup, ở đây là ma trận R gần suy biến thay
vì đệ quy nổ số). **Kết quả pooled MAE cuối cùng: baseline=26.95, LMS=26.96, RLS=29.83,
Wiener=29.96 (bpm)** — baseline và LMS gần như hoà, RLS/Wiener nhỉnh tệ hơn. Mỗi participant
có "filter thắng" khác nhau (P02→LMS, P03→RLS, P04→LMS, P16→RLS, P17→Wiener), không có mẫu
số chung. **Kết luận trung thực cho pha MVP của research track:** với tham số hiện tại
(8-tap FIR, accel magnitude làm reference duy nhất, session ~7.5 phút, N=5 participant),
chưa thuật toán classical nào chứng minh được lợi ích nhất quán so với không lọc gì. Đây là
kết quả thật để viết vào paper (Q3 target), không phải thất bại của quy trình — [[project-next-session]].

## 2026-07-28 — Thêm RLS vào `lms_denoise_mvp.py`, bắt + sửa bug windup số học
RLS đầu tiên chạy nổ số hoàn toàn (residual std 7e3 → 2.3e7 trong 1 session 450s) — root
cause: λ=0.99 khiến ma trận P tăng không giới hạn (~148x mỗi 5s) trong các đoạn accel gần-
phẳng (đúng finding case-b hồi trước trong session này: lying/sitting/standing có std_mag
thấp) mà không đủ excitation để ghìm P lại — RLS "windup" kinh điển. Fix: reset P về giá trị
ban đầu khi trace(P) vượt ngưỡng (`RLS_TRACE_RESET`), cộng re-symmetrize P mỗi bước. Sau fix,
RLS về lại thang đo hợp lý: pooled MAE=29.83bpm (so baseline=26.95, LMS=26.96) — RLS thắng
nhiều participant hơn (3/5: P03/P16/P17) nhưng thua đậm ở P04 (46.06) kéo trung bình xuống.
Không kết luận thuật toán nào thắng rõ ràng — cả 3 vẫn quanh 27-30bpm, chưa đủ chính xác lâm
sàng. Còn Wiener (bước cuối trong so sánh 3 thuật toán) chưa làm — [[project-next-session]].

## 2026-07-28 — `lms_denoise_mvp.py` mở rộng ra 5 participant: LMS KHÔNG thắng nhất quán (pooled MAE gần như hoà)
Sau khi sửa peak-detection qua 3 vòng (range-gate → spectral FFT → continuity-tracking
+ burn-in — xem entry trước) và thấy LMS thắng rõ trên P02 (24.0 vs 29.6 bpm MAE), chạy
tiếp trên cả 5 participant dual-PPG (P02/P03/P04/P16/P17, refactor `run_pipeline()` tái
dùng theo participant thay vì hardcode 1 người). **Kết quả P02 KHÔNG generalize**: pooled
MAE baseline=26.95 vs LMS=26.96 — gần như hoà. 3/5 participant LMS giúp (P02/P04/P16),
2/5 làm tệ hơn (P03/P17). Theo activity: LMS giúp lying/walking, hại sitting/running.
**Kết luận trung thực cho giai đoạn này:** với NLMS tham số hiện tại (8 tap, mu=0.5) +
pipeline BPM hiện tại (vẫn còn sai 20-35bpm, chưa đủ tin cậy tuyệt đối), chưa thể kết
luận LMS có lợi ích nhất quán qua participant. Không phải thất bại của thí nghiệm — đây
đúng là lý do phải test nhiều người thay vì tin 1 kết quả đơn lẻ — nhưng means bài báo
Q3 chưa có câu chuyện "LMS thắng" để viết, cần RLS/Wiener so sánh thêm hoặc debug sâu
hơn per-participant (P03/P17 tệ hơn — vì sao khác P02/P04/P16?) trước khi kết luận.

## 2026-07-28 — Bắt đầu track LMS/RLS/Wiener: `lms_denoise_mvp.py` (P02, LMS only) — peak-detection CHƯA đủ tin cậy
MVP đầu tiên cho research track: resample raw wrist/fingertip/accel (P02, keyed bằng
`elapsed_ms`) lên grid chung 100Hz, bandpass 0.7-3.5Hz, peak-detect để tính BPM tức thời,
so BPM lỗi (MAE) giữa baseline (wrist thô) và NLMS (accel làm reference) theo từng activity.
**Kết quả chưa dùng được:** sanity-check ground-truth (fingertip) so với cột `bpm` on-device
cho thấy BPM tức thời nhảy phi thực tế (53→125→133→18.5 bpm liên tiếp lúc đang nằm yên) — đã
thêm 1 lớp lọc range sinh lý (40-180bpm) trong `instantaneous_bpm()`, cải thiện nhẹ (baseline
MAE 24.1→21.4bpm) nhưng KHÔNG đủ — MAE tổng vẫn >20bpm, quá cao để tin. Quyết định: **peak-
detection method cần làm lại (khác hẳn heuristic prominence-threshold hiện tại) trước khi so
sánh LMS/RLS/Wiener** — không phải bug riêng của LMS, filter nào cũng cần ground-truth này.
Dừng ở đây theo đúng nguyên tắc anti-rabbit-hole, không tiếp tục vá tham số — [[project-next-session]].

## 2026-07-28 — Thêm bước pipeline mới: `train_activity_classifier.py` → `models/activity_classifier.pkl`
Pipeline giờ có thêm 1 bước sau `data/processed/`: train 5-class DecisionTree (LOGO-CV,
N=17) và export model ra `models/activity_classifier.pkl`, tái chạy được bất cứ lúc nào,
không sửa tay. Kết quả: mean accuracy 0.547/17-fold, lying/sitting/standing confuse nặng
(lying recall 0.283 — đúng root cause bug-1 đã đóng: magnitude không mang thông tin hướng
đeo), walking/running tách tốt (0.639/0.771). Đây là kết quả cuối cùng được báo cáo trung
thực, không phải bug cần vá tiếp — [[project-next-session]].
Riêng track LMS/RLS/Wiener: check nhanh `std_mag` (`check_accel_variance_by_activity.py`)
cho thấy accel reference lúc static (lying/sitting/standing) KHÔNG phẳng tuyệt đối, chỉ thấp
hơn dynamic ~15x (median) — không lo RLS mất ổn định số học, nhưng nên tách báo cáo
static/dynamic riêng khi so sánh 3 thuật toán lọc, đừng gộp chung.

File này **không phải** thay cho `git log` — git log ghi từng dòng code đổi gì,
còn file này chỉ ghi lại những chỗ **hợp đồng giữa 2 phần** của hệ thống bị đổi
(schema data, giao thức giữa firmware/script, kiến trúc chuyển transport, v.v.) —
những thứ mà nếu không biết thì phần còn lại của hệ thống sẽ vỡ ngầm.

Mỗi entry chỉ 2-3 dòng: **đổi gì** + **tại sao**. Không ghi chi tiết implementation.

---

## 2026-07-28 — `log_serial.py` tự phân loại session + tự đề xuất participant_id
Sau mỗi lần retrieve, `log_serial.py` giờ tự áp rule dry-run (2026-07-22) + check độ
đầy đủ, rồi tự dời file: dry-run → `firmware_test_fixtures/`, hoàn chỉnh → `valid_sessions/`
kèm tự thêm 1 dòng vào `participant_log.csv`. Session cụt-nhưng-có-thật (kiểu brownout,
không phải dry-run) **không** tự dời — để nguyên chờ quyết định salvage/bỏ bằng tay,
vì rule không đủ để tự quyết đúng trường hợp này.
`participant_id` của dòng mới được **tự đoán** (số P tiếp theo, giả định participant mới)
thay vì để trống — để `build_processed_dataset.py` chạy được ngay không cần sửa tay giữa
2 bước, đổi lại: nếu hôm đó là người quay lại lần 2 (không phải người mới), phải tự sửa lại
ID cho đúng sau — đây là quyết định đánh đổi tốc độ lấy rủi ro sai nhỏ, chấp nhận được vì
sửa sau dễ hơn nhiều so với dựng lại participant log từ đầu (đã từng phải làm, tốn nhiều
công hơn hẳn).

## 2026-07-22 — Rule loại session không có activity thật; chia `experiments/wrist/` thành `valid_sessions/`/`firmware_test_fixtures/`
Phát hiện qua plot (`session_4_20260717_163545.csv`): accel phẳng tuyệt đối suốt "running"
(đáng lẽ phải dao động mạnh nhất) — thiết bị nằm yên trên bàn, không ai đeo, chỉ có state
machine tự chuyển label theo thời gian. Mã hoá thành rule kiểm tra toàn bộ 21 session
"hoàn chỉnh": `median(std_mag | running) / median(std_mag | lying) < 3` → nghi ngờ không phải
activity thật. 6/21 session bị flag (2 đã visual-confirm, 4 còn lại tin theo rule, chưa
plot). Đã chuyển 6 file này (`session_1_20260710_134540`, `session_2_20260714_185529`,
`session_3_20260714_170107`, `session_5_20260714_170110`, `session_3_20260717_163426`,
`session_4_20260717_163545`, cùng raw_accel/raw_ppg/raw_ppg2 đi kèm nếu có) sang
`experiments/wrist/firmware_test_fixtures/` — không xoá, vẫn dùng được làm test fixture cho
pipeline/firmware (đã biết trước "đáp án đúng" là không có activity thật) và đo noise floor
cảm biến. 15 session còn lại (activity thật, đã pass rule) chuyển sang
`experiments/wrist/valid_sessions/` — đây là tập dùng để process/train tiếp. Thêm
`session_manifest.csv` ghi rõ status + lý do cho từng session.

## 2026-07-22 — Quyết định: giữ transition buffer 15s, không lọc motion-spike tự nhiên khỏi dataset
So sánh chi phí trước khi quyết: tăng buffer 15s→20s chỉ phòng hờ 1 rủi ro chưa đo được
chính xác (PPG settle time sau transition — không đo nổi do raw capture mất mẫu không đều,
~72-79Hz thực tế thay vì 100Hz danh định), nhưng ăn hết data của đúng các session bị
brownout cắt giữa chừng (`session_1_20260717_173122.csv` sẽ mất 100% dòng sạch còn lại của
đoạn standing) — giữ 15s. Outlier check (`mean_mag > median + 3×1.4826×MAD`, tính riêng theo
từng session×activity) trên 21 session hoàn chỉnh cho thấy 6.34% dòng có "spike" tự nhiên,
dàn trải đều across sessions (0.5%-13.9%, không có session nào bất thường hẳn) — quyết định
GIỮ NGUYÊN, không lọc, vì model nhắm tới robust real-world detection, không phải lab-clean.

## 2026-07-22 — Raw data cố định trong `experiments/`, dataset đã xử lý sang `data/processed/`
Toàn bộ `experiments/wrist/*.csv`/`*.log` (session thu 17/7-20/7) trước đó chỉ tồn tại trên ổ
đĩa local, chưa từng commit — đã backup vào git. Từ giờ: `experiments/` là raw, bất khả xâm
phạm (không script nào được sửa/xoá file trong đó); mọi dataset đã lọc/gắn participant_id/thêm
feature mới phải ghi ra `data/processed/` (thư mục mới, sinh ra từ script chạy lại được, không
sửa tay) — theo đúng pattern `data/raw` vs `data/processed` đã dùng ở project Aikido cũ.

## 2026-07-17 — Known issue: BLE `TimeoutError()`/disconnect dù participant đứng sát laptop
Ghi nhận lúc thu participant thật đầu tiên: comment cũ trong `setupBLE()` (2026-07-10)
đoán BLE drop là "real-RF symptom, body attenuation/antenna orientation" — giả định
ngầm là chỉ xảy ra khi ở xa. Lần này drop xảy ra ngay cả khi đứng sát máy, giả định đó
có thể sai — chưa root-cause. **Không ảnh hưởng data**: kiến trúc flash-trước-BLE-sau
([[data-collection-pipeline-v2]]) nghĩa là session vẫn ghi đủ vào flash bất kể BLE có
rớt hay không — để fix sau, không chặn việc thu data tiếp.

## 2026-07-17 — Custom partition table cho `firmware_ble` (LittleFS 1.5MB → 4.94MB)
Đo trực tiếp trên board: partition mặc định chỉ cấp 1.5MB cho LittleFS (theo profile
4MB chip, dù board thật có 8MB) — không đủ chứa raw waveform 1 participant chạy đủ 5
activity (~1.6MB). `platformio.ini` (env `ble`) giờ trỏ `board_build.partitions` sang
`partitions_ble_8mb.csv` (bỏ OTA slot thứ 2, dồn hết cho app0 3MB + spiffs 4.94MB).
**Flash lại firmware sẽ xoá toàn bộ session file cũ đang lưu trên board** — dump trước
nếu có data cần giữ.

## 2026-07-17 — Fix: adaptive PPG threshold có thể kẹt vĩnh viễn, không tự phục hồi
`acAmplitudeEstimate` chỉ được cập nhật BÊN TRONG nhánh "1 wave vừa vượt ngưỡng hiện
tại" — nếu 1 motion spike (hoặc seed lúc khởi động) đẩy ngưỡng cao hơn biên độ nhịp
tim thật, không có wave nào vượt được nữa để tự đưa ngưỡng xuống → `bpm`/`bpm_fresh`
đứng yên vĩnh viễn dù contact tốt. Thêm decay: sau `PPG_AC_STALE_MS`=2000ms không có
wave nào hoàn thành, `acAmplitudeEstimate` tự giảm dần về `PPG_AC_ONSET_MIN`.

## 2026-07-17 — Known limitation: `raw_ppg_N.csv`/`raw_ppg2_N.csv` mất ~28% mẫu, threshold detector không đủ tin cậy
Đo trên 1 dry-run 8 phút thật: raw waveform (100Hz) chỉ giữ được ~72% mẫu kỳ vọng,
rải rác ~3000 khoảng hở nhỏ (~100ms/lần) — nghi do `task_raw_writer` flush flash mỗi
500ms làm khựng hệ thống ngắn. `session_N.csv` (dataset chính) KHÔNG bị ảnh hưởng,
100% đầy đủ — chỉ raw waveform phụ trợ (research track LMS/RLS/Wiener) bị rớt mẫu.
Riêng: replay lại thuật toán onset/reset trên raw data thật cho thấy chỉ 58/228 wave
được accept làm beat, khoảng cách giữa các beat được accept có lúc tới 58s — xác nhận
`bpm`/`bpm_fresh` live chỉ nên coi là chỉ báo thô, KHÔNG phải ground truth heart rate.
Ground truth thật phải tính offline từ raw waveform — đúng lý do research track LMS
tồn tại, không phải bug cần vá thêm ở threshold real-time.

## 2026-07-15 — Thêm raw waveform capture (task + queue riêng) cho hướng nghiên cứu LMS
Câu hỏi nghiên cứu (so sánh LMS/RLS/Wiener) không trả lời được nếu chỉ có BPM đã tính sẵn —
cần chạy thuật toán lên chính raw signal. Thêm `task_raw_writer` (task 6) + `raw_imu_queue`/
`raw_ppg_queue` riêng, ghi `/raw_ppg_N.csv` + `/raw_accel_N.csv` song song với `session_N.csv`
(không thay thế). Chỉ hoạt động khi `protocolStarted` (không ghi raw lúc prep). Flush mỗi
500ms (không gộp batch lớn) để giới hạn lượng data mất nếu board crash giữa chừng.
`nextSessionPath()` đổi thành `nextSessionNumber()` để 3 file cùng participant dùng chung số
N. `log_serial.py` KHÔNG cần sửa — logic dump vốn tổng quát theo marker `----- FILE: X -----`.

## 2026-07-16 — Thêm MAX30102 thứ 2 (fingertip, ground-truth channel)
Cảm biến MAX30102 có địa chỉ I2C cố định (0x57, không có chân ADDR) nên không thể dùng
chung bus với con hiện tại (dorsal wrist) — con mới đi trên bus I2C riêng (`Wire1`, SDA=GPIO3/D2,
SCL=GPIO2/D1), task riêng `task_ppg2_reader` (task 7), không cần `i2c_mutex` vì không đụng bus
với ai. `BUZZER_PIN` dời từ D2(GPIO3) sang D3(GPIO4) để nhường chỗ. Chỉ ghi raw capture vào `/raw_ppg2_N.csv` (cùng schema `raw_ppg_N.csv`) — KHÔNG đưa
vào `ppg_queue`/BPM/`session_N.csv`, vì vai trò của nó là ground-truth tham chiếu cho so sánh
LMS/RLS/Wiener (`experiments/fingertip/`), không phải BPM sống thứ 2. `log_serial.py` không
cần sửa (marker-based). `STACK_RAW` tăng 8192→12288 vì 3 buffer raw giờ ~7.6KB, margin cũ
không đủ an toàn.

**Checklist rabbit-hole — dừng lại và tắt raw capture nếu:**
- Build lỗi > ~15 phút chưa fix được
- Pipeline feature đã validate hôm 07-14 (`bpm`/`std_mag`/`ppg_contact`/`bpm_fresh`) chạy
  sai/khác trước sau khi thêm raw capture (regression) — tắt ngay bằng cách comment
  `xTaskCreate(task_raw_writer...)` + 2 chỗ gọi `xQueueSend(raw_*_queue...)`
- Thấy dấu hiệu mất sample/queue tràn nhiều dù đã tăng depth — chấp nhận raw capture
  best-effort, không cố tối ưu thêm ngay
- Ghi flash raw làm lệch nhịp đọc IMU/PPG (task watchdog reset, log lỗi lạ)
- Debug việc này quá ~30-45 phút mà chưa ổn định → dừng, dùng `firmware_capture`/
  `capture_waveform.py` (công cụ demo riêng, đã chạy được) thay vì tiếp tục vá pipeline chính

## 2026-07-15 — Ngưỡng detect nhịp thích nghi + cột `bpm_fresh` + tăng dòng LED
Phát hiện qua `check_dataset_readiness.py`: BPM bị đứng yên hàng chục giây ở nhiều file,
do 2 nguyên nhân khác nhau — (1) motion artifact + tuột tiếp xúc thoáng qua, (2) ngồi yên
quá tĩnh khiến biên độ AC thật không vượt ngưỡng cố định `ac>50/ac<-15`. Sửa: ngưỡng detect
giờ co giãn theo biên độ sóng gần nhất (`acAmplitudeEstimate`) thay vì hằng số — giải quyết
được cả 2 case. Thêm cột `bpm_fresh` (ghi cả flash CSV lẫn BLE payload) — đánh dấu rõ khi
nào 1 nhịp THẬT SỰ được detect gần đây, để lọc bỏ đúng đoạn data không đáng tin thay vì đoán
qua thống kê hậu kỳ. `check_dataset_readiness.py` giờ ưu tiên dùng cột này, chỉ fallback về
heuristic cũ cho file cũ chưa có. Cũng tăng dòng LED MAX30102 (30→55) làm thử nghiệm phần
cứng bổ trợ cho case (2). File cũ trước ngày này sẽ luôn bị flag "no bpm_fresh column".

## 2026-07-14 — Dump không cần reset nữa: on-demand trigger qua Serial bất cứ lúc nào
Board vào enclosure rồi không bấm nút reset được nữa; cả 2 cách thay thế (DTR pulse qua
pyserial, rút/cắm USB đúng lúc) đều không ổn định trên board/OS này. Root cause thật sự:
thiết kế cũ *bắt buộc* phải reset mới dump được — bỏ luôn yêu cầu đó thay vì cố fix cách
reset. Giờ `task_classifier` lắng nghe ký tự Serial mỗi vòng lặp (~40-60ms); gửi bất cứ
lúc nào SAU khi 5 hoạt động xong (`protocolFinished`) sẽ trigger dump ngay, không giới hạn
3 giây sau boot nữa. Gate theo `protocolFinished` để không bao giờ dump giữa lúc đang ghi
(tránh mở/xoá file đang được ghi dở). `log_serial.py` không đổi logic, chỉ đổi message.

## 2026-07-14 — Protocol: thêm 15s prep trước hoạt động 1; âm thanh báo hiệu chuyển sang laptop
Trước đây recording bắt đầu ngay lúc boot — không kịp vào tư thế "lying" đầu tiên. Giờ có
15s im lặng để chuẩn bị (không ghi row nào, cả flash lẫn BLE — xem `protocolStarted`), rồi
mới bắt đầu tính activity 1. Quyết định: âm thanh báo hiệu (chuyển hoạt động, kết thúc, mất
tiếp xúc PPG) chuyển hẳn sang phát từ **laptop** qua `log_ble.py` (`winsound`), không dùng
buzzer phần cứng nữa — né được bug "im lặng khi chạy pin" chưa fix, thay vì debug nó.
`BUZZER_ENABLED` giữ nguyên = 0.

## 2026-07-14 — Fix: `ppgOK` là flag tĩnh (boot-time), đổi thành `ppg_contact` sống theo từng dòng
Field `ppgOK` (thêm 2026-07-10) đáng lẽ phải phản ánh live contact nhưng thực ra chỉ set 1
lần lúc `setup()` — mọi dòng trong 1 session đều cùng giá trị, nên cảnh báo "mất contact"
trong `log_ble.py`/`visualize_session.py` chưa từng thật sự bắt được gì. Giờ tính lại mỗi
window (dựa vào watchdog `lastPpgMs` có sẵn) → field mới `ppg_contact`, ghi vào CẢ flash CSV
(cột mới, trước đây không có) lẫn BLE payload (đổi tên). `log_serial.py` quality_check giờ
cũng check field này cho flash CSV, giống `log_ble.py` đã làm cho live-view.

## 2026-07-11 — TEAMMATE_SETUP.md: thêm đường dẫn không cần Git
Teammate không có Git vẫn tải/nộp data được qua giao diện web GitHub (ZIP download +
upload trực tiếp trên trình duyệt). Đây là hợp đồng mới giữa quy trình thu data và
người thu — không bắt buộc môi trường dev đầy đủ nữa.

## 2026-07-10 — BLE payload thêm `ppgOK` + `seconds_left`
Schema JSON giữa firmware (`firmware_ble/main.cpp`) và `log_ble.py` đổi — 2 field mới
tính ở phía device (không phải client tự đoán), để live-view cảnh báo sensor lệch +
đếm ngược chính xác. **Chỉ có ở `firmware_ble/`, chưa port sang `firmware_main/`.**

## 2026-07-10 — Thêm `visualize_session.py`
Consumer mới của schema CSV đã có sẵn (không đổi schema) — dùng để validate data
bằng mắt trước khi push, dựa trên assumption: cường độ vận động phải tăng dần theo
thứ tự lying→sitting→standing→walking→running.

## 2026-07-10 — Pivot: BLE thay WiFi (Option 4) làm transport chính để thu data
`firmware_main/` (Jetson WiFi AP + UDP) parked, không xoá — debug NetworkManager tốn
quá nhiều thời gian. `firmware_ble/` (fork mới) trở thành nhánh chính thức để thu
data thật. Quyết định: ưu tiên độ ổn định đã được chứng minh hơn tính năng mới.

## 2026-07-10 — BLE payload embed full row schema
Trước đó `log_ble.py` tự giữ đồng hồ + tự suy label — rủi ro lệch giờ với đồng hồ
thiết bị (dual-clock-drift). Giờ device nhúng toàn bộ row (label, is_transition,
elapsed_ms...) thẳng vào payload — device là nguồn sự thật duy nhất, cả flash lẫn BLE.

## 2026-07-10 — Fix: BLE advertising không tự resume sau disconnect
NimBLE không tự bật lại advertising sau khi client ngắt kết nối — thêm callback
`onDisconnect()` + watchdog 5s. `log_ble.py` cũng đổi: re-scan thiết bị mỗi lần
reconnect thay vì dùng lại reference cũ (2 lỗi cộng dồn gây ra 100% reconnect fail).

## 2026-07-07 — Kiến trúc: flash là nguồn sự thật, wireless chỉ là best-effort
Firmware ghi mọi row vào flash (LittleFS) **vô điều kiện**; WiFi/BLE chỉ dùng để xem
live, không bao giờ bắt buộc. Lý do: radio contention (WiFi+BLE chung 1 ăng-ten,
campus WiFi nghẽn) khiến wireless-là-primary không đáng tin cậy.

## 2026-07-07 — Đổi nguồn điện: power bank thường → pin LiPo qua JST
Power bank thường tự ngắt sau ~30s vì ESP32 không rút đủ dòng để pass "device
connected" detection — làm session bị cắt giữa chừng không báo lỗi. Chuyển sang pin
LiPo cắm trực tiếp qua cổng JST của XIAO (có mạch quản lý sạc onboard, chính thức
hỗ trợ cắm đồng thời cả USB).

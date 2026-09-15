# Thiết bị đeo tay theo dõi vận động & sức khoẻ

**Thiết bị đeo cổ tay giá ~25 USD, phân loại hoạt động thể chất ngay trên vi điều khiển —
kèm phân tích nguyên nhân gốc rễ vì sao khối đo nhịp tim không thể hoạt động.**

`ESP32-S3` · `FreeRTOS` · `C++` · `Python` · `scikit-learn` · `Xử lý tín hiệu nhúng`

🇬🇧 [Read in English](README.md)

---

## Đây là gì

Thiết bị đeo cổ tay dựng từ linh kiện khoảng 25 USD, thay thế cho các thiết bị nghiên cứu
giá 325–1690 USD. Mọi thứ chạy trực tiếp trên vi điều khiển: không app điện thoại, không
cloud, không cần internet.

Hai khối độc lập:

- **Khối A — nhận dạng hoạt động.** Phân loại Nằm / Ngồi / Đứng / Đi bộ / Chạy từ cảm biến
  gia tốc ở cổ tay, thời gian thực, ngay trên chip.
- **Khối B — nhịp tim.** Khử nhiễu chuyển động khỏi tín hiệu PPG ở cổ tay, dùng gia tốc kế
  làm tín hiệu tham chiếu nhiễu (NLMS / RLS / Wiener).

Khối A chạy được và đã deploy. Khối B thì không — và **phần đáng giá nhất của dự án là
chuỗi bằng chứng chỉ ra tại sao**: nguyên nhân nằm ở phần cứng cảm biến, không phải ở
thuật toán.

📄 Báo cáo đầy đủ: **[paper/THESIS.md](paper/THESIS.md)** — 7 chương, từ phương pháp tới
phân tích nguyên nhân gốc. Mọi con số trong đó đều chạy lại được theo
[paper/EVIDENCE_GUIDE.md](paper/EVIDENCE_GUIDE.md).

---

## Kết quả chính

| | Kết quả | Đo bằng cách nào |
| :--- | :--- | :--- |
| Phân loại hoạt động (3 lớp) | **85.3%** trên người chưa từng thấy | LOGO-CV, 18 participant, 16.880 window |
| Phân loại hoạt động (5 lớp) | **54.8%** trên người chưa từng thấy | Cùng giao thức — lỗi mang tính cấu trúc, xem bên dưới |
| Độ chính xác chạy thật trên board | chạy 98.4% · đứng 96.8% · đi bộ 83.4% | Session thật, model chạy trên ESP32 |
| Tài nguyên firmware | **11.4% RAM** (37 KB / 320 KB) · **18.1% flash** | `pio run -e ble`, 7 task FreeRTOS + BLE + LittleFS |
| Dataset | **18 participant**, 5 hoạt động, 20.258 window có nhãn | Tự thu, không dây nối, ghi thẳng vào flash on-chip |
| Tỉ lệ tín hiệu PPG cổ tay dùng được | **9.6%** số window (so với 35.0% ở đầu ngón tay) | Sau khi dựng lại bộ ước lượng tham chiếu |

LOGO-CV = Leave-One-Group-Out cross-validation: train trên 17 người, test trên người thứ
18, lặp lại 18 lần. Nó đo khả năng tổng quát hoá sang **người dùng mới**, không phải sang
window mới của người model đã thấy.

---

## Hai phát hiện kỹ thuật

### 1. Chứng minh bộ đặc trưng về mặt toán học không thể giải được bài toán

Model 5 lớp dừng ở 54.8%. Confusion matrix cho thấy lỗi không rải đều — nó nằm **trọn vẹn**
trong một khối 3×3: nằm, ngồi, đứng lẫn lộn với nhau, trong khi ranh giới tĩnh/động lại rất
sạch.

Cả 4 đặc trưng đều là hàm của magnitude gia tốc `√(ax² + ay² + az²)`, mà magnitude thì
**bất biến với phép quay**. Thứ duy nhất phân biệt ba tư thế tĩnh lại chính là hướng cổ
tay. Thông tin đó bị xoá ngay ở bước trích đặc trưng, trước khi model nhìn thấy gì — nên
không model nào, không lượng tuning nào lấy lại được.

Ba hướng sửa đã thử (mean từng trục; mean từng trục tương đối so với baseline nằm của chính
người đó; test lại cả hai ở N lớn hơn) đều đúng với một số người và hỏng với người khác, vì
góc đeo không bao giờ được calibrate. Sau lần thứ ba, việc này được **chủ động dừng lại**,
giới hạn được báo cáo như một phát hiện đã truy ra gốc rễ, và bài toán được **định nghĩa
lại cho khớp với thứ cảm biến đo được về mặt vật lý** — 3 lớp, 85.3%.

Phần ghi chú trung thực, được tính ra chứ không nói lướt: majority-class baseline là 0.201
cho bài 5 lớp nhưng tới 0.599 cho bài 3 lớp (lớp `stationary` gộp 3/5 lớp gốc). Nên phép so
sánh công bằng là biên độ vượt baseline **của chính bài toán đó** — **+0.347 so với
+0.254** — chứ không phải con số thô 0.548 → 0.853, vốn thổi phồng mức cải thiện.

### 2. Tìm ra lỗi sai gấp 2 lần nằm ngay trong phép đo tham chiếu

Vòng so sánh filter đầu tiên cho MAE 26.95–29.96 bpm — gấp 5–6 lần ngưỡng lâm sàng
ANSI/AAMI EC13 (±5 bpm), và mọi adaptive filter đều *tệ hơn* việc không lọc gì cả.

Trước khi kết luận thuật toán vô dụng, **chính kênh tham chiếu** được đem đi kiểm tra bằng
một quy luật sinh lý: *nhịp tim lúc chạy phải cao hơn hẳn lúc nằm.* Kết quả: 3/5 participant
không thoả. P17 đo được 76.0 bpm lúc nằm và 77.0 bpm lúc chạy.

Nguyên nhân gốc: **lỗi octave** — bộ ước lượng dựa trên FFT bám nhầm vào nửa hoặc gấp đôi
tần số thật. Nó sống sót hàng tuần vì một ràng buộc liên tục (`MAX_JUMP_BPM = 25`) thuộc về
tầng **làm mượt** đã âm thầm bảo vệ một lỗi ở tầng **đo**: dãy [77, 77, 77, …] trông rất ổn
định nên được tin tưởng, còn giá trị đúng 156 bpm thỉnh thoảng bắt được lại bị loại vì
"nhảy quá xa".

Bộ ước lượng dựng lại làm việc trong miền thời gian (`HR = 60 / median(khoảng RR)`), có chỉ
số chất lượng tín hiệu (`CV = σ_RR / μ_RR`), và **được phép trả về "không đọc được"** thay
vì đoán bừa. Đối chiếu với việc đếm đỉnh bằng tay, nó sửa sai theo **cả hai chiều**
(P17 77.0 → 156.9; P16 155.8 → 118.9), và tỉ lệ participant qua được kiểm tra sinh lý tăng
từ 40% lên 80%.

Khi đã có một cái thước đáng tin, kết quả thật lộ ra: kênh cổ tay chỉ cho nhịp tim dùng
được ở **9.6%** số window. Nguyên nhân nằm ở khối thu quang — MAX30102 là linh kiện đo SpO2
với LED 660 nm đỏ / 880 nm hồng ngoại, trong khi đo nhịp tim phản xạ ở cổ tay cần bước sóng
xanh lá ~525 nm. Benchmark mà dự án tự so sánh (TROIKA, ~2 bpm) dùng cùng vị trí đeo, cùng
độ dài window, cùng metric — nhưng với LED xanh lá.

**Kết luận: một vấn đề tưởng là phần mềm nhưng chưa bao giờ là phần mềm.** Không filter nào
tách được tín hiệu mà tầng thu thập chưa từng bắt được.

---

## Kiến trúc hệ thống

```
[MPU6050 25 Hz]   [MAX30102 cổ tay 100 Hz]   [MAX30102 đầu ngón 100 Hz]
       |                    |                          |
       +--- 3 task đọc cảm biến (ưu tiên cao nhất, nhịp cố định) ---+
       |                    |                          |
    imu_queue          ppg_queue                  raw_ppg2_queue
       |                    |                          |
  [task_classifier] -> đặc trưng -> decision tree -> lớp hoạt động
       |                    |
  [task_flash_writer] -> session_N.csv + raw_ppg / raw_ppg2 / raw_accel  (LittleFS)
       |
  [task_ble_streamer] -> JSON live (chỉ để xem, không bao giờ bắt buộc)
```

Ba quyết định kiến trúc trụ được suốt dự án:

1. **Bảy task FreeRTOS không chia sẻ gì ngoài queue.** Không biến global giữa các task. Ba
   task đọc cảm biến giữ ưu tiên cao nhất và là những task duy nhất bám nhịp cố định; phân
   loại, ghi flash và BLE được phép trễ mà không bao giờ làm lệch tần số lấy mẫu.
2. **Flash là nguồn sự thật; không dây chỉ là best-effort.** Mọi dòng dữ liệu đều ghi vào
   flash on-chip vô điều kiện. Quyết định này thay thế transport WiFi/UDP rồi tới BLE-là-
   chính, cả hai đều rớt dữ liệu đúng lúc participant chuyển động.
3. **Thiết bị sở hữu đồng hồ và nhãn.** Dòng dữ liệu đầy đủ (label, `elapsed_ms`, cờ
   transition) được ghép ngay trên thiết bị, nên máy tính không bao giờ có thể bất đồng về
   thời điểm.

Cây quyết định sau khi train được export thành **C if/else lồng nhau**
(`scripts/train/export_classifier_to_c.py`) — không runtime TFLite, không cấp phát heap,
chỉ vài phép so sánh float mỗi window.

---

## Cấu trúc repo

```
firmware/               Source PlatformIO (src_dir)
  ble/                  Firmware chính: 7 task FreeRTOS, BLE, LittleFS, classifier đã deploy
  baseline/             Bản single-loop dùng làm mốc so sánh (latency/RAM)
  capture/              Công cụ thu raw waveform độc lập
scripts/
  collect/              Rút session từ flash thiết bị, xem BLE live, thu waveform
  dataset/              Session thô -> data/processed/master_dataset.csv, kiểm tra chất lượng
  train/                Train + đánh giá LOGO-CV, export ra C header
  analysis/             Pipeline Khối B (NLMS/RLS/Wiener, HR estimator v2, sanity check)
                        và các script vẽ hình import nó — một cụm gắn chặt với nhau
  report/               Công cụ báo cáo độc lập: sinh sơ đồ, markdown -> docx
  viz/                  Vẽ session, vẽ raw waveform, viewer serial thời gian thực
experiments/            Session thô, đúng như lúc thu (wrist/, fingertip/)
data/processed/         Dataset dẫn xuất, sinh bởi scripts/dataset/
models/                 Model đã train (.pkl)
paper/                  Báo cáo, báo cáo tiến độ theo tuần, hình
docs/                   Hướng dẫn thu data cho người cùng nhóm
archived/               Phần việc đã park, giữ lại làm hồ sơ (firmware WiFi/UDP, Jetson server, README cũ)
```

`experiments/` (thô, bất biến, đúng như lúc thu) được tách khỏi `data/processed/` (dẫn
xuất, tái tạo được) một cách có chủ đích — và đường dẫn dữ liệu thô cố tình không đổi tên,
để các bước tái lập kết quả đã công bố trong báo cáo vẫn còn đúng.

---

## Build và chạy

**Firmware** (PlatformIO, Seeed XIAO ESP32-S3):

```bash
pio run -e ble                 # firmware chính (đã verify: RAM 11.4%, flash 18.1%)
pio run -e ble -t upload
pio device monitor             # 115200 baud
```

**Công cụ phía máy tính** — mọi script đều chạy từ thư mục gốc của repo:

```bash
pip install -r requirements.txt

python scripts/collect/log_serial.py COM3          # rút session từ flash thiết bị
python scripts/dataset/build_processed_dataset.py  # -> data/processed/master_dataset.csv
python scripts/train/train_activity_classifier.py  # LOGO-CV + train + lưu .pkl
python scripts/train/export_classifier_to_c.py     # -> firmware/ble/activity_classifier_5class.h
python scripts/analysis/lms_denoise_mvp.py         # so sánh NLMS / RLS / Wiener
```

---

## Đặt kết quả vào bối cảnh

| Đại lượng | Dự án này | Công bố gần nhất để so | Khác biệt giải thích khoảng cách |
| :--- | :--- | :--- | :--- |
| HAR 3 lớp, user-independent | 0.853 (n=18) | Đúng tầm của literature với 1 gia tốc kế ở cổ tay | — |
| HAR 5 lớp, user-independent | 0.548 (n=18) | Bao & Intille (2004): ~84% | Họ dùng **5** vị trí cảm biến gồm đùi và hông; ở đây không có kênh orientation |
| Nhịp tim PPG cổ tay | MAE 27–30 bpm, yield 9.6% | TROIKA (Zhang 2015): ~2 bpm | Cùng vị trí, window, metric — **515 nm xanh lá so với 880 nm hồng ngoại** |

Không kết quả nào là bất thường. Cả hai đều rơi đúng chỗ literature dự đoán — và đó chính
là điểm mấu chốt: phần thiếu hụt đã được truy về nguyên nhân cụ thể, có tên, chứ không bị
bỏ lại như một bí ẩn.

---

## Giới hạn, nói thẳng

- Chưa có máy đo nhịp tim cổ tay hoạt động được, và **thêm bao nhiêu phần mềm trên phần
  cứng này cũng không tạo ra được** — nó cần khối thu quang bước sóng xanh lá.
- Kênh con quay hồi chuyển của MPU6050 chưa bao giờ được đọc; phân tích Khối A cho thấy đó
  đúng là kênh còn thiếu đang chặn mục tiêu 5 lớp.
- Mỗi participant chỉ 1 session, thứ tự hoạt động cố định, không calibrate góc đeo và không
  kiểm soát lực tiếp xúc — nên độ lặp lại (test-retest) chưa biết.
- Ground truth là một cảm biến PPG thứ hai, không phải ECG.

---

## Tài liệu

| Tài liệu | Nội dung |
| :--- | :--- |
| [CHANGELOG.md](CHANGELOG.md) | Mọi quyết định ở mức boundary/interface kèm lý do, theo ngày |
| [paper/THESIS.md](paper/THESIS.md) | **Báo cáo đầy đủ** — 7 chương: phương pháp, hai khối, phân tích nguyên nhân gốc, giới hạn |
| [paper/EVIDENCE_GUIDE.md](paper/EVIDENCE_GUIDE.md) | Cách chạy lại từng con số trong báo cáo, theo từng lệnh |
| [paper/activity_classifier_REPORT.md](paper/activity_classifier_REPORT.md) | Phát hiện Khối A, nguyên nhân gốc và phân tích baseline công bằng |
| [paper/adaptive_filter_comparison_REPORT.md](paper/adaptive_filter_comparison_REPORT.md) | Phương pháp Khối B, lỗi octave và kết quả |
| [paper/proposal_vs_reality.md](paper/proposal_vs_reality.md) | Đối chiếu 14 mục: hứa gì so với làm được gì |
| [paper/weekly_reports/](paper/weekly_reports/) | Ghi chép từng tuần: làm được gì, kết quả nghĩa là gì |
| [docs/TEAMMATE_SETUP.md](docs/TEAMMATE_SETUP.md) | Hướng dẫn thu data viết cho người không phải dev |
| [archived/README_original_2026-08-13.md](archived/README_original_2026-08-13.md) | README phát triển bản gốc, giữ nguyên |

---

## Nhóm và phạm vi

Đồ án 3 người, 13 tuần (tháng 6–9/2026).

- **Hoàng Nguyễn Ngọc Giang** — firmware và kiến trúc FreeRTOS, xử lý tín hiệu, train và
  deploy model, pipeline dữ liệu, phân tích. Toàn bộ nội dung trong repo này.
- **Phan Ngọc Quốc Duy** — thiết kế PCB và phần điện.
- **Trần Thanh Tùng** — thiết kế cơ khí/vỏ hộp, vị trí đặt cảm biến.

Dự thi Convergence Innovation Competition (Georgia Tech), hạng mục Global Health and
Wellbeing.

# Changelog — quyết định ở mức boundary/interface

File này **không phải** thay cho `git log` — git log ghi từng dòng code đổi gì,
còn file này chỉ ghi lại những chỗ **hợp đồng giữa 2 phần** của hệ thống bị đổi
(schema data, giao thức giữa firmware/script, kiến trúc chuyển transport, v.v.) —
những thứ mà nếu không biết thì phần còn lại của hệ thống sẽ vỡ ngầm.

Mỗi entry chỉ 2-3 dòng: **đổi gì** + **tại sao**. Không ghi chi tiết implementation.

---

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

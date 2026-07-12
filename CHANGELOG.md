# Changelog — quyết định ở mức boundary/interface

File này **không phải** thay cho `git log` — git log ghi từng dòng code đổi gì,
còn file này chỉ ghi lại những chỗ **hợp đồng giữa 2 phần** của hệ thống bị đổi
(schema data, giao thức giữa firmware/script, kiến trúc chuyển transport, v.v.) —
những thứ mà nếu không biết thì phần còn lại của hệ thống sẽ vỡ ngầm.

Mỗi entry chỉ 2-3 dòng: **đổi gì** + **tại sao**. Không ghi chi tiết implementation.

---

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

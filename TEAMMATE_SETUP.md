# Hướng dẫn thu data (Windows)

Làm theo thứ tự từ trên xuống. Chỗ nào có khung code thì copy-paste y nguyên vào **PowerShell**.

Thu data chạy hoàn toàn bằng pin (không cần laptop kè kè bên cạnh lúc thu), thiết bị coi như
đã được nạp sẵn firmware rồi. Bạn không cần đụng gì đến PlatformIO hay firmware cả — chỉ cần
chạy mấy file Python bên dưới thôi.

## 0. Chuẩn bị (cài 1 lần)

1. Cài Python 3.10+: https://www.python.org/downloads/ — nhớ tick **"Add python.exe to PATH"** lúc cài
2. Nhận lời mời collaborator qua email vịt gửi (check cả spam)
3. Sạc đầy / chuẩn bị pin cho thiết bị (dùng pin hoặc power bank — lúc thu thật thì đừng cắm USB vào laptop)
4. (Không bắt buộc) Cài Git for Windows: https://git-scm.com/download/win — nếu không muốn cài thì xem Cách B ở bước 1

## 1. Tải code về

**Cách A — có Git:**
```powershell
git clone https://github.com/ChuoiUhuhu0727/wearable-health-monitor.git
cd wearable-health-monitor
git checkout week1-2/baseline-freertos
```

**Cách B — không cài Git:**
1. Bấm link này để tải file zip (đã đúng branch sẵn rồi):
   https://github.com/ChuoiUhuhu0727/wearable-health-monitor/archive/refs/heads/week1-2/baseline-freertos.zip
2. Giải nén ra đâu đó (VD Desktop). Mở PowerShell, `cd` vào folder vừa giải nén.
3. Từ đây trở đi làm y hệt cách A — Git chỉ cần lại ở bước 7 (mà bước đó cũng có cách không cần Git).

## 2. Cài thư viện Python

```powershell
python -m pip install pyserial bleak matplotlib
```

- `pyserial` — bắt buộc, để lấy data qua cổng USB sau khi thu xong
- `bleak` — không bắt buộc, chỉ cần nếu muốn xem data chạy live lúc đang thu (nên dùng, xem bước 4)
- `matplotlib` — không bắt buộc, chỉ cần để tự vẽ kiểm tra data trước khi gửi (nên dùng, xem bước 6)

## 3. Check sensor nhanh trước khi thu

Cắm thiết bị vào laptop qua USB, mở Serial Monitor (icon phích cắm của PlatformIO, hoặc gõ
`pio device monitor -b 115200`), nhìn khoảng 15-30 giây:

- `ppgOK:1` → cảm biến nhịp tim đang đọc được, ổn
- `ppgOK:0` hoặc thấy dòng `[WARN] MAX30102 không tìm thấy` → cảm biến chưa đọc được —
  chỉnh lại vị trí/dây nối trước khi thu thật, không thì data thu ra sẽ không dùng được

Bước này chỉ tốn 30 giây nhưng đỡ phải thu lại cả buổi nếu sensor bị lệch mà không biết.

## 4. Thu data — chạy pin hoàn toàn, có thể xem live

1. Rút dây USB ra. Cắm pin/power bank vào thay thế.
2. Thiết bị tự chạy 5 hoạt động liên tiếp — lying, sitting, standing, walking, running —
   mỗi hoạt động 90 giây (15s đầu để ổn định + 75s data sạch).
3. Data được ghi thẳng vào bộ nhớ thiết bị ngay lúc thu — không cần laptop ở gần, không cần
   BLE/WiFi kết nối, có mất kết nối giữa chừng cũng không sao, data vẫn an toàn.

**Nên làm: bật xem live cho mấy hoạt động đứng yên.**
Buzzer hiện chạy pin không kêu ổn định (lỗi phần cứng đã biết, chưa fix được), nên đừng dựa
vào tiếng bíp để biết đang ở hoạt động nào. Thay vào đó, mở laptop chạy:

```powershell
python log_ble.py
```

Để laptop cách thiết bị trong khoảng 1m. Lúc đang kết nối, terminal sẽ báo rõ luôn, không
cần đoán:
- `=== NOW RECORDING: STANDING ===` — báo hoạt động vừa chuyển, kèm hoạt động tiếp theo là gì
- `[!] Switching to 'walking' in 5s — get ready` — đếm ngược 5 giây cuối trước khi chuyển hoạt động
- `[WARNING] PPG sensor lost contact` — cảm biến nhịp tim bị lệch, **chỉnh lại strap ngay lúc đó**
  luôn, đừng để thu xong mới biết

**Lúc bắt đầu đi bộ/chạy thì màn hình sẽ báo mất kết nối** — BLE tầm ngắn (~1m) nên chuyện này
bình thường, không phải lỗi. Sẽ thấy dòng `[WARN] BLE disconnected — likely moved out of range`,
data vẫn an toàn trong flash của thiết bị. Trước khi đi xa laptop, nhớ giờ lại: mỗi hoạt động
đúng 90 giây, theo thứ tự trên — vừa thấy banner "NOW RECORDING: WALKING" là có thể tự bấm giờ
điện thoại 90s cho 2 hoạt động walking/running còn lại.

## 5. Lấy data về máy

```powershell
python log_serial.py COM3
```

(Đổi `COM3` thành đúng cổng của thiết bị — check ở Device Manager → Ports nếu không chắc.)

**Quan trọng — chạy lệnh này TRƯỚC khi cắm/reset thiết bị.** Script sẽ đứng chờ, rồi bạn mới
cắm hoặc bấm reset — nó bắt đúng khoảnh khắc ngay lúc boot để rút data ra. Nếu bị timeout thì
reset lại thiết bị lần nữa, script tự thử lại.

**Nếu thu xong mà chưa chạy lệnh này ngay thì cũng không sao** — data vẫn nằm an toàn trong
flash của thiết bị, không tự mất. Có thể thu nhiều người liên tiếp (chỉ cần tắt/bật lại nguồn
giữa mỗi người) rồi mới chạy `log_serial.py` một lần để lấy hết ra cùng lúc. Chỉ cần nhớ đừng
để quá lâu — thiết bị chỉ chứa tối đa 20 lượt thu, quá số đó thì các lượt sau sẽ ghi đè lẫn nhau.

Mỗi lượt thu được lưu thành 1 file CSV riêng, trong `experiments/wrist/`, và script tự in
luôn 1 bảng kiểm tra chất lượng (đếm số dòng, nhịp tim có bất thường không) để biết ngay có
cần thu lại không.

**Cách file được đặt tên:** `session_N_YYYYMMDD_HHMMSS.csv`, VD `session_1_20260710_142941.csv`.
Tự động đặt, không cần tự gõ tên gì cả:
- `N` — số thứ tự lượt thu **trên thiết bị**, tăng dần mỗi lần tắt/bật nguồn để thu người mới
  (không phải số thứ tự do bạn chọn). Thu 3 người liên tiếp mà chưa lấy data ra thì sẽ ra
  `session_1`, `session_2`, `session_3`.
- `YYYYMMDD_HHMMSS` — thời điểm **lấy từng file ra** trong lúc chạy `log_serial.py`, không phải
  lúc thu thật. Nếu để dồn nhiều lượt rồi mới lấy ra 1 lần, timestamp giữa các file sẽ xêm xêm
  nhau (cách nhau vài giây, tùy lúc đó truyền xong file trước) chứ không hẳn trùng khớp — bình
  thường, cứ nhìn số `N` để phân biệt từng lượt, đừng dựa vào timestamp.

## 6. Kiểm tra data trước khi gửi

```powershell
python visualize_session.py experiments/wrist/session_1_<timestamp-của-bạn>.csv
```

(Không ghi path cũng được — nó tự chọn file mới lấy gần nhất.)

Lệnh này vẽ ra nhịp tim + độ chuyển động của cả buổi thu, tô màu theo từng hoạt động. Data
**ổn** sẽ có dạng: độ chuyển động (`mean_mag`/`std_mag`) tăng dần từ lying → sitting → standing
→ walking → running, đúng theo thứ tự cường độ tăng dần. Nếu thấy đồ thị phẳng lì suốt cả 5
hoạt động, hoặc có 1 đoạn trống bất thường không giải thích được, chụp gửi vịt xem trước khi
push — nhiều khả năng là sensor bị tuột hoặc bị bỏ sót 1 đoạn.

## 7. Gửi data lên GitHub, mở Pull Request

**Chỉ gửi file bắt đầu bằng `session_` và đuôi `.csv`** (VD: `session_1_20260710_142941.csv`)
— đây là data thật lấy ra từ flash thiết bị. Các file khác **không cần gửi**:
- `diag_*.log` — log debug nội bộ, không phải data
- `ble_live_*.csv` — chỉ là bản xem live lúc thu, có thể thiếu dòng do rớt kết nối, không phải bản chuẩn
- `*_plot.png` — ảnh tự vẽ để kiểm tra ở bước 6, không phải data

**Cách A — có Git:**
```powershell
git checkout -b data/<tên-bạn>
git add experiments/wrist/
git commit -m "Add wrist data session(s) from <tên-bạn>"
git push origin data/<tên-bạn>
```

Đổi `<tên-bạn>` thành tên thật (VD `data/khang`).

Sau khi push, terminal sẽ in ra 1 link kiểu:
`https://github.com/ChuoiUhuhu0727/wearable-health-monitor/pull/new/data/<tên-bạn>`

Mở link đó, bấm **"Create pull request"** là xong.

**Cách B — không cài Git, upload thẳng trên web:**
1. Vào https://github.com/ChuoiUhuhu0727/wearable-health-monitor
2. Bấm vào ô chọn branch (góc trên trái, gần danh sách file — đang ghi `main`), đổi sang `week1-2/baseline-freertos`
3. Bấm vào folder `experiments` → `wrist`
4. Bấm **"Add file"** (góc phải trên) → **"Upload files"**
5. Kéo thả các file `session_*.csv` mới thu (chỉ mấy file mới tạo hôm nay thôi) vào
6. Kéo xuống dưới, ghi commit message kiểu: `Add wrist data session(s) from <tên-bạn>`
7. Chọn **"Create a new branch for this commit and start a pull request"**, đặt tên branch `data/<tên-bạn>`
8. Bấm **"Propose changes"**, rồi bấm **"Create pull request"** ở trang tiếp theo

Xong — không cần cài Git gì cả.

## Nếu gặp lỗi

- Check sensor báo `ppgOK:0` → MAX30102 chưa đọc được. Chỉnh lại dây/vị trí trước khi thu —
  thu trong lúc này thì data không dùng được.
- `log_ble.py` báo "Device not found" và cứ thử lại mãi → thiết bị chưa bật nguồn, đang kết
  nối với máy khác rồi, hoặc để quá xa — lại gần trong 1m và check lại pin.
- `log_serial.py` cứ bị timeout → nhớ chạy script này TRƯỚC khi cắm/reset thiết bị, và check
  lại đúng cổng COM chưa.
- `python -m pip install ...` báo lỗi → check `pip` có chạy được không: gõ `python -m pip --version`
  trước, nếu lỗi thì lúc cài Python chưa tick "Add to PATH" (cài lại và tick ô đó).
- `git push` báo "permission denied" → lời mời collaborator chưa được accept — check email,
  hoặc nhắn vịt gửi lại.

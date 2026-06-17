# Hướng dẫn chạy code cho Duy / Tùng

> Tài liệu này dành cho bạn **không phải dân lập trình**. Làm theo từng bước, không cần hiểu code.  
> Nếu bị lỗi ở bước nào → chụp màn hình → nhắn cho Giang.

---

## Bước 0 — Cài đặt (chỉ làm 1 lần duy nhất)

### 0.1 — Cài VS Code

1. Vào trang: **https://code.visualstudio.com**
2. Nhấn nút **Download for Windows**
3. Mở file vừa tải về, cài bình thường (Next → Next → Install)

### 0.2 — Cài PlatformIO trong VS Code

1. Mở VS Code vừa cài
2. Nhìn sang thanh bên trái, tìm icon hình **4 ô vuông** (Extensions)
3. Trong ô tìm kiếm gõ: `PlatformIO`
4. Nhấn **Install** vào cái tên **PlatformIO IDE**
5. Chờ cài xong → VS Code sẽ tự restart

> Lần đầu mở PlatformIO có thể mất 3–5 phút để nó tải thêm công cụ. Cứ để máy chạy.

---

## Bước 1 — Tải code về máy

1. Vào link: **https://github.com/ChuoiUhuhu0727/Martial-Arts-Signal-Analysis**
2. Nhấn nút xanh **Code** → chọn **Download ZIP**
3. Giải nén file ZIP ra Desktop hoặc một thư mục dễ tìm
4. Mở VS Code → **File** → **Open Folder** → chọn folder vừa giải nén

---

## Bước 2 — Cắm board vào máy tính

1. Dùng cáp USB-C cắm board **XIAO ESP32-S3** vào máy tính
2. Đèn LED trên board sẽ sáng lên → đã nhận điện
3. Chờ Windows tự nhận driver (khoảng 10–30 giây)

---

## Nhiệm vụ A — Đo baseline (làm trước)

> Mục đích: đo xem AI trên board chạy nhanh cỡ nào, dùng bao nhiêu bộ nhớ.  
> **Để board đứng yên trên bàn trong khi đo.**

### A.1 — Chọn đúng firmware

1. Nhìn góc dưới cùng của VS Code, tìm thanh màu xanh dương
2. Tìm chỗ hiện tên environment (có thể đang ghi `seeed_xiao_esp32s3`)
3. Nhấn vào đó → chọn **`baseline`**

*(Nếu không thấy thanh xanh → nhấn icon hình con kiến ở thanh bên trái, tìm mục PROJECT TASKS)*

### A.2 — Nạp firmware vào board

1. Trong thanh xanh dưới cùng, tìm icon mũi tên **→** (Upload)
2. Nhấn vào đó
3. VS Code sẽ bắt đầu biên dịch code (hiện chữ đỏ/trắng chạy trong Terminal bên dưới)
4. Chờ đến khi thấy dòng chữ: `SUCCESS` hoặc `Done uploading`
5. Nếu báo lỗi `Port not found` → thử rút cáp USB ra cắm lại, đợi 5 giây rồi nhấn Upload lại

### A.3 — Mở Serial Monitor

1. Trong thanh xanh dưới cùng, tìm icon **ổ cắm điện** (Monitor)
2. Nhấn vào đó
3. Một cửa sổ Terminal sẽ mở ra bên dưới — bắt đầu thấy chữ chạy

### A.4 — Chờ đủ 60 giây

Board sẽ tự in báo cáo mỗi 10 giây. Trông sẽ như thế này:

```
=======================================================
   [LIVE #1] BASELINE REPORT — T=10s
=======================================================
--- FLASH ---
  Sketch used       :  154320 bytes  ( 150.7 KB)
  ...
--- RAM ---
  Free heap (now)   :  321456 bytes  ( 314.0 KB)
  ...
--- LATENCY: classifySignal() ---
  Mean    :     2.15 us  (0.0022 ms)
  ...
=======================================================
```

Sau 60 giây sẽ thấy dòng:
```
>>> ĐO XONG — copy toàn bộ output này gửi cho Giang <<<
```

### A.5 — Gửi kết quả cho Giang

1. Nhấn vào cửa sổ Terminal
2. **Ctrl + A** để chọn tất cả
3. **Ctrl + C** để copy
4. Paste vào Messenger / Zalo gửi cho Giang

---

## Nhiệm vụ B — Chạy firmware FreeRTOS mới (làm sau khi xong A)

> Mục đích: kiểm tra board có phát Bluetooth không, đủ để điện thoại nhìn thấy.

### B.1 — Chọn đúng firmware

1. Nhìn thanh xanh dưới cùng, nhấn vào tên environment
2. Chọn **`freertos_v1`**

### B.2 — Nạp firmware

Làm y hệt bước A.2 (nhấn mũi tên Upload, chờ SUCCESS)

### B.3 — Mở Serial Monitor

Làm y hệt bước A.3. Sẽ thấy:

```
=======================================================
   WEARABLE MONITOR — FreeRTOS v1
   CPU: 240 MHz  |  Free heap: 312.4 KB
=======================================================
[OK]  Sensors initialized.
[BLE] Advertising: WearableMonitor
[OK]  4 FreeRTOS tasks created.

>activity:0|bpm:75.00|heap:298432
>activity:0|bpm:75.00|heap:298432
...
```

Nếu thấy những dòng `>activity:...|bpm:...` chạy liên tục → firmware đang hoạt động bình thường.

### B.4 — Kiểm tra Bluetooth trên điện thoại

1. Tải app **nRF Connect** trên điện thoại  
   - iPhone: App Store → tìm "nRF Connect"  
   - Android: CH Play → tìm "nRF Connect for Mobile"

2. Mở app → nhấn **SCAN**

3. Tìm trong danh sách tên **`WearableMonitor`**

4. Nếu thấy tên đó → chụp ảnh màn hình → gửi cho Giang ✓

5. Nếu không thấy sau 30 giây → thử tắt Bluetooth điện thoại rồi bật lại → scan lại

### B.5 — Gửi kết quả cho Giang

Gửi cho Giang:
- Ảnh chụp màn hình nRF Connect thấy `WearableMonitor`
- Ảnh chụp Serial Monitor đang chạy `>activity:...|bpm:...`

---

## Xử lý lỗi thường gặp

| Lỗi thấy | Cách xử lý |
| :--- | :--- |
| `Port not found` hoặc `No device` | Rút cáp USB → cắm lại → Upload lại |
| `Board not found` | Tắt VS Code → mở lại → thử lại |
| `Compilation error` | Chụp màn hình → nhắn Giang, không tự sửa |
| Serial Monitor không hiện chữ | Kiểm tra baud rate phải là **115200** |
| Board không lên đèn khi cắm USB | Thử cáp USB khác hoặc cổng USB khác |
| nRF Connect không thấy `WearableMonitor` | Bật lại Bluetooth → scan lại; đảm bảo firmware `freertos_v1` đã được nạp |

---

## Tóm tắt nhanh (checklist)

**Cài một lần:**
- [ ] Cài VS Code
- [ ] Cài extension PlatformIO

**Nhiệm vụ A (baseline):**
- [ ] Tải code, mở folder trong VS Code
- [ ] Cắm board, chọn env `baseline`, nhấn Upload
- [ ] Mở Serial Monitor, chờ 60 giây
- [ ] Copy toàn bộ output gửi Giang

**Nhiệm vụ B (FreeRTOS + BLE):**
- [ ] Chọn env `freertos_v1`, nhấn Upload
- [ ] Mở Serial Monitor — thấy `>activity:...|bpm:...` chạy liên tục
- [ ] Tải nRF Connect, scan thấy `WearableMonitor`
- [ ] Chụp ảnh gửi Giang

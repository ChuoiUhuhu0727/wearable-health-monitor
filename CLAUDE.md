# Wearable Health Monitor — Claude Code Project Instructions

## CHANGELOG.md — bắt buộc cập nhật

Sau bất kỳ thay đổi nào ở mức **boundary/interface** (không phải chi tiết
implementation), thêm 1 entry 2-3 dòng vào `CHANGELOG.md` ở repo root.

**Boundary/interface nghĩa là gì** — phép thử: "nếu đổi chỗ này mà KHÔNG đi sửa 1
file/phần khác, thì phần đó có vỡ ngầm không?" Có → phải ghi. Không → bỏ qua.

Ví dụ cần ghi:
- Đổi schema data giữa firmware và script (BLE JSON payload, cột CSV)
- Đổi giao thức/kiến trúc transport (VD: pivot WiFi → BLE)
- Đổi hợp đồng giữa các task/module (kiểu dữ liệu qua FreeRTOS queue)
- Đổi quy trình ảnh hưởng người khác (VD: cách teammate nộp data)

Ví dụ KHÔNG cần ghi: sửa bug nội bộ 1 hàm, đổi tên biến, tối ưu thuật toán mà
input/output không đổi, thêm log debug.

Format mỗi entry:
```
## YYYY-MM-DD — <tên ngắn gọn>
<đổi gì> — <tại sao>. (2-3 dòng, không hơn)
```

Mục đích: file này là report material cuối ngày/tuần cho vịt, và là checkpoint để
đọc lại nắm được kiến trúc hệ thống mà không cần nhớ từng bug/detail đã fix.

## Ngôn ngữ
Chat bằng tiếng Việt, ngắn gọn, trực tiếp — theo phong cách đã thiết lập trong các
phiên trước với vịt.

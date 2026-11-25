# GĐ38 — RELIABILITY REMEDIATION (INHERITED FROM GĐ36 & GĐ37)

## 1. US Stock Session Hours Calendar (`libs/bot/experiments/calendar.py`)
Giải quyết triệt để vấn đề chuyển đổi múi giờ và lịch giao dịch chứng khoán Mỹ:
- **Múi giờ**: `America/New_York` (xử lý động EST/EDT qua `zoneinfo.ZoneInfo`).
- **Giờ giao dịch chuẩn**: 09:30:00 — 16:00:00 Eastern Time.
- **Ngày đóng cửa sớm (Early Close)**: 13:00:00 Eastern Time (ví dụ: Black Friday, ngày trước 4/7, Christmas Eve).
- **Ngày lễ thị trường (Official Holidays)**: New Year's Day, Martin Luther King Jr. Day, Presidents' Day, Good Friday, Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas Day (áp dụng quy tắc dời ngày nghỉ bù thứ Hai nếu trùng cuối tuần).
- **Phiên bản chính sách**: `policy_version = "2026.1"`.

## 2. Economic Sequence Fingerprint (`libs/bot/experiments/fingerprint.py`)
Mã băm SHA-256 chuỗi sự kiện kinh tế hoàn chỉnh:
$$\text{StrategySignal} \longrightarrow \text{SignalDecision} \longrightarrow \text{SimulationOrderIntent} \longrightarrow \text{SimulatedOrder} \longrightarrow \text{SimulatedFill} \longrightarrow \text{PortfolioTransaction}$$
- Bỏ qua các định danh ngẫu nhiên tạm thời (ephemeral UUIDs), chỉ băm các giá trị nghiệp vụ bất biến: symbol, side, price, quantity, state, order_type, timestamp.
- Bảo đảm tính tái lập bit-to-bit qua các lần chạy độc lập.

## 3. GĐ37 Queue Overflow Reliability Remediation (`dispatcher.py`, `supervisor.py`)
Khắc phục nguy cơ bot giao dịch trên dữ liệu thiếu hụt khi hàng đợi bị tràn:
- **Fail-Closed State Transition**: Khi một bot gặp `DROPPED_QUEUE_FULL`, dispatcher đánh dấu bot vào danh sách `_gap_blocked_bots` và kích hoạt chuyển trạng thái session sang `DATA_GAP_BLOCKED`.
- **Chặn phát sinh lệnh**: Trong trạng thái `DATA_GAP_BLOCKED`, bot hoàn toàn ngừng sinh tín hiệu và không tạo lệnh mới.
- **Backlog Replay & Gap Reconciliation**: Cung cấp cơ chế `reconcile_data_gap(bot_id, missing_events)` để nạp bù nến bị thiếu theo đúng thứ tự thời gian trước khi phục hồi về trạng thái `RUNNING`.
- **Cách ly hoàn hảo với bot đồng cấp**: Các bot khác trong hệ thống tiếp tục nhận và xử lý nến bình thường (`ENQUEUED`), hoàn toàn không bị ảnh hưởng bởi bot bị nghẽn.

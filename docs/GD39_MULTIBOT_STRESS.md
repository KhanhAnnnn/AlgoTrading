# GĐ39 — MULTI-BOT STRESS & RESOURCE ISOLATION

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ39 — End-to-End Integration, Short Soak & Reliability Verification  
**Môi trường:** SIMULATION ONLY  

---

## 1. Mục tiêu Kiểm chứng Cách ly Đa Bot (Multi-Bot Isolation)

Đảm bảo hệ thống có khả năng vận hành đồng thời nhiều Paper Trading Bot mô phỏng với các chiến lược và cấu hình khác nhau mà không xảy ra bất kỳ sự can thiệp chéo (cross-contamination) hoặc suy giảm hiệu năng nào.

---

## 2. Các Lớp Cách ly Đã Được Kiểm Chứng

### A. Cách ly Tài chính & Vị thế
- Mỗi Bot vận hành trên một `SimulationPortfolioManager` độc lập.
- Tiền mặt ban đầu (`initial_cash`), số dư khả dụng (`available_cash`), và tiền ký quỹ (`reserved_cash`) hoàn toàn tách biệt.
- Bot A thực hiện giao dịch NVDA không làm thay đổi số dư hoặc vị thế của Bot B (ngay cả khi Bot B cũng đăng ký cùng mã NVDA).

### B. Cách ly Sổ lệnh & Lịch sử Khớp lệnh
- Mỗi Bot có một `SimulationBroker` và `OrderManager` riêng.
- Lệnh mở, lệnh hủy và khớp lệnh của Bot A không xuất hiện trong sổ lệnh của Bot B.
- Khóa trùng lặp (`idempotency_key`) được gắn nhãn theo phiên làm việc của từng Bot.

### C. Cách ly Quản lý Rủi ro & Drawdown
- Mỗi Bot có một `SignalDecisionEngine` và `DrawdownMonitor` riêng.
- Nếu Bot A chạm ngưỡng dừng lỗ tối đa hoặc drawdown limit dẫn đến trạng thái `RISK_LOCKED`, Bot B hoàn toàn không bị ảnh hưởng và vẫn tiếp tục giao dịch bình thường nếu điều kiện danh mục của Bot B an toàn.

### D. Khoanh vùng Bán kính Thiệt hại (Blast Radius Containment)
- Khi một Bot gặp lỗi nghiêm trọng (Exception trong quá trình tính toán chỉ báo hoặc lỗi giả lập), chỉ riêng Bot đó chuyển sang trạng thái `ERROR`.
- `MultiBotSupervisor` ghi nhận lỗi và duy trì các Bot còn lại ở trạng thái `RUNNING`.

---

## 3. Thực thi Giới hạn Tài nguyên (Resource Policy Enforcement)

- Giới hạn số lượng Bot đồng thời (`max_concurrent_bots = 10`): Khi cố gắng khởi động bot thứ 11, hệ thống ném ra `ConcurrencyLimitExceededError` một cách fail-closed.
- Giới hạn hàng đợi sự kiện (`max_queue_size_per_bot = 1000`): Ngăn ngừa rò rỉ bộ nhớ do tích tụ hàng đợi.
- Thời gian dừng an toàn (`shutdown_timeout_seconds = 5.0`): Hỗ trợ dừng tuần tự từng bot hoặc toàn bộ bot (`shutdown_all()`) mà không làm nghẽn tiến trình chính.

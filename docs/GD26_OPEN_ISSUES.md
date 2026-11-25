# GĐ26: Open Issues & Post-Release Bug Tracking Register

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ26 — Post-Release Stabilization & Maintenance  
**Status:** `TRACKED — ACCEPTABLE_RISK`  
**Evaluation Timestamp:** `2026-10-31T21:46:00+07:00`

---

## 1. Tổng quan Sổ theo dõi Lỗi (Bug Tracking Register)

Báo cáo này hệ thống hóa các phát hiện kỹ thuật, giới hạn đã biết (Known Limitations), và các vấn đề mở ghi nhận được trong quá trình vận hành sau phát hành v1.0.0. Tất cả các phát hiện đã được phân loại mức độ nghiêm trọng, phân tích nguyên nhân gốc rễ, và xác nhận không ảnh hưởng đến tính toàn vẹn của chốt an toàn `DRY_RUN` hay cổng `PaperExecutionGate`.

---

## 2. Ma trận Phân loại Mức độ Nghiêm trọng

| Mã Vấn đề | Tiêu đề | Phân loại | Mức độ | Trạng thái | Đánh giá Rủi ro |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ISSUE-26-01** | Cảnh báo Data Stale khi ngoài giờ mở cửa sàn chứng khoán | Data Engine | **LOW** | *Mitigated (Đã xử lý)* | Không có rủi ro; đã bổ sung phân loại `IDLE_MARKET_CLOSED` |
| **ISSUE-26-02** | Khác biệt định dạng số dư giữa snapshot REST và WebSocket Alpaca | Broker Sync | **LOW** | *Mitigated (Đã xử lý)* | Không có rủi ro; ưu tiên REST snapshot làm chân lý (Ground Truth) |
| **ISSUE-26-03** | Thiếu tính năng tự động xoay vòng log nền trong file compose | DevOps | **MEDIUM**| *Resolved (Đã xử lý)* | Đã chuẩn hóa bằng [scripts/rotate_logs.ps1](file:///d:/AlgoTrading/scripts/rotate_logs.ps1) |
| **ISSUE-26-04** | Trạng thái Mock Broker lưu cục bộ trên file JSON đơn lẻ | Storage | **LOW** | *Accepted Limitation* | Phù hợp cho chế độ Dry-Run; đã có backup tự động |
| **ISSUE-26-05** | Nút gửi lệnh trên giao diện hiển thị cảnh báo đỏ khi chọn Alpaca Paper | UI / UX | **INFO** | *By Design (Cố ý)* | Tính năng an toàn: Nhắc nhở người dùng cổng thực thi đang khóa |

---

## 3. Phân tích Chi tiết Từng Vấn đề

### ISSUE-26-01: Cảnh báo Data Stale khi ngoài giờ mở cửa sàn chứng khoán
- **Hiện tượng:** Vào các ngày cuối tuần hoặc ngoài giờ giao dịch US Equities (sau 16:00 EST), các ticks cổ phiếu (AAPL, MSFT, NVDA) không phát sinh dữ liệu mới, khiến bộ đếm trễ vượt ngưỡng $120\text{ giây}$.
- **Nguyên nhân gốc rễ:** Sàn chứng khoán thực tế đóng cửa; pipeline không nhận được nến mới.
- **Biện pháp xử lý:** Cập nhật logic đánh giá sức khỏe trong backend: Khi ngoài khung giờ giao dịch US Market, chuyển trạng thái luồng cổ phiếu sang `IDLE_MARKET_CLOSED` thay vì báo `WARNING` hay `CRITICAL`. Luồng Crypto vẫn kiểm tra 24/7.
- **Trạng thái:** **MITIGATED & VERIFIED**.

---

### ISSUE-26-02: Khác biệt định dạng số dư giữa snapshot REST và WebSocket Alpaca
- **Hiện tượng:** Alpaca REST API trả về các giá trị số dư dưới dạng chuỗi có định dạng (ví dụ `"100000.00"`), trong khi WebSocket message trả về số thực (ví dụ `100000.0`).
- **Nguyên nhân gốc rễ:** Chuẩn hóa khác nhau giữa hai giao thức của Alpaca Paper API.
- **Biện pháp xử lý:** Triển khai lớp chuyển đổi `Pydantic` trong `libs/alpaca_paper_sdk.py` và `main.py` để ép kiểu dữ liệu đồng nhất sang `float` với làm tròn 2 chữ số thập phân (`round(val, 2)`).
- **Trạng thái:** **MITIGATED & VERIFIED**.

---

### ISSUE-26-03: Nguy cơ tệp log tăng trưởng dung lượng không giới hạn
- **Hiện tượng:** Các daemon chạy nền (`task-4640`, `task-4644`, Flink JobManager) liên tục ghi nhật ký, dẫn tới dung lượng các tệp trong `logs/` có thể vượt quá $100\text{ MB}$ sau nhiều tuần vận hành.
- **Nguyên nhân gốc rễ:** Hệ điều hành Windows và Docker Compose mặc định không tích hợp logrotate tự động như Linux systemd.
- **Biện pháp xử lý:** Phát triển script [scripts/rotate_logs.ps1](file:///d:/AlgoTrading/scripts/rotate_logs.ps1), tự động nén và lưu trữ các tệp log $\ge 10\text{ MB}$ vào [logs/archive/](file:///d:/AlgoTrading/logs/archive/).
- **Trạng thái:** **RESOLVED & VERIFIED**.

---

### ISSUE-26-04: Trạng thái Mock Broker lưu trên tệp JSON đơn lẻ
- **Hiện tượng:** Tệp [data/mock_broker/mock_broker_state.json](file:///d:/AlgoTrading/data/mock_broker/mock_broker_state.json) là nguồn lưu trữ duy nhất của các giao dịch mô phỏng.
- **Nguyên nhân gốc rễ:** Kiến trúc tối giản không sử dụng database nặng (PostgreSQL/MySQL) nhằm phục vụ mục đích kiểm thử nhẹ và độc lập.
- **Biện pháp xử lý:** Triển khai cơ chế sao lưu tự động [scripts/backup_system.ps1](file:///d:/AlgoTrading/scripts/backup_system.ps1) và khôi phục [scripts/restore_system.ps1](file:///d:/AlgoTrading/scripts/restore_system.ps1) có hỗ trợ dry-run.
- **Trạng thái:** **ACCEPTED AS KNOWN LIMITATION** (Đạt yêu cầu cho phiên bản v1.0.0).

---

### ISSUE-26-05: Nút gửi lệnh trên UI hiển thị cảnh báo đỏ khi chọn Alpaca Paper
- **Hiện tượng:** Khi người dùng chuyển sang tab `ALPACA_PAPER` trên Trading Workbench Panel, nút "Submit Order" bị vô hiệu hóa kèm nhãn cảnh báo `"EXECUTION GATE CLOSED (DRY-RUN)"`.
- **Nguyên nhân gốc rễ:** Thiết kế bảo mật có chủ đích (Security by Design).
- **Biện pháp xử lý:** Đây là tính năng an toàn cốt lõi ngăn ngừa việc vô tình kích hoạt lệnh khi chưa được cấp phép. Phía backend trả về HTTP 403 Forbidden nếu có request bypass client.
- **Trạng thái:** **CLOSED — BY DESIGN**.

---

## 4. Kết luận Đánh giá Rủi ro

Không có bất kỳ lỗi loại **P0 (Critical)** hoặc **P1 (High)** nào tồn đọng. Tất cả các mục trong sổ theo dõi lỗi đều thuộc diện quản lý được, có giải pháp giảm thiểu rõ ràng, và hoàn toàn thỏa mãn tiêu chí vận hành ổn định sau phát hành của phiên bản v1.0.0.


# GĐ28: Final Known Limitations & Constraints Register

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ28 — V1.0 Final Acceptance & Project Closure  
**Status:** `DOCUMENTED & FORMALLY_ACCEPTED`  
**Evaluation Timestamp:** `2026-10-31T22:42:00+07:00`

---

## 1. Mục tiêu Danh mục Giới hạn Đã Biết

Tài liệu này xác lập minh bạch và trung thực các giới hạn kỹ thuật (Known Limitations), các phát hiện mở (Open Findings) và các ràng buộc vận hành của phiên bản phát hành v1.0.0. Toàn bộ các giới hạn này đã được phân loại mức độ rủi ro, có phương án kiểm soát chặt chẽ và được chấp thuận chính thức trước khi đóng phạm vi V1.0.

---

## 2. Bảng Tổng hợp Các Giới hạn & Phát hiện Mở

| Mã Giới hạn | Tiêu đề | Phân loại | Mức độ | Trạng thái Chấp thuận | Ghi chú & Tác động |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **OF-01** | Phiên ngâm GĐ18 bị gián đoạn (Interrupted Soak) | Reliability | **MEDIUM**| `CONDITIONALLY_ACCEPTED` | Tổng thời gian lịch đạt 170.06h nhưng bị gián đoạn bởi host idle / engine timeout |
| **OF-02** | Nguồn gốc dữ liệu tick NVDA ngoài giờ chưa được xác thực độc lập | Market Data | **LOW** | `CONDITIONALLY_ACCEPTED` | Cuối tuần sàn chứng khoán đóng cửa; pipeline gán nhãn `IDLE_MARKET_CLOSED` |
| **OF-03** | Cổng thực thi Alpaca Paper khóa chặt (Execution Locked) | Security | **INFO** | `BY_DESIGN_ACCEPTED` | Chốt an toàn: Giữ chế độ Read-Only để bảo vệ tài khoản |
| **OF-04** | Tuyến giao dịch tiền thật không tồn tại (Live Prohibited) | Safety | **INFO** | `BY_DESIGN_ACCEPTED` | Rào cản bảo vệ tài chính: Cấm tuyệt đối Live Trading |
| **OF-05** | Hiệu suất chiến lược không cam kết lợi nhuận tài chính | Financial | **INFO** | `BY_DESIGN_ACCEPTED` | Nền tảng phục vụ mục đích phân tích kỹ thuật và mô phỏng giáo dục |
| **OF-06** | Trạng thái Mock Broker lưu trên tệp JSON đơn lẻ | Architecture| **LOW** | `ACCEPTED_LIMITATION` | Đã có cơ chế sao lưu tự động và khôi phục cô lập đạt RTO $0.067\text{s}$ |

---

## 3. Phân tích Chi tiết Từng Giới hạn

### OF-01: GĐ18 Operational Soak Closeout (Interrupted Soak)
- **Bản chất kỹ thuật:** Trong giai đoạn ngâm 168 giờ (GĐ18), tổng thời gian theo dõi lịch từ baseline đạt $170.06\text{ giờ}$. Tuy nhiên, tiến trình Docker Desktop daemon trên hệ điều hành Windows gặp phải một số lần timeout / restart do chế độ sleep / idle của máy chủ.
- **Tuyên ngôn trung thực:** Không tuyên bố hệ thống đạt 168 giờ uptime liên tục không gián đoạn. Kết quả được nghiệm thu có điều kiện theo phân loại:
  ```
  CONDITIONALLY_ACCEPTED — CLOSEOUT_INTERRUPTED_SOAK
  ```
- **Biện pháp kiểm soát:** Đã thiết lập các tác vụ bảo trì tự động [scripts/rotate_logs.ps1](file:///d:/AlgoTrading/scripts/rotate_logs.ps1) và kịch bản khôi phục [scripts/disaster_recovery_engine.py](file:///d:/AlgoTrading/scripts/disaster_recovery_engine.py).

---

### OF-02: Dữ liệu Cổ phiếu Ngoài Khung giờ Giao dịch (Market Closed Behavior)
- **Bản chất kỹ thuật:** Thị trường chứng khoán Mỹ chỉ giao dịch từ 09:30 đến 16:00 EST từ Thứ Hai đến Thứ Sáu. Ngoài khung giờ này và vào cuối tuần, sàn không phát sinh nến giá thực tế.
- **Biện pháp xử lý:** Backend phân loại trạng thái luồng cổ phiếu sang `IDLE_MARKET_CLOSED` thay vì báo lỗi mất dữ liệu. Luồng Crypto tiếp tục chạy 24/7.

---

### OF-03 & OF-04: Khóa Thực thi Lệnh và Cấm Live Trading
- **Bản chất kỹ thuật:** Cổng `PaperExecutionGate.is_gate_open` cố định bằng `False`. Bất kỳ lệnh ghi nào đều bị máy chủ từ chối với mã HTTP 403 Forbidden.
- **Đánh giá rủi ro:** Đây là thiết kế bảo vệ chủ động (Security by Design), hoàn toàn phù hợp với phạm vi phát hành V1.0.

---

### OF-05: Tuyên bố Miễn trừ Lợi nhuận Chiến lược (Profitability Disclaimer)
- **Tuyên bố pháp lý & kỹ thuật:** Các tín hiệu mua/bán (Buy/Sell signals) và đường SMA hiển thị trên Dashboard được xây dựng nhằm mục đích thử nghiệm thuật toán và nghiên cứu khoa học. Người vận hành không sử dụng hệ thống như một khuyến nghị đầu tư tài chính được chứng nhận.


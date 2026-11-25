# GĐ25 — SỔ CÁI ĐÓNG CÁC PHÁT HIỆN MỞ (MASTER OPEN FINDINGS CLOSEOUT)
## BẢNG TỔNG HỢP TRẠNG THÁI CUỐI CÙNG VÀ CƠ CHẾ GIẢM THIỂU RỦI RO

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ25 — Final Release & Operational Sign-off  
**Thời điểm lập sổ:** 31/10/2026 14:00:00 UTC (21:00:00 ICT)  
**Tiêu chí kiểm định liên quan:** TC-G25-06, Toàn bộ chuỗi kiểm toán GĐ18–GĐ25  

---

## 1. Sổ Cái Đóng Các Phát Hiện Mở GĐ18 (OF-01 đến OF-05)

| Mã Phát Hiện | Tiêu Đề Phát Hiện Kỹ Thuật | Phân Loại Rủi Ro | Trạng Thái Cuối Cùng | Căn Cứ Đóng Hồ Sơ & Cơ Chế Giảm Thiểu |
| :---: | :--- | :---: | :---: | :--- |
| **OF-01** | Kết quả phiên ngâm độ bền 168 giờ liên tục | Thấp | **`CONDITIONALLY_ACCEPTED`** | Cửa sổ thời gian lịch trình đạt 170.06h (> 168h target). Không đánh dấu PASS giả tạo do ghi nhận các chu kỳ máy trạm Windows sleep/idle làm ngắt quãng phiên đơn liên tục. Uptime tích lũy thực tế đạt > 142.5h với 0 lỗi checkpoint RocksDB và 0 sự cố rò rỉ bộ nhớ. |
| **OF-02** | Thiếu chứng từ gốc cho các giao dịch nạp tiền & mua ban đầu | Thấp | **`PROVENANCE_UNCONFIRMED`** | Bảo lưu trạng thái này theo chuẩn kiểm toán kế toán độc lập. Các giao dịch được phản ánh trong sổ cái `GET /api/paper/activities` của Alpaca Paper, nhưng không có biên lai PDF ngoài đời thực tương ứng. |
| **OF-03** | Hiện tượng nến trùng timestamp $\Delta t = 0\text{s}$ trên luồng Crypto | Rất thấp | **`RESOLVED_BY_DESIGN`** | Xác nhận là thiết kế chuẩn của Alpaca WebSocket v2: nến cập nhật (`is_final=false`) xuất hiện sau nến chốt ban đầu. Hệ thống đã xử lý khử trùng lặp an toàn qua khóa tổng hợp `symbol:event_time:signal`. |
| **OF-04** | Nguy cơ nhầm lẫn giữa dữ liệu tự nhiên và dữ liệu thử nghiệm | Trung bình | **`RESOLVED_BY_DESIGN`** | Thiết lập rào chắn cô lập tuyệt đối: không bao giờ bơm dữ liệu mock/fixture vào các topic Kafka tự nhiên. Mọi thao tác mô phỏng được định tuyến vào `data/mock_broker/mock_broker_state.json`. |
| **OF-05** | Phân loại dữ liệu trễ đối với cổ phiếu ngoài giờ giao dịch | Thấp | **`RESOLVED_BY_DESIGN`** | Tích hợp đồng hồ thị trường (`market_clock`) tự động phân loại đúng trạng thái `IDLE_MARKET_CLOSED` thay vì báo lỗi hệ thống `DOWN` hoặc `STALE` sai lệch. |

---

## 2. Sổ Cái Đóng Các Phát Hiện Bổ Sung Tại GĐ24 & GĐ25

| Mã Phát Hiện | Tiêu Đề Phát Hiện | Trạng Thái Cuối Cùng | Giải Trình Toán Học & Kỹ Thuật Chi Tiết |
| :---: | :--- | :---: | :--- |
| **F-G24-02** | Chênh lệch sức mua (Buying Power Variance) $\Delta \text{BP} = \$6.83$ | **`RESOLVED_BY_DESIGN`** | Đã giải trình bằng công thức ký quỹ Margin Reg-T 4x: Sự thay đổi giá thị trường của đúng $1.0$ cổ phiếu NVDA nắm giữ $(\$215.35 \to \$208.52)$ làm giảm giá trị danh mục $\$6.83$, tương ứng giảm sức mua đúng $\$6.83$. Số dư tiền mặt giữ nguyên $\$99,773.38$. |
| **F-G24-03** | Khối lượng nắm giữ BTC ($0.000120008$) nhỏ hơn khối lượng mua ($0.000120309$) | **`RESOLVED_BY_DESIGN`** | Đã đối soát chính xác tới cấp độ Satoshi ($10^{-8}\text{ BTC}$): Khoản phí giao dịch `CFEE` được trừ trực tiếp bằng tiền mã hóa: $0.000120309 - 0.000000301 = 0.000120008\text{ BTC}$. |
| **F-G24-04** | Chuẩn hóa phân loại 4 loại hoạt động qua 5 bản ghi | **`RESOLVED_BY_DESIGN`** | Sổ cái nghiệp vụ gồm 4 loại hình (`JNLC`, `FILL`, `CFEE`, `FEE`) phân bổ trên đúng 5 bản ghi lịch sử, đối soát số dư tiền mặt khớp chính xác từng cent $(\$99,773.38)$. |
| **F-G25-01** | Kiểm soát quyền hạn máy chủ cho broker đích (Server-Side Authority) | **`RESOLVED_BY_DESIGN`** | Backend FastAPI cưỡng chế trả về `HTTP 403 Forbidden` khi phát hiện `target_broker="ALPACA_PAPER"` trong chế độ `DRY_RUN`. |
| **F-G25-02** | Đóng mặc định cổng thực thi (Fail-Closed Execution Gate) | **`RESOLVED_BY_DESIGN`** | `paper_gate.is_gate_open = False` theo mặc định, loại trừ hoàn toàn nguy cơ đặt lệnh thật vô ý. |

---

## 3. Kết Luận Kiểm Toán Hồ Sơ (Audit Summary)

Tất cả các phát hiện kỹ thuật phát sinh trong suốt vòng đời dự án (từ GĐ18 đến GĐ25) đều đã được phân loại minh bạch, đối soát số liệu chuẩn xác hoặc đóng lại với phán quyết kỹ thuật rõ ràng. Không còn bất kỳ phát hiện nghiêm trọng (Critical/High Severity) nào chưa được xử lý.


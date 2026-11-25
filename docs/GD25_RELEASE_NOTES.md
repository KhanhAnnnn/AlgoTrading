# GĐ25 — BẢN GHI PHÁT HÀNH CHÍNH THỨC (OFFICIAL RELEASE NOTES)
## ALGOTRADING PLATFORM — PHIÊN BẢN CHÍNH THỨC V1.0.0

**Mã phiên bản:** `v1.0.0` (Thương mại ổn định)  
**Thời điểm phát hành:** 31/10/2026 14:00:00 UTC (21:00:00 ICT)  
**Kho mã nguồn:** `D:\AlgoTrading`  
**Chế độ mặc định:** `TRADING_MODE=DRY_RUN`  
**Cổng an toàn:** `PaperExecutionGate: CLOSED (Fail-Closed)`  

---

## 1. Giới Thiệu Phiên Bản v1.0.0

Phiên bản **AlgoTrading v1.0.0** là bước chuyển dịch toàn diện, đưa hệ thống từ giai đoạn nghiên cứu thử nghiệm (R&D) sang một nền tảng phân tích định lượng, giám sát luồng dữ liệu thời gian thực và mô phỏng giao dịch thương mại ổn định (**Commercial-Grade Platform**).

Sản phẩm được thiết kế để phục vụ hai nhóm đối tượng:
- **Chuyên viên Vận hành Hệ thống (DevOps / SRE):** Giám sát cụm phân tán Redpanda, Flink streaming, kiểm soát độ trễ hàng đợi, đo nhịp tim tiến trình theo mô hình 5 trụ cột sức khỏe.
- **Chuyên viên Phân tích & Giao dịch (Quants / Traders):** Theo dõi thị trường chứng khoán và crypto, phân tích sắc thái tin tức vĩ mô, đối soát tài khoản danh mục Alpaca Paper chỉ đọc, và thử nghiệm chiến lược giao dịch tự động trong trạm làm việc mô phỏng hoàn toàn an toàn.

---

## 2. Các Tính Năng Nổi Bật (Key Highlights)

### 2.1. Trục Giám Sát Thị Trường Thông Minh (Market Intelligence)
- **Luồng Dữ liệu Thời Gian Thực Phân Tán:** Tích hợp cụm Redpanda 2 brokers thu nạp liên tục các luồng `crypto-bars-1m`, `crypto-trades`, `crypto-news`, `stock-prices` và `market-news`.
- **Biểu Đồ Nến Đa Khung Thời Gian:** Hiển thị biểu đồ nến tương tác chất lượng cao cho Stocks (AAPL, NVDA) và Crypto (BTC/USD, ETH/USD).
- **Chỉ Báo Kỹ Thuật Định Lượng:** Tích hợp đường trung bình động SMA(20), SMA(50), chỉ báo sức mạnh tương đối RSI, dao động phân kỳ MACD.
- **Phân Tích Cảm Tính Tin Tức (News Sentiment):** Hệ thống phân loại sắc thái tin tức tự động, hỗ trợ nhà đầu tư nắm bắt nhanh tâm lý thị trường.

### 2.2. Trục Quản Lý Danh Mục & Lệnh Thật Chỉ Đọc (Portfolio & Order Management)
- **Đồng Bộ Dữ Liệu Alpaca Paper Chỉ Đọc (Read-Only):** Tải trực tiếp thông tin tài khoản `PA31BG5IX`, số dư tiền mặt $(\$99,773.38)$, sức mua đòn bẩy ký quỹ Reg-T 4x $(>\$300,000)$, và trạng thái `ACTIVE`.
- **Danh Mục Vị Thế Thật:** Hiển thị vị thế nắm giữ gốc ($1.0\text{ NVDA}$ và $0.000120008\text{ BTC}$) với độ chính xác toán học khớp từng Satoshi.
- **Sổ Cái Nghiệp Vụ Hoạt Động (Activities Ledger):** Quản lý và đối soát 4 loại nghiệp vụ (`JNLC`, `FILL`, `CFEE`, `FEE`) trải đều trên 5 bản ghi lịch sử.

### 2.3. Trục Trạm Làm Việc Giao Dịch Mô Phỏng (Trading Workbench)
- **Hỗ Trợ 5 Loại Lệnh Giao Dịch Tiêu Chuẩn:** Đặt lệnh Thị trường (Market), Lệnh Giới hạn (Limit), Lệnh Dừng (Stop), Dừng Giới hạn (Stop-Limit) và Dừng Bám theo (Trailing Stop).
- **Giao Dịch Nâng Cao:** Hỗ trợ đặt lệnh phân số (Fractional Qty) và lệnh theo số tiền USD (Notional Dollar Orders) với quy đổi tỷ giá tự động.
- **Quản Trị Lệnh Mở:** Cho phép sửa lệnh treo tại chỗ (In-Flight Replace) kế thừa thuộc tính liên kết `replaces`, và hủy hàng loạt (Bulk Cancel) trong trường hợp khẩn cấp.
- **Lưu Trữ Tách Biệt & Đặt Lại An Toàn:** Dữ liệu mô phỏng được lưu trữ độc lập tại [`data/mock_broker/mock_broker_state.json`](file:///d:/AlgoTrading/data/mock_broker/mock_broker_state.json). Nút bấm "Reset Simulation" phục hồi ngay $\$100,000.00$ tiền mặt mock mà không ảnh hưởng tài khoản Alpaca Paper.

### 2.4. Độ Bền Luồng & Tự Phục Hồi (Resilience & Self-Healing)
- **Khử Trùng Lặp Luồng (Deduplication):** Tự động loại bỏ các bản tin sự kiện trùng lặp thông qua khóa `event:order_id:timestamp`.
- **Bảo Vệ Thứ Tự Đơn Điệu (Monotonic Hierarchy):** Ngăn ngừa tình trạng các sự kiện mạng trễ đè bẹp các trạng thái hoàn tất cuối cùng (`filled`).
- **Tự Hàn Gắn Sau Mất Mạng (REST Reconciliation):** Tự động truy vấn REST để bù đắp các trạng thái bị gián đoạn ngay khi kết nối mạng phục hồi.

---

## 3. Ranh Giới Phạm Vi & Cảnh Báo An Toàn (Scope & Boundaries)

> [!CAUTION]
> **Tuyên bố Ranh Giới Sản Phẩm Bắt Buộc:**
> - Bản phát hành **v1.0.0** hoạt động ở chế độ thử nghiệm **`TRADING_MODE=DRY_RUN`**.
> - Cổng thực thi lệnh thật **`PaperExecutionGate` ĐANG ĐÓNG** (Fail-Closed).
> - **TUYỆT ĐỐI KHÔNG** hỗ trợ giao dịch Live bằng tiền thật. Không có bất kỳ tuyến gọi mạng nào cho phép gửi lệnh ra sàn giao dịch ngoài đời thực.
> - Tính năng Alpaca Paper hoạt động ở chế độ **CHỈ ĐỌC (READ-ONLY)** để theo dõi số dư, danh mục và lịch sử.
> - Toàn bộ thao tác gửi lệnh, sửa lệnh và hủy lệnh trên giao diện Workbench đều được định tuyến vào **Mock Broker nội bộ**.

---

## 4. Tóm Tắt Kết Quả Kiểm Thử Chất Lượng (Quality Verification)

Hệ thống đã vượt qua toàn bộ chuỗi kiểm định chất lượng:
- **Kiểm thử GĐ25:** **26 / 26 Đạt (100%)**
- **Kiểm thử Hồi quy GĐ20–GĐ24:** **130 / 130 Đạt (100%)**
- **Tổng số ca kiểm thử thành công:** **156 / 156 Đạt (100% Zero-Regression)**
- **Biên dịch Frontend Sản xuất:** Vite build thành công trong 651ms với 0 lỗi TypeScript và 0 rò rỉ thông tin xác thực.


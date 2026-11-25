# GĐ20 — ĐẶC TẢ KIỂM CHỨNG TRADING WORKBENCH ĐẦU CUỐI
## END-TO-END TRADING WORKBENCH VALIDATION SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ20 — End-to-End Integration & Market Data Integrity  
**Môi trường:** Môi trường Test Khép kín (Mock Broker Engine)  
**Tệp dữ liệu trạng thái:** `data/mock_broker/mock_broker_state.json`  
**Bộ kiểm thử:** [`tests/test_gd20_e2e_integration.py`](file:///d:/AlgoTrading/tests/test_gd20_e2e_integration.py) (Các test từ TC-G20-09 đến TC-G20-18)  
**Tiêu chuẩn đối chiếu:** *Alpaca Markets Paper Trading Guide (Dec 2024)*  

---

## 1. Mục tiêu Kiểm định Workbench

Mục tiêu của phân hệ Trading Workbench trong GĐ20 là kiểm chứng năng lực vận hành đầu cuối từ giao diện web người dùng, qua REST API, đến động cơ khớp lệnh mô phỏng `MockTradingBroker`. Toàn bộ quy trình phải bảo đảm trải nghiệm giống 100% với tài liệu *Alpaca Paper Trading Guide* nhưng vận hành trong môi trường an toàn tuyệt đối.

---

## 2. Kết quả Kiểm chứng Chi tiết Từng Chức năng

### 2.1. Tải Tổng quan Tài khoản & Vị thế (TC-G20-09)
- **API Kiểm tra:** `GET /api/workbench/account` và `GET /api/workbench/positions`.
- **Kết quả Thực tế:**
  - `status: "ACTIVE"`
  - `currency: "USD"`
  - `cash: $100,000.00`
  - `equity: $100,000.00`
  - `buying_power: $400,000.00` (Chuẩn ký quỹ 4x Reg-T)
  - `is_mock: true`, `broker: "SIMULATED_MOCK_BROKER"`
- **Đánh giá:** Đáp ứng hoàn hảo cấu trúc tài khoản chuẩn Alpaca.

### 2.2. Đặt Lệnh Đa dạng Thể loại (TC-G20-10)
Đã thử nghiệm và kiểm chứng thành công cả 5 loại lệnh chuẩn:
1. **Market Order:** Tạo lệnh Mua 10 AAPL $\rightarrow$ Khớp lệnh tức thì (`status: "filled"`, `filled_qty: 10.0`), trừ tiền mặt và ghi nhận vị thế mới.
2. **Limit Order:** Tạo lệnh Mua 5 NVDA giá giới hạn $100.00 (thấp hơn thị giá) $\rightarrow$ Tiếp nhận vào hàng đợi chờ khớp (`status: "new"`, `filled_qty: 0.0`).
3. **Stop Order:** Tạo lệnh Bán 2 TSLA giá dừng $180.00 $\rightarrow$ Tiếp nhận vào hàng đợi chờ kích hoạt (`status: "new"`).
4. **Stop-Limit Order:** Tạo lệnh Mua 4 MSFT với stop $400.00 và limit $405.00 $\rightarrow$ Tiếp nhận vào hàng đợi (`status: "new"`).
5. **Trailing Stop Order:** Tạo lệnh Bán 0.1 BTC/USD với khoảng trượt $2.5\%$ (`trail_percent: 2.5`) $\rightarrow$ Tiếp nhận vào hàng đợi (`status: "new"`).

### 2.3. Lệnh Số lượng Lẻ & Giá trị Tiền mặt (TC-G20-11)
- **Fractional Shares:** Gửi lệnh mua `0.0452` BTC $\rightarrow$ Khớp chính xác `filled_qty: 0.0452`, tính đúng giá vốn và cập nhật vị thế crypto lẻ.
- **Notional Dollar Orders:** Gửi lệnh mua `$1,000.00` ETH/USD $\rightarrow$ Động cơ tự động quy đổi dựa trên thị giá hiện hành thành số lượng lẻ tương ứng và thực hiện khớp lệnh trọn vẹn.
- **Quy tắc Loại trừ Tương hỗ:** Gửi đồng thời cả `qty` và `notional` $\rightarrow$ Bị từ chối ngay với mã lỗi `400 Bad Request`.

### 2.4. Kiểm soát Tính Lũy thừa (Client Order ID Idempotency - TC-G20-12)
- Khởi tạo mã định danh duy nhất: `cid = "test_idempotent_e02e8a6a"`.
- Lần gửi 1: Thành công tạo lệnh (`200 OK`).
- Lần gửi 2 (trùng `cid`): Động cơ phát hiện xung đột và từ chối ngay lập tức:
  ```json
  {
    "detail": "Duplicate client_order_id 'test_idempotent_e02e8a6a'. Existing order: mock_ord_86e6963fb255430f"
  }
  ```
- **Ý nghĩa:** Ngăn chặn tuyệt đối rủi ro gửi lệnh trùng do thao tác double-click của người dùng hoặc do mạng truyền lại gói tin.

### 2.5. Lọc Danh sách Lệnh Đang Mở (TC-G20-13)
- **API Kiểm tra:** `GET /api/workbench/orders?status=open&symbol=AAPL`.
- **Kết quả:** Hệ thống lọc chính xác các lệnh thỏa mãn đồng thời:
  - Trạng thái thuộc tập hợp đang mở: `["new", "accepted", "pending_new", "partially_filled"]`.
  - Đúng mã tài sản được chỉ định (`symbol = "AAPL"`).

### 2.6. Sửa Lệnh Đang Chờ Khớp (Order Replacement - TC-G20-15)
- **API Kiểm tra:** `PATCH /api/workbench/orders/{order_id}` với payload sửa `{"qty": 8.0, "limit_price": 205.0}`.
- **Kết quả:**
  - Lệnh cũ chuyển trạng thái sang `replaced`.
  - Lệnh mới được tạo mang số lượng mới (`8.0`), giá giới hạn mới (`205.0`) và liên kết chặt chẽ với lệnh cũ thông qua trường `replaces: "mock_ord_b1c1bbd6b23a413c"`.

### 2.7. Hủy Lệnh Đơn lẻ và Hủy Hàng loạt (TC-G20-16)
- **Hủy Đơn lẻ:** `DELETE /api/workbench/orders/{order_id}` $\rightarrow$ Trạng thái chuyển thành `canceled`, giải phóng sức mua.
- **Hủy Hàng loạt (Bulk Cancel):** `DELETE /api/workbench/orders` $\rightarrow$ Quét toàn bộ sổ lệnh, hủy đồng loạt tất cả các lệnh mở và trả về danh sách các lệnh đã hủy:
  ```json
  {
    "canceled_count": 2,
    "canceled_orders": [...]
  }
  ```

### 2.8. Nhật ký Kiểm toán & Chi tiết Vòng đời (TC-G20-14, TC-G20-17)
- **Chi tiết Lệnh:** `GET /api/workbench/orders/{order_id}` trả về cấu trúc gồm cả thông số lệnh (`order`) và chuỗi sự kiện vòng đời (`activities`).
- **Nhật ký Kiểm toán Toàn cục:** `GET /api/workbench/activities` cung cấp danh sách bất biến ghi lại mọi thao tác phát sinh kèm dấu thời gian ISO 8601 UTC.

### 2.9. Bền vững Trạng thái qua Khởi động lại (TC-G20-18)
- Toàn bộ trạng thái số dư, danh mục vị thế, sổ lệnh và nhật ký được lưu trữ nguyên tử xuống đĩa tại `data/mock_broker/mock_broker_state.json`.
- Khi khởi động lại dịch vụ backend FastAPI, động cơ tự động đọc lại trạng thái từ tệp JSON, khôi phục nguyên vẹn 100% dữ liệu mô phỏng mà không làm mất mát thông tin.

---

## 3. Tuyên bố về Ranh giới Mô phỏng

> [!IMPORTANT]
> **Cam kết Cách ly Tuyệt đối:**
> 1. Mọi lệnh được tạo, sửa hoặc hủy trên Trading Workbench đều thuộc phạm vi quản lý của `MockTradingBroker`.
> 2. Các lệnh này **tuyệt đối KHÔNG được gửi tới hoặc khớp trên sàn giao dịch Alpaca**.
> 3. Toàn bộ đối tượng dữ liệu đều mang cờ nhận diện `is_mock: true` và `broker: "SIMULATED_MOCK_BROKER"`.

---

## 4. Kết luận Kiểm chứng

Phân hệ Trading Workbench hoạt động ổn định, chính xác, tương thích hoàn toàn với quy chuẩn nghiệp vụ của *Alpaca Markets Paper Trading Guide*, sẵn sàng phục vụ công tác đào tạo, kiểm thử giao diện và phát triển thuật toán giả lập.


# GĐ19 — THIẾT KẾ & ĐẶC TẢ ĐỘNG CƠ MÔ PHỎNG MOCK BROKER
## MOCK TRADING BROKER ENGINE ARCHITECTURE & SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ19 — Order Management & Trading Workbench  
**Mã nguồn:** [`libs/mock_trading_broker.py`](file:///d:/AlgoTrading/libs/mock_trading_broker.py)  
**Tệp lưu trữ trạng thái:** `data/mock_broker/mock_broker_state.json`  
**Chế độ:** `TRADING_MODE=DRY_RUN`  
**Tiêu chuẩn đối chiếu:** *Alpaca Markets Paper Trading Guide (Dec 2024)*  

---

## 1. Mục tiêu và Nguyên tắc Thiết kế

Động cơ **Mock Trading Broker** (`MockTradingBroker`) được xây dựng nhằm cung cấp môi trường khớp lệnh, quản lý tài khoản và hạch toán danh mục hoàn toàn khép kín. Động cơ này độc lập 100% với SDK Alpaca thật, đảm bảo:
1. **Tuyệt đối không phát sinh lệnh thật**: Không bao giờ thực hiện HTTP request mang tính ghi (`POST`, `PATCH`, `DELETE`) tới các endpoint giao dịch của Alpaca Paper hay Alpaca Live.
2. **Tuân thủ quy chuẩn Alpaca**: Tái hiện chính xác cấu trúc dữ liệu, các trường thuộc tính, quy tắc kiểm tra ràng buộc và vòng đời lệnh theo tài liệu *Alpaca Markets Paper Trading Guide*.
3. **Phân biệt nguồn gốc minh bạch**: Mọi đối tượng tài khoản, vị thế, lệnh và hoạt động đều được gắn cờ `is_mock=True` và `broker="SIMULATED_MOCK_BROKER"`.
4. **Bền vững trạng thái (Atomic Persistence)**: Trạng thái tài khoản và danh sách lệnh được đồng bộ hóa tức thời xuống tệp JSON trên đĩa, cho phép phục hồi nguyên vẹn sau khi khởi động lại backend.

---

## 2. Kiến trúc Mô hình Dữ liệu (State & Data Models)

```
+-----------------------------------------------------------------------------------+
|                                 MockTradingBroker                                 |
+-----------------------------------------------------------------------------------+
| - account: MockAccount                                                            |
| - orders: Dict[str, MockOrder]                                                    |
| - positions: Dict[str, MockPosition]                                              |
| - activities: List[MockActivity]                                                  |
| - client_order_ids: Dict[str, str]  (Idempotency Index)                           |
+-----------------------------------------------------------------------------------+
       |                    |                       |                    |
       v                    v                       v                    v
+--------------+   +-----------------+   +--------------------+   +-----------------+
| MockAccount  |   |    MockOrder    |   |    MockPosition    |   |  MockActivity   |
|--------------|   |-----------------|   |--------------------|   |-----------------|
| equity       |   | id              |   | symbol             |   | id              |
| cash         |   | client_order_id |   | qty                |   | order_id        |
| buying_power |   | symbol          |   | side (long/short)  |   | activity_type   |
| portfolio_val|   | side (buy/sell) |   | avg_entry_price    |   | transaction_time|
| day_pl       |   | type            |   | current_price      |   | details         |
| day_pl_pct   |   | status          |   | market_value       |   | is_mock=True    |
| is_mock=True |   | qty / notional  |   | unrealized_pl      |   | broker=SIMULATED|
| broker=SIMUL |   | limit_price     |   | unrealized_pl_pct  |   +-----------------+
+--------------+   | stop_price      |   | is_mock=True       |
                   | trail_price/%   |   | broker=SIMULATED   |
                   | filled_qty/avg  |   +--------------------+
                   | is_mock=True    |
                   | broker=SIMULATED|
                   +-----------------+
```

### 2.1. Baseline Tài khoản Khởi tạo
- **Equity**: `$100,000.00`
- **Cash**: `$100,000.00`
- **Buying Power**: `$400,000.00` (Chuẩn ký quỹ Reg-T 4x Day Trading)
- **Currency**: `USD`
- **Status**: `ACTIVE`

---

## 3. Quy tắc Kiểm tra Ràng buộc (Validation & Idempotency Rules)

Trước khi lệnh được tiếp nhận vào hệ thống, `MockTradingBroker` thực hiện chuỗi kiểm tra nghiêm ngặt:

1. **Loại trừ tương hỗ Số lượng & Giá trị (`qty` vs `notional`)**:
   - Nếu cả `qty` và `notional` đều được cung cấp $\rightarrow$ Báo lỗi `400 Bad Request` (`Cannot specify both qty and notional`).
   - Nếu cả hai đều rỗng hoặc $\le 0$ $\rightarrow$ Báo lỗi `400 Bad Request`.
2. **Kiểm tra Ràng buộc theo Loại Lệnh (Order-Specific Price Validation)**:
   - **Limit Order**: Bắt buộc phải có `limit_price > 0`.
   - **Stop Order**: Bắt buộc phải có `stop_price > 0`.
   - **Stop-Limit Order**: Bắt buộc phải có đồng thời cả `limit_price > 0` và `stop_price > 0`.
   - **Trailing Stop Order**: Bắt buộc phải có `trail_price > 0` hoặc `trail_percent > 0` (loại trừ tương hỗ lẫn nhau).
3. **Kiểm tra Tính Lũy thừa (Client Order ID Idempotency)**:
   - Nếu `client_order_id` đã tồn tại trong chỉ mục `client_order_ids` $\rightarrow$ Từ chối với lỗi `Idempotency violation: client_order_id already exists`. Ngăn chặn hoàn toàn hiện tượng tạo lệnh trùng lặp khi người dùng click đúp hoặc do lỗi mạng truyền lại.
4. **Kiểm tra Sức mua & Tiền mặt (Purchasing Power Check)**:
   - Lệnh Mua (`BUY`) yêu cầu giá trị ước tính không vượt quá `buying_power`.
   - Lệnh Bán (`SELL`) yêu cầu tài khoản phải có vị thế hợp lệ hoặc tuân thủ quy chế bán khống (short-selling).

---

## 4. Vòng đời Lệnh & Cỗ máy Trạng thái (Order Lifecycle State Machine)

```
                 +-----------------------+
                 |     ORDER_SUBMIT      |
                 +-----------------------+
                             |
                             v
                 +-----------------------+
                 |      pending_new      |
                 +-----------------------+
                             |
             +---------------+---------------+
             |                               |
             v                               v
    (Validation Pass)               (Validation Fail)
             |                               |
             v                               v
     +---------------+               +---------------+
     |   accepted    |               |   rejected    |
     +---------------+               +---------------+
             |
     +-------+-----------------------+-----------------------+
     |                               |                       |
     v                               v                       v
(Market / In-The-Money)       (User Request)          (User Request)
     |                               |                       |
     v                               v                       v
+---------------+             +---------------+       +---------------+
|    filled     |             |   canceled    |       |   replaced    |
+---------------+             +---------------+       +---------------+
                                                              |
                                                              v
                                                     (New Child Order Spawned)
```

### 4.1. Khớp Lệnh Giả lập (Fill Simulation Engine)
- Đối với lệnh **Market Order** hoặc lệnh **Limit Order** có mức giá chấp nhận ngay (Marketable), động cơ thực hiện khớp lệnh tức thì:
  - Giá khớp (`filled_avg_price`) được lấy từ sổ giá tham chiếu hiện hữu (hoặc mức giá quy định).
  - Trạng thái chuyển thành `filled`.
  - Cập nhật số lượng khớp (`filled_qty = qty`).
  - Thời điểm khớp (`filled_at`) được ghi nhận theo UTC ISO 8601.

### 4.2. Hạch toán Vị thế & Danh mục (Position & Portfolio Accounting)
- **Khi Mua (`BUY`)**:
  - Tiền mặt giảm: $\text{Cash} \leftarrow \text{Cash} - (\text{filled\_qty} \times \text{price})$.
  - Nếu mã chưa có trong danh mục: Tạo mới `MockPosition`.
  - Nếu mã đã có trong danh mục: Gia tăng số lượng và tính lại giá vốn bình quân gia quyền:
    $$\text{avg\_entry\_price} = \frac{(\text{old\_qty} \times \text{old\_entry}) + (\text{new\_qty} \times \text{new\_price})}{\text{old\_qty} + \text{new\_qty}}$$
- **Khi Bán (`SELL`)**:
  - Giảm số lượng vị thế.
  - Hoàn trả tiền mặt kèm theo khoản lãi/lỗ đã hiện thực hóa (Realized P&L).
  - Nếu số lượng vị thế về 0: Loại bỏ vị thế khỏi danh mục.
- **Tính toán Lãi/Lỗ & Giá trị Tài sản ròng**:
  - $\text{Portfolio Value} = \sum (\text{qty}_i \times \text{current\_price}_i)$
  - $\text{Equity} = \text{Cash} + \text{Portfolio Value}$
  - $\text{Unrealized P\&L} = (\text{current\_price} - \text{avg\_entry\_price}) \times \text{qty}$

### 4.3. Quy trình Sửa Lệnh (Order Replacement)
- Tuân thủ phương thức `replace_order_by_id` của Alpaca:
  1. Kiểm tra lệnh gốc có đang ở trạng thái có thể sửa (`new`, `accepted`, `pending_new`).
  2. Đánh dấu lệnh cũ là `replaced`.
  3. Khởi tạo một lệnh mới kế nhiệm mang các thông số đã cập nhật (`limit_price`, `stop_price`, `qty`).
  4. Gán liên kết `replaces_order_id` trên lệnh mới trỏ về lệnh cũ.
  5. Ghi nhận 2 bản ghi kiểm toán: `ORDER_REPLACED` (cho lệnh cũ) và `ORDER_SUBMITTED` (cho lệnh mới).

### 4.4. Quy trình Hủy Lệnh Đơn lẻ và Hàng loạt (Cancellation & Bulk Cancel)
- **Cancel One Order**: Kiểm tra trạng thái lệnh, chuyển đổi sang `canceled`, giải phóng sức mua đã khóa, ghi nhật ký `ORDER_CANCELED`.
- **Bulk Cancel All Orders**: Quét toàn bộ danh mục lệnh, lọc các lệnh đang mở và đồng loạt hủy bỏ, trả về danh sách các mã lệnh đã hủy thành công.

---

## 5. Nhật ký Kiểm toán Bất biến (Immutable Activity Audit Log)

Mọi biến động trạng thái đều tạo ra một đối tượng `MockActivity` độc lập, lưu giữ:
- `id`: Định danh duy nhất UUID v4.
- `order_id`: Mã lệnh liên kết.
- `activity_type`: Phân loại hoạt động (`ORDER_SUBMITTED`, `ORDER_FILLED`, `ORDER_CANCELED`, `ORDER_REPLACED`, `ORDER_REJECTED`, `BULK_CANCEL`).
- `transaction_time`: Dấu thời gian UTC chuẩn ISO 8601 chính xác tới micro-giây.
- `details`: Từ điển chứa toàn bộ thuộc tính thay đổi (giá khớp, số lượng, chênh lệch tiền mặt).
- `is_mock=True`, `broker="SIMULATED_MOCK_BROKER"`.

---

## 6. Kết luận

Động cơ `MockTradingBroker` giải quyết triệt để nhu cầu thử nghiệm toàn diện quy trình giao dịch theo tài liệu *Alpaca Markets Paper Trading Guide* mà không cần cấp quyền ghi trên tài khoản thực hay tài khoản paper thật, đảm bảo cách ly tuyệt đối và duy trì an toàn 100% cho hệ thống.


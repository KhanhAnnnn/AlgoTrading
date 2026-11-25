# GĐ19 — TÀI LIỆU THIẾT KẾ & VẬN HÀNH ORDER MANAGEMENT & TRADING WORKBENCH
## ORDER MANAGEMENT & TRADING WORKBENCH SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ19 — Order Management & Trading Workbench  
**Trạng thái hệ thống:** `TRADING_MODE=DRY_RUN`  
**Soak Session (GĐ18):** `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` (Không gián đoạn)  
**Tài liệu tham chiếu:** *Alpaca Markets Paper Trading Guide (Dec 2024)*  
**Mục tiêu:** Xây dựng giao diện web toàn diện cho phép quản trị tài khoản, danh mục vị thế, theo dõi vòng đời lệnh và mô phỏng giao dịch theo chuẩn Alpaca Paper Trading trong môi trường giả lập an toàn tuyệt đối.

---

## 1. Tổng quan Kiến trúc Giao diện (Workbench Architecture)

Giao diện **Trading Workbench** được tích hợp trực tiếp vào ứng dụng web `trading-dashboard`, đóng vai trò là trạm điều khiển trung tâm (cockpit) dành cho giao dịch viên và kỹ sư thuật toán. Toàn bộ các thao tác phát lệnh, sửa lệnh, hủy lệnh và khớp lệnh đều được vận hành thông qua **Mock Broker Engine** độc lập, ngăn chặn hoàn toàn việc gửi request ghi đến Alpaca API trong khi vẫn duy trì trải nghiệm người dùng tương thích 100% với tài liệu *Alpaca Markets Paper Trading Guide*.

```
+-----------------------------------------------------------------------------------------+
|                                    TRADING DASHBOARD                                    |
|  [System Status] [Pipeline] [Flink Streaming] [Alpaca Paper] [Trading Workbench (NEW)]  |
+-----------------------------------------------------------------------------------------+
                                             |
                   +-------------------------+-------------------------+
                   |                                                   |
                   v                                                   v
      [Read-Only Telemetry View]                           [Simulation Workbench]
       - Alpaca Paper Account ($100k)                       - Simulated Account Overview ($100k)
       - Historical Positions (2 orders)                    - Interactive Order Ticket
       - Historical Orders Audit Trail                      - Open Orders (Replace / Cancel / Bulk)
       - Strict Read-Only (/api/paper/*)                    - Order History & P&L Realization
                                                            - Real-time Positions Tracking
                                                            - Order Activity Audit Trail
                                                            - Isolated Backend (/api/workbench/*)
```

---

## 2. Chi tiết các Phân hệ Giao diện (Workbench Sub-Panels)

### 2.1. Account Overview Bar (Tổng quan Tài khoản Mô phỏng)
Thanh chỉ số tài khoản mô phỏng hiển thị liên tục ở đầu trang với các thông số tài chính chuẩn Alpaca:
- **Simulated Equity**: Tổng giá trị tài sản ròng = Tiền mặt (`Cash`) + Tổng giá trị thị trường của các vị thế đang nắm giữ (`Portfolio Market Value`). Mặc định khởi tạo: `$100,000.00`.
- **Cash Balance**: Lượng tiền mặt khả dụng để giải ngân hoặc rút. Được cập nhật tức thì khi lệnh Mua (trừ tiền) hoặc lệnh Bán (cộng tiền) được khớp.
- **Buying Power**: Sức mua khả dụng theo chuẩn ký quỹ Reg-T (4x đối với Day Trading, 2x đối với Overnight).
- **Portfolio Value**: Tổng giá trị vốn hóa của các mã chứng khoán/crypto đang mở trong danh mục.
- **Day Profit/Loss**: Lãi/lỗ tích lũy trong ngày tính bằng USD và tỷ lệ phần trăm (%).
- **Trạng thái & Huy hiệu An toàn**: Hiển thị nhãn `[SIMULATED BROKER]` màu tím nổi bật và `[DRY_RUN ENFORCED]` màu lục, khẳng định không phát sinh rủi ro tài chính thật.

### 2.2. Order Ticket (Phiếu Đặt Lệnh Tương tác)
Hỗ trợ đầy đủ các loại lệnh và phương thức định lượng theo hướng dẫn *Alpaca Paper Trading Guide*:
- **Mã tài sản (Symbol)**: Hỗ trợ mã chứng khoán Mỹ (e.g. `AAPL`, `MSFT`, `TSLA`, `NVDA`) và tiền mã hóa (e.g. `BTC/USD`, `ETH/USD`). Tự động chuẩn hóa chữ hoa.
- **Chiều giao dịch (Side)**: `BUY` (Mua) hoặc `SELL` (Bán) với màu sắc trực quan (Xanh ngọc / Đỏ cam).
- **Loại định lượng (Quantity Mode)**:
  - *Shares / Units (`qty`)*: Hỗ trợ cả số nguyên lẫn số thập phân (**Fractional shares** lên tới 9 chữ số thập phân, e.g. `0.054 BTC`).
  - *Dollar Amount (`notional`)*: Đặt lệnh theo giá trị tiền mặt (e.g. `$500.00` cổ phiếu NVDA). Hệ thống tự động quy đổi số lượng dựa trên thị giá.
  - *Quy tắc loại trừ tương hỗ (Mutual Exclusivity)*: Giao diện và API nghiêm cấm chỉ định đồng thời cả `qty` và `notional`.
- **Loại lệnh (Order Type)**:
  1. **Market Order**: Khớp ngay tại mức giá thị trường hiện hữu.
  2. **Limit Order**: Yêu cầu nhập mức giá trần khi mua hoặc giá sàn khi bán (`limit_price`).
  3. **Stop Order**: Kích hoạt lệnh thị trường khi giá chạm ngưỡng `stop_price`.
  4. **Stop-Limit Order**: Yêu cầu cả `stop_price` (ngưỡng kích hoạt) và `limit_price` (giá giới hạn thực thi).
  5. **Trailing Stop Order**: Hỗ trợ bám đuổi biến động giá qua `trail_price` (chênh lệch tuyệt đối USD) hoặc `trail_percent` (tỷ lệ phần trăm).
- **Hiệu lực lệnh (Time In Force - TIF)**:
  - `DAY`: Hiệu lực trong phiên giao dịch.
  - `GTC` (Good 'Til Canceled): Hiệu lực đến khi được hủy.
  - `IOC` (Immediate Or Cancel): Khớp ngay lập tức phần có thể, hủy phần còn lại.
  - `FOK` (Fill Or Kill): Khớp toàn bộ ngay lập tức hoặc hủy bỏ hoàn toàn.
- **Client Order ID**: Cho phép người dùng nhập mã định danh tùy biến hoặc tự động sinh UUID v4 nhằm bảo đảm tính lũy thừa (**Idempotency**).
- **Xác thực trực tiếp (Client-Side Validation)**: Kiểm tra tính hợp lệ trước khi gửi, hiển thị thông báo lỗi chi tiết nếu vi phạm quy tắc định dạng.

### 2.3. Open Orders Panel (Quản lý Lệnh Đang Mở)
- Danh sách bảng hiển thị toàn bộ các lệnh đang ở trạng thái chờ khớp (`new`, `accepted`, `pending_new`, `partially_filled`).
- Cung cấp tính năng lọc đa chiều:
  - Lọc theo mã tài sản (`Symbol`).
  - Lọc theo chiều (`BUY` / `SELL`).
  - Lọc theo trạng thái (`Status`).
- **Thao tác hành động (Actions)**:
  - **Replace Order**: Mở cửa sổ điều chỉnh `limit_price`, `stop_price` hoặc số lượng `qty` của lệnh mà không làm mất thứ tự ưu tiên hàng đợi.
  - **Cancel Order**: Hủy tức thời một lệnh được chọn.
  - **Cancel All Orders**: Hủy hàng loạt tất cả các lệnh đang mở chỉ với 1 cú click (Bulk Cancel).

### 2.4. Order History Panel (Lịch sử Lệnh Đã Đóng)
- Lưu trữ toàn bộ các lệnh đã kết thúc vòng đời: `filled` (đã khớp), `canceled` (đã hủy), `expired` (hết hạn), `replaced` (đã thay thế), `rejected` (bị từ chối).
- Hiển thị chi tiết mức giá khớp trung bình (`filled_avg_price`), số lượng đã khớp (`filled_qty`), và thời điểm khớp chính xác tính theo mili-giây UTC.
- Hỗ trợ xem liên kết phụ hệ: Khi một lệnh bị thay thế (`replaced`), bảng hiển thị mã lệnh mới kế nhiệm (`replaces_order_id`).

### 2.5. Positions Panel (Danh mục Vị thế Mở)
- Hiển thị danh sách các tài sản đang thực sự nắm giữ trong tài khoản mô phỏng:
  - Mã tài sản (`Symbol`).
  - Chiều vị thế (`Side`: Long / Short).
  - Số lượng nắm giữ (`Qty`).
  - Giá vốn bình quân (`Average Entry Price`).
  - Giá thị trường hiện tại (`Current Price`).
  - Tổng giá trị thị trường (`Market Value`).
  - Lãi/Lỗ chưa thực hiện (`Unrealized P&L` USD và `%`).
- Trực quan hóa biến động P&L với màu xanh (lãi) và đỏ (lỗ).

### 2.6. Order Details Modal (Cửa sổ Chi tiết Lệnh)
- Cho phép nhấp vào bất kỳ mã lệnh nào để mở modal thông tin chi tiết chuyên sâu:
  - UUID hệ thống và `client_order_id`.
  - Thông số kỹ thuật đầy đủ: Class lệnh, Side, Type, TIF, Qty, Notional, Limit/Stop prices.
  - Thống kê khớp: Executed Shares, Remaining Shares, Average Fill Price.
  - **Dòng thời gian vòng đời (Lifecycle Audit Timeline)**: Liệt kê trình tự các sự kiện từ lúc gửi (`SUBMITTED`), chuyển tiếp (`ACCEPTED`), khớp lệnh (`FILLED`), sửa đổi (`REPLACED`) đến hủy (`CANCELED`).

### 2.7. Order Activity Log Panel (Nhật ký Hoạt động Kiểm toán)
- Bảng nhật ký kiểm toán bất biến (Immutable Audit Trail) ghi lại mọi thao tác phát sinh:
  - Thời điểm UTC ISO 8601.
  - Loại hoạt động (`ORDER_SUBMITTED`, `ORDER_FILLED`, `ORDER_CANCELED`, `ORDER_REPLACED`, `ORDER_REJECTED`, `BULK_CANCEL`).
  - Chi tiết mã lệnh và mã tài sản liên quan.
  - Mô tả nguyên nhân (e.g. `Market order filled at 150.25`, `Order canceled by user request`).

---

## 3. Trạng thái Trải nghiệm Người dùng (UX States)

1. **Loading State**: Hiển thị biểu tượng tải dữ liệu mượt mà khi hệ thống đang truy vấn REST API backend.
2. **Empty State**: Khi danh sách rỗng (chưa có vị thế hoặc chưa có lệnh mở), giao diện hiển thị hình minh họa tinh gọn kèm hướng dẫn "Chưa có dữ liệu. Hãy sử dụng Order Ticket để tạo lệnh mô phỏng mới."
3. **Error State**: Nếu có lỗi mạng hoặc backend không phản hồi, hiển thị thông báo lỗi rõ ràng kèm nút "Thử lại" (Retry).
4. **Auto-refresh Cadence**: Giao diện tự động làm mới số liệu mỗi 5 giây, đồng thời cung cấp nút "Làm mới" thủ công để cập nhật tức thì.
5. **Dữ liệu thật không bị che lấp**: Tuyệt đối không sinh dữ liệu giả mạo trong các panel Alpaca Paper thật (`/api/paper/*`) nhằm che giấu lỗi API. Panel thật phản ánh đúng 2 lệnh lịch sử ban đầu từ tài liệu.

---

## 4. Kết luận

Phân hệ **Order Management & Trading Workbench** hoàn thiện toàn diện năng lực tương tác giao dịch mô phỏng của hệ thống AlgoTrading, đáp ứng 100% các tiêu chuẩn trong *Alpaca Markets Paper Trading Guide* mà không xâm phạm hay gây nhiễu đến tiến trình kiểm thử ngâm GĐ18 đang diễn ra.


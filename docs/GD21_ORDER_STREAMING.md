# GĐ21.2 — KIẾN TRÚC & XỬ LÝ SỰ KIỆN TRADINGSTREAM
## ALPACA TRADINGSTREAM EVENT INGESTION & RECONCILIATION SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ21 — Alpaca Paper Trading Integration (GĐ21.2)  
**Chế độ:** `TRADING_MODE=DRY_RUN`  
**Bộ xử lý sự kiện:** [`libs/alpaca_order_stream_processor.py`](file:///d:/AlgoTrading/libs/alpaca_order_stream_processor.py)  
**Giao thức tham chiếu:** Alpaca WebSocket TradingStream API (`wss://paper-api.alpaca.markets/v2/stream`)  

---

## 1. Khảo sát Giao thức Alpaca TradingStream (Protocol Survey)

Alpaca cung cấp kênh truyền WebSocket chuyên biệt mang tên **TradingStream** nhằm cập nhật trạng thái lệnh tức thời mà không cần liên tục thăm dò (polling) REST API:

### 1.1. Luồng Bắt tay & Đăng ký Kênh (Handshake & Subscription)
1. **Kết nối:** `wss://paper-api.alpaca.markets/v2/stream`
2. **Xác thực (Authentication):**
   ```json
   {
     "action": "auth",
     "key": "<ALPACA_KEY_ID>",
     "secret": "<ALPACA_SECRET_KEY>"
   }
   ```
3. **Đăng ký nhận cập nhật lệnh (Listen `trade_updates`):**
   ```json
   {
     "action": "listen",
     "data": {
       "streams": ["trade_updates"]
     }
   }
   ```

### 1.2. Phân loại Sự kiện Lệnh (`trade_updates` Events)
Khi lệnh thay đổi trạng thái, Alpaca phát thông điệp mang cấu trúc:
- `event`: Tên sự kiện (`new`, `fill`, `partially_filled`, `canceled`, `expired`, `replaced`, `rejected`, `stopped`, `pending_cancel`).
- `timestamp`: Dấu thời gian phát sinh sự kiện ISO 8601 UTC.
- `order`: Toàn bộ thuộc tính của lệnh tại thời điểm đó.

---

## 2. Thách thức Kỹ thuật và Giải pháp Cốt lõi (Resilience Architecture)

Trong môi trường mạng phân tán thời gian thực, luồng sự kiện streaming thường đối mặt với 4 thách thức lớn được xử lý triệt để bởi `AlpacaOrderStreamProcessor`:

```
+---------------------------------------------------------------------------------------------------+
|                         CỖ MÁY XỬ LÝ SỰ KIỆN TRADINGSTREAM RESILIENT ENGINE                       |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [Incoming WebSocket Stream]                                                                      |
|             |                                                                                     |
|             v                                                                                     |
|  [1. Deduplication Filter]        --> Kiểm tra khóa duy nhất `event:order_id:timestamp`           |
|             |                                                                                     |
|             v                                                                                     |
|  [2. Monotonic State Precedence]  --> Ngăn chặn sự kiện đến muộn đè bẹp trạng thái hoàn tất       |
|             |                                                                                     |
|             v                                                                                     |
|  [3. Unknown Event Isolation]     --> Cách ly sự kiện lạ, không làm sập tiến trình                |
|             |                                                                                     |
|             v                                                                                     |
|  [4. Authoritative REST Reconcile]--> Tự động vá dữ liệu thiếu sau khi reconnect                 |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 2.1. Lọc Sự kiện Trùng lặp (Deduplication - TC-G21-09)
- **Vấn đề:** Do cơ chế gửi lại gói tin (TCP retransmission) hoặc chuyển vùng kết nối, client có thể nhận cùng 1 sự kiện `fill` nhiều lần.
- **Giải pháp:** Hệ thống tạo khóa định danh duy nhất:
  $$\text{event\_key} = \text{event\_type} + \text{":"} + \text{order\_id} + \text{":"} + \text{timestamp}$$
- Nếu `event_key` đã xuất hiện trong `seen_event_keys`, sự kiện lập tức bị loại bỏ (`DROPPED_DUPLICATE`) và tăng chỉ số đếm, bảo đảm vị thế không bị tính trùng lặp.

### 2.2. Xử lý Sự kiện Đến Muộn hoặc Sai Thứ tự (Out-of-Order Precedence - TC-G21-10)
- **Vấn đề:** Sự kiện `new` (khởi tạo) có thể bị nghẽn mạng và đến *sau* sự kiện `fill` (khớp lệnh). Nếu ghi đè ngây thơ, lệnh sẽ bị chuyển ngược từ `filled` về `new`!
- **Giải pháp:** Thiết lập **Hệ thống Cấp bậc Trạng thái Đơn điệu (Monotonic State Hierarchy)**:

$$\text{pending\_new (Cấp 1)} \longrightarrow \text{new / accepted (Cấp 2)} \longrightarrow \text{partially\_filled (Cấp 3)} \longrightarrow \text{filled / canceled / replaced / rejected (Cấp 4)}$$

- **Quy tắc Bất biến:** Một sự kiện có cấp bậc thấp hơn **tuyệt đối không được phép ghi đè** lên trạng thái có cấp bậc cao hơn hiện hữu. Nếu phát hiện vi phạm, hệ thống ghi nhận `HANDLED_OUT_OF_ORDER`, bảo toàn nguyên vẹn trạng thái `filled`.

### 2.3. Cách ly Sự kiện Không xác định (Unknown Events - TC-G21-11)
- Khi Alpaca bổ sung các loại sự kiện nội bộ mới (`custom_event_xyz`), bộ xử lý không làm gián đoạn hệ thống (`no crash/no 500`), mà đóng gói vào bản ghi `UNKNOWN_EVENT` kèm snapshot để kiểm toán.

### 2.4. Mất Kết nối & Tự Động Tái Lập (Disconnect & Reconnect - TC-G21-12)
- Khi đường truyền bị ngắt, trạng thái chuyển sang `DISCONNECTED`.
- Sau khi tái lập kết nối thành công (`reconnected`), hệ thống tự động tăng biến đếm `reconnect_count` và chuyển sang bước đối soát.

---

## 3. Cơ chế Đối soát Tự Động với REST (Authoritative REST Reconciliation - TC-G21-13)

Sau mỗi lần tái lập kết nối hoặc theo định kỳ, hệ thống gọi phương thức:
`stream_processor.reconcile_with_rest(rest_orders)`

```
[In-Memory Stream Cache] <==================> [Authoritative Alpaca REST API]
       (Cache)                                           (Ground Truth)
          |                                                    |
          +------------------ SO SÁNH ĐỐI CHIẾU ---------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
(Thiếu lệnh trong Cache)                         (Lệch trạng thái)
             |                                               |
             v                                               v
    [Thêm lệnh mới vào Cache]                       [Cập nhật trạng thái theo REST]
    (MISSED_IN_STREAM)                              (STATUS_MISMATCH)
```

### Bằng chứng Kiểm thử Thực tế:
- Kiểm thử đã đưa vào 2 lệnh thật từ Alpaca Paper (`25f85bed...` và `c5d4311a...`).
- Kết quả đối soát:
  - `rest_orders_examined`: 2
  - `synced_count`: 2
  - `status`: **`"RECONCILED"`**
  - Đồng bộ 100% dữ liệu vào bộ nhớ đệm.

---

## 4. Endpoints Giám sát Trạng thái Luồng

Backend cung cấp 2 endpoint chuyên dụng phục vụ việc theo dõi sức khỏe kết nối:
1. **`GET /api/paper/stream/status`:**
   - Trả về `connection_status: "CONNECTED"`, `reconnect_count: 0`, số sự kiện đã xử lý và số sự kiện bị loại bỏ do trùng lặp.
2. **`GET /api/paper/sync/reconcile`:**
   - Kích hoạt quy trình đối soát trực tiếp giữa TradingStream cache và Alpaca Paper REST API.

---

## 5. Kết luận GĐ21.2

Cỗ máy xử lý sự kiện `AlpacaOrderStreamProcessor` thiết lập nền tảng hoàn chỉnh, an toàn và chống chịu lỗi cao cho việc tiếp nhận cập nhật lệnh thời gian thực, sẵn sàng cho việc tích hợp WebSocket chính thức trong các giai đoạn tương lai.


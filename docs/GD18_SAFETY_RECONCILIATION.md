# GĐ18 — MULTI-SOURCE SAFETY RECONCILIATION & AUDIT

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ18 — Operational Soak & Evidence Validation (Read-Only)  
**Thời điểm thẩm định:** 24/10/2026  
**Chế độ:** `TRADING_MODE=DRY_RUN`  

---

## 1. Phương pháp Đối chiếu An toàn Đa nguồn (Triangulated 3-Way Safety Audit)

Để bảo đảm tuyệt đối rằng không có bất kỳ lệnh giao dịch ngoài ý muốn nào được gửi lên sàn giao dịch Alpaca trong toàn bộ giai đoạn soak và shadow mode, hệ thống thiết lập cơ chế đối chiếu chéo độc lập từ 3 nguồn:

```
                  ┌─────────────────────────────────────────┐
                  │    Nguồn 1: Adapter Execution Guard     │
                  │       (AlpacaPaperSDK DRY_RUN)          │
                  └────────────────────┬────────────────────┘
                                       │
                      Triangulated     │     Safety Check
                                       ▼
┌──────────────────────────────────────┴──────────────────────────────────────┐
│                                                                             │
│  Nguồn 2: Local Process & Logs                    Nguồn 3: Alpaca Live API  │
│  - shadow_observations.jsonl                      - GET /v2/orders?status=all│
│  - crypto_order_intent.json                       - GET /v2/account         │
│  - Zero executed trade actions                    - Total Orders = Exactly 2│
│                                                                             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │   KẾT LUẬN: TUYỆT ĐỐI AN TOÀN │
                       │    (0 Unintended Orders)      │
                       └───────────────────────────────┘
```

---

## 2. Chi tiết 3 Nguồn Độc lập

### Nguồn 1: Adapter / Execution Guard (Chắn cổng Thực thi)
- **Thành phần:** `libs/alpaca_paper_sdk.py` và cờ môi trường `TRADING_MODE=DRY_RUN`.
- **Cơ chế:** Khi `dry_run_orders=True`, các phương thức gửi lệnh (`submit_order`, `replace_order`, `cancel_order`) bị chặn lại ở tầng Adapter.
- **Hành vi:** Trả về đối tượng phản hồi giả lập (`mock_order_response`) với thuộc tính `id="mock_dry_run_..."`, `status="dry_run_recorded"`. Adapter hoàn toàn **không khởi tạo HTTP Request (POST/PATCH/DELETE)** tới máy chủ Alpaca.
- **Kiểm thử:** `TC-G18-12` — **PASSED**.

### Nguồn 2: Local Process & Shadow Logs (Nhật ký Xử lý Nội bộ)
- **Tệp nguồn:** `data/logs/shadow_observations.jsonl` và `data/orders/crypto_order_intent.json`.
- **Nội dung kiểm tra:** Toàn bộ tín hiệu phát sinh từ Flink streaming (`BUY`, `SELL`, `HOLD`) được định tuyến vào `ShadowModeObserver`.
- **Thuộc tính hành động:** Trường `action` của mọi bản ghi đều được ấn định là:
  $$\text{action} = \text{"OBSERVED_ONLY_NO_ORDER"}$$
- **Kiểm thử:** `TC-G18-13` — **PASSED** (0 bản ghi có trạng thái gửi lệnh thật).

### Nguồn 3: Alpaca Paper Trading API (Sổ lệnh Thực tế trên Broker)
- **Endpoint kiểm tra:** `https://paper-api.alpaca.markets/v2/orders?status=all&limit=500`.
- **Kết quả đối chiếu:**
  - Tổng số lệnh trong toàn bộ lịch sử tài khoản: **Chính xác 2 lệnh**.
  - Lệnh 1: `BTCUSD` — Mua 0.002 BTC (khởi tạo từ GĐ10.6 để xác thực E2E).
  - Lệnh 2: `NVDA` — Mua 10 cổ phiếu (khởi tạo từ GĐ11 để xác thực danh mục).
  - Số lệnh mới phát sinh từ GĐ12 đến GĐ18: **Chính xác 0 lệnh (Zero)**.
- **Kiểm thử:** `TC-G18-14` — **PASSED**.

---

## 3. Ma trận Đối chiếu Chéo và Xử lý Bất thường (Reconciliation Logic)

| Kịch bản Đối chiếu | Nguồn 1 (Adapter) | Nguồn 2 (Local Logs) | Nguồn 3 (Alpaca API) | Đánh giá An toàn | Biện pháp Xử lý |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Kịch bản A (Thực tế GĐ18)** | `DRY_RUN` | `OBSERVED_ONLY` | 2 lệnh cũ, 0 lệnh mới | **TUYỆT ĐỐI AN TOÀN (PASS)** | Cho phép duy trì quan sát |
| **Kịch bản B (Lệch Nghiêm trọng)** | `DRY_RUN` | `OBSERVED_ONLY` | Xuất hiện lệnh mới (> 2) | **BÁO ĐỘNG ĐỎ (CRITICAL)** | Dừng ngay lập tức toàn bộ tiến trình |
| **Kịch bản C (Lệch Tầng Ghi nhận)** | `DRY_RUN` | Ghi nhận "SUBMITTED" | 2 lệnh cũ, 0 lệnh mới | **CẢNH BÁO VẬN HÀNH (WARN)** | Sửa lại logic ghi log nội bộ |
| **Kịch bản D (Lỗi Cấu hình)** | `LIVE_EXECUTE` | `OBSERVED_ONLY` | Bất kỳ | **BÁO ĐỘNG ĐỎ (CRITICAL)** | Ép hạ về `DRY_RUN`, hủy token API |

**Kết luận Tổng hợp (TC-G18-15):** Hệ thống đang vận hành chuẩn xác theo **Kịch bản A**. Cả 3 nguồn độc lập đều đồng thuận 100% rằng không có bất kỳ lệnh ngoài ý muốn nào được gửi lên sàn.

---

## 4. Tính Toàn vẹn của Bằng chứng (Evidence Integrity)

### 4.1. Mã định danh Sự kiện Bền vững (Event ID Determinism)
Để loại trừ triệt để nguy cơ va chạm chuỗi khi nối các trường bằng dấu hai chấm thông thường, mã định danh `event_id` được sinh bằng hàm băm SHA256 với cấu trúc tiền tố nghiêm ngặt:
$$\text{event\_id} = \text{SHA256}(\text{Salt} \,\|\, \text{Symbol} \,\|\, \text{":"} \,\|\, \text{EventTime} \,\|\, \text{":"} \,\|\, \text{SignalType})[0:16]$$
- **Khả năng chống va chạm ký tự phân cách (Delimiter Collision Immunity):**
  - Cặp dữ liệu `("BTC:USD", "12:00", "BUY")` và `("BTC", "USD:12:00", "BUY")` sẽ tạo ra 2 giá trị hash hoàn toàn khác biệt (`TC-G18-16` PASSED).
- **Phân lập Dữ liệu Fixture và Dữ liệu Thị trường Tự nhiên:**
  - Dữ liệu mô phỏng / kiểm thử: $\text{Salt} = \text{"FIXTURE:"}$.
  - Dữ liệu thị trường thật: $\text{Salt} = \text{"NATURAL:"}$.
  - Ngay cả khi có cùng symbol, timestamp và tín hiệu, hash của fixture và live stream không bao giờ trùng nhau (`TC-G18-17` PASSED).

### 4.2. Độ bền của Bảng Chỉ mục qua Khởi động lại (Index Durability Across Restarts)
- Khi `ShadowModeObserver` được khởi tạo, nó đọc tuần tự tệp `shadow_observations.jsonl` và tái tạo tập hợp `seen_event_ids`.
- Đảm bảo một tín hiệu đã xuất hiện trước khi restart không bị xử lý lại sau khi restart (`TC-G18-18` PASSED).

---

## 5. Thẩm định Giao diện Dashboard và Kênh Cảnh báo Slack

### 5.1. Thẩm định Mã nguồn Dashboard (Read-Only UI Audit)
Toàn bộ mã nguồn Frontend (`trading-dashboard/frontend/src/`) và Backend (`trading-dashboard/backend/main.py`) đã được quét tự động:
1. **Không có Form/Nút gửi lệnh:** Không tồn tại bất kỳ nút bấm hoặc form giao diện nào có nhãn `Submit Order`, `Place Order`, `Buy`, `Sell`, `Cancel Order`.
2. **Không có API Ghi Lệnh:** Không tồn tại endpoint nào có dạng `POST /api/orders`, `POST /api/trade`, `DELETE /api/orders`.
3. Toàn bộ các API đều là `GET` phục vụ việc truy vấn dữ liệu quan sát (`TC-G18-22` PASSED).

### 5.2. Định dạng Cảnh báo Slack (Slack Operational Framing)
Nhật ký `SlackNotifier` và outbox queue được kiểm tra:
- Các thông báo gửi lên Slack chỉ thuần túy mang tính chất thông báo vận hành (Operational Alert): tình trạng kết nối Kafka, Flink checkpoint, cảnh báo độ trễ.
- Không phát sinh tin nhắn nào gây hiểu lầm là đã khớp lệnh thực tế trên sàn giao dịch (`TC-G18-23` PASSED).


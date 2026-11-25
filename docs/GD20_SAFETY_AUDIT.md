# GĐ20 — BÁO CÁO KIỂM TOÁN AN TOÀN & RANH GIỚI HỆ THỐNG
## SYSTEM SAFETY AUDIT & BOUNDARY ISOLATION SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ20 — End-to-End Integration & Market Data Integrity  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Trạng thái phiên Soak GĐ18:** `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` (Không gián đoạn)  
**Bộ kiểm thử an toàn:** [`tests/test_gd20_e2e_integration.py`](file:///d:/AlgoTrading/tests/test_gd20_e2e_integration.py) (Các test từ TC-G20-19 đến TC-G20-26)  

---

## 1. Tôn chỉ An toàn Bất biến (Core Safety Mandates)

Quá trình tích hợp đầu cuối GĐ20 được thực hiện dưới sự kiểm soát của 5 nguyên tắc an toàn nghiêm ngặt:

1. **Khóa Cứng Chế độ `DRY_RUN`:** Biến môi trường `TRADING_MODE=DRY_RUN` được thiết lập bất biến trong tệp cấu hình `.env`, cấu hình Docker Compose và các tiến trình thực thi.
2. **Không Phát sinh Lệnh Thật:** Cấm tuyệt đối việc gọi các phương thức mang tính ghi (`submit_order`, `replace_order`, `cancel_order`) tới Alpaca Paper hoặc Live.
3. **Chặn Đứng Endpoint Giao dịch Phía Máy chủ:** Toàn bộ các route đặt lệnh truyền thống bị đánh chặn chủ động ở tầng API Gateway và trả về mã lỗi HTTP `403 Forbidden`.
4. **Cách ly Dữ liệu Giả lập Khỏi Dữ liệu Thị trường:** Mọi tác vụ trên Mock Broker chỉ được ghi vào kho dữ liệu mô phỏng, tuyệt đối không bơm thông điệp vào các topic Kafka thị trường tự nhiên.
5. **Bảo tồn Tuyệt đối Phiên Ngâm GĐ18:** Không khởi động lại các container Flink, Redpanda và các producer đang đo đạc thời gian ngâm 168 giờ.

---

## 2. Kiểm toán Rào chắn Máy chủ (Server-Side Safety Interceptors - TC-G20-20)

Tại tầng API Gateway (`trading-dashboard/backend/main.py`), các endpoint có nguy cơ bị khai thác để đặt lệnh thật đều được thiết lập cơ chế đánh chặn chủ động:

```python
@app.post("/api/orders")
async def intercept_legacy_orders():
    raise HTTPException(
        status_code=403,
        detail="CRITICAL SAFETY GUARD: Live and unsimulated order placement is strictly prohibited. "
               "TRADING_MODE is locked to DRY_RUN. For simulated orders, use /api/workbench/orders."
    )

@app.post("/api/trade")
async def intercept_trade():
    raise HTTPException(
        status_code=403,
        detail="CRITICAL SAFETY GUARD: Live trade execution is strictly prohibited. TRADING_MODE is DRY_RUN."
    )

@app.post("/api/v2/orders")
async def intercept_v2_orders():
    raise HTTPException(
        status_code=403,
        detail="CRITICAL SAFETY GUARD: Direct Alpaca write endpoints are blocked by safety guardrails."
    )
```

### Kết quả Kiểm thử Tự động:
- Gửi yêu cầu `POST` tới `/api/orders` $\rightarrow$ Trả về chính xác **`403 Forbidden`**.
- Gửi yêu cầu `POST` tới `/api/trade` $\rightarrow$ Trả về chính xác **`403 Forbidden`**.
- Gửi yêu cầu `POST` tới `/api/v2/orders` $\rightarrow$ Trả về chính xác **`403 Forbidden`**.
- Payload thông báo lỗi nêu rõ nguyên nhân bị chặn bởi `CRITICAL SAFETY GUARD`.

---

## 3. Kiểm toán Rò rỉ Thông tin Xác thực (Credential Security - TC-G20-21)

Đã thực hiện kiểm toán tĩnh (Static Analysis) và kiểm toán động (Runtime Inspection) trên toàn bộ hệ thống:
1. **Kiểm tra Frontend Bundle (`dist/`):**
   - Quét gói biên dịch `npm run build`: Không chứa các chuỗi khóa bí mật như `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY` hoặc token cá nhân.
2. **Kiểm tra API Responses:**
   - Phân tích phản hồi từ `/api/workbench/account`, `/api/workbench/orders`, `/api/paper/account`: Tuyệt đối không để lộ secret key hoặc chuỗi xác thực.
3. **Kiểm tra Nhật ký Backend:**
   - Không có thông tin nhạy cảm được in ra console hoặc ghi vào tệp log.

---

## 4. Tách biệt Tuyệt đối Giữa Giả lập và Tài khoản Thật (TC-G20-22, TC-G20-23)

Hệ thống duy trì ranh giới vật lý và logic độc lập giữa 2 không gian:

```
+---------------------------------------------------------------------------------------------------+
|                                      BẢN ĐỒ CÁCH LY HỆ THỐNG GĐ20                                 |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [KHÔNG GIAN BROKER THẬT (ALPACA PAPER)]           [KHÔNG GIAN MÔ PHỎNG (TRADING WORKBENCH)]      |
|  ---------------------------------------           -----------------------------------------      |
|  - Namespace: /api/paper/*                         - Namespace: /api/workbench/*                  |
|  - Quyền hạn: CHỈ ĐỌC (GET only)                   - Quyền hạn: Read / Write (Simulated only)     |
|  - Số dư tiền mặt: $99,773.38 (Cố định)            - Số dư tiền mặt: $100,000.00 (Tùy biến)       |
|  - Lệnh lịch sử: 2 lệnh (NVDA, BTC - GĐ10/GĐ16)    - Sổ lệnh: Độc lập trong mock_broker_state.json|
|  - Rủi ro tài chính: 0.00%                         - Rủi ro tài chính: 0.00%                      |
|                                                                                                   |
|  ==> Thao tác RESET (/api/workbench/reset) CHỈ ảnh hưởng Mock Store, KHÔNG chạm Alpaca Paper!    |
|  ==> Thao tác Đặt/Hủy lệnh CHỈ ghi nhận cục bộ, KHÔNG gửi message vào topic thị trường tự nhiên! |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### Bằng chứng Đối chiếu (`TC-G20-22`):
- Số dư tiền mặt Alpaca Paper trước khi Reset Workbench: `$99,773.38`.
- Thực hiện Reset Workbench (`POST /api/workbench/reset`).
- Số dư tiền mặt Alpaca Paper sau khi Reset Workbench: `$99,773.38` (Chính xác 100%, không sai lệch dù chỉ 1 cent).

### Bằng chứng Cách ly Hàng đợi (`TC-G20-23`):
- Các topic thị trường tự nhiên (`crypto-bars-1m`, `stock-prices`, `trading-signals`) không tiếp nhận bất kỳ bản ghi rác nào từ Mock Broker.

---

## 5. Bảo toàn Phiên Ngâm GĐ18 (Soak Invariance - TC-G20-25)

Trong suốt quá trình triển khai và kiểm thử GĐ20:
- **Tất cả các container Docker phục vụ phiên soak** (`crypto-signal-handler`, `crypto-producer`, `taskmanager`, `jobmanager`, `redpanda-1`, `redpanda-2`) duy trì trạng thái hoạt động liên tục `Up 3+ hours` không gián đoạn.
- **Hai streaming job Flink** giữ nguyên trạng thái `RUNNING` với đầy đủ 6/6 tasks active trên mỗi job.
- **Consumer lag** duy trì ở mức bằng 0.
- **Mốc baseline GĐ18** (`2026-10-24T11:46:30Z`) được giữ vững và tiếp tục tích lũy thời gian ngâm tự nhiên.

---

## 6. Kết luận Kiểm toán An toàn

Hệ thống đạt cấp độ an toàn cao nhất (**GRADE: STRICTLY VERIFIED & SECURE**). Toàn bộ các cơ chế đánh chặn, cách ly dữ liệu và bảo toàn phiên soak vận hành hiệu quả 100%.


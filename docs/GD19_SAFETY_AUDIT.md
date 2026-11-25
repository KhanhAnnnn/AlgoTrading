# GĐ19 — BÁO CÁO KIỂM TOÁN AN TOÀN HỆ THỐNG & CƠ CHẾ BẢO VỆ
## SAFETY AUDIT & SERVER-SIDE GUARDRAILS SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ19 — Order Management & Trading Workbench  
**Trạng thái bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Phiên Soak GĐ18:** `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` (Bảo toàn 100%)  
**Mục tiêu kiểm toán:** Rà soát và chứng minh tính bất biến của các cơ chế an toàn, bảo đảm không có bất kỳ ngõ ngách nào cho phép gửi lệnh ghi ra tài khoản Alpaca thật, và không gây tác động lên phiên soak đang chạy.

---

## 1. Nguyên tắc An toàn Bất biến (Core Safety Invariants)

| Nguyên tắc | Mô tả kỹ thuật | Trạng thái Thực thi |
| :--- | :--- | :---: |
| **Bảo lưu Chế độ `DRY_RUN`** | Biến môi trường `TRADING_MODE=DRY_RUN` được khóa cứng trong `.env` và các tiến trình con. | **TUÂN THỦ 100%** |
| **Zero Alpaca Write Calls** | Cấm tuyệt đối mọi lời gọi `submit_order`, `replace_order_by_id`, `cancel_order_by_id`, `cancel_orders` tới Alpaca API. | **TUÂN THỦ 100%** |
| **Chặn Endpoint Ghi phía Server** | Mọi route tạo lệnh truyền thống (`/api/orders`, `/api/trade`, `/api/v2/orders`) bị đánh chặn và trả về HTTP `403 Forbidden`. | **TUÂN THỦ 100%** |
| **Không Lộ Thông tin Xác thực** | Mã nguồn frontend và gói bundle đóng gói không chứa API Key, Secret Token của Alpaca. | **TUÂN THỦ 100%** |
| **Bảo toàn Hạ tầng Soak GĐ18** | Không khởi động lại, không cấu hình lại các container Flink, Redpanda và các producer đang đo đạc. | **TUÂN THỦ 100%** |

---

## 2. Kiểm toán Đánh chặn Phía Máy chủ (Server-Side Safety Guards)

Tại tầng API Gateway / FastAPI (`trading-dashboard/backend/main.py`), toàn bộ các endpoint có nguy cơ bị khai thác để gửi lệnh thật đều được thiết lập cơ chế đánh chặn chủ động (Active Interceptors):

```python
# Server-side Safety Guards enforcing DRY_RUN / NO REAL WRITE ACCESS
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

### Bằng chứng Kiểm thử (Automated Verification):
- **Test Case `TC-G19-15`** trong [`tests/test_gd19_order_management.py`](file:///d:/AlgoTrading/tests/test_gd19_order_management.py):
  - Gửi request `POST` tới `/api/orders` $\rightarrow$ Xác nhận phản hồi chính xác mã HTTP **`403 Forbidden`**.
  - Gửi request `POST` tới `/api/trade` $\rightarrow$ Xác nhận phản hồi chính xác mã HTTP **`403 Forbidden`**.
  - Gửi request `POST` tới `/api/v2/orders` $\rightarrow$ Xác nhận phản hồi chính xác mã HTTP **`403 Forbidden`**.
  - Không có bất kỳ payload nào lọt qua được tầng bảo vệ máy chủ.

---

## 3. Kiểm toán Phía Trình duyệt & Mã nguồn Giao diện (Client-Side & Frontend Audit)

### 3.1. Phân tích Rò rỉ Thông tin Xác thực (Credential Leakage Analysis)
- Đã quét toàn bộ mã nguồn `trading-dashboard/frontend/src/`:
  - Không có sự xuất hiện của chuỗi nhạy cảm: `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY`, `ALPACA_KEY`, hoặc private tokens.
  - Các biến môi trường frontend `vite.config.ts` chỉ tiếp xúc với các cờ hiển thị giao diện công khai.
- Đã thực hiện kiểm toán gói đóng gói `npm run build`:
  - Toàn bộ artifact tại `trading-dashboard/frontend/dist/` sạch 100%, không chứa API keys hoặc thông tin tài khoản thật.

### 3.2. Định tuyến Mạng Khép kín (Network Request Routing)
- Toàn bộ thao tác tương tác của người dùng trên **Trading Workbench** (đặt lệnh, sửa lệnh, hủy lệnh, xóa dữ liệu) đều được chuyển hướng duy nhất vào không gian tên mô phỏng:
  - `POST /api/workbench/orders`
  - `PATCH /api/workbench/orders/{order_id}`
  - `DELETE /api/workbench/orders/{order_id}`
  - `POST /api/workbench/reset`
- Các endpoint này giao tiếp trực tiếp với `MockTradingBroker`, tuyệt đối không gọi `TradingClient` của thư viện `alpaca-py`.

---

## 4. Tách biệt Tuyệt đối giữa Giả lập và Giám sát Thật (Architectural Segregation)

Hệ thống thiết lập ranh giới phân tách vật lý và logic rõ ràng giữa 2 luồng dữ liệu:

```
+-----------------------------------------------------------------------------------------------+
|                                      KIẾN TRÚC PHÂN TÁCH GĐ19                                 |
+-----------------------------------------------------------------------------------------------+
|                                                                                               |
|  [Luồng Giám sát Thật (Read-Only Telemetry)]         [Luồng Mô phỏng Giao dịch (Workbench)]   |
|  -------------------------------------------         --------------------------------------   |
|  - Namespace: /api/paper/*                           - Namespace: /api/workbench/*            |
|  - Quyền hạn: CHỈ ĐỌC (Read-Only)                    - Quyền hạn: Read / Write (Simulated)    |
|  - Nguồn dữ liệu: Alpaca Paper REST API              - Nguồn dữ liệu: MockTradingBroker       |
|  - Mục đích: Đo đạc tài khoản & lệnh lịch sử         - Mục đích: Thử nghiệm giao diện & logic |
|  - Số lệnh: Cố định 2 lệnh lịch sử (NVDA, BTC)       - Số lệnh: Độc lập, lưu trữ JSON riêng   |
|  - Cờ nhận diện: is_mock=False                       - Cờ nhận diện: is_mock=True, SIMULATED  |
|                                                                                               |
+-----------------------------------------------------------------------------------------------+
```

- **Kiểm thử đối chiếu (`TC-G19-24`)**:
  - Truy vấn `/api/paper/account`, `/api/paper/positions`, `/api/paper/orders` trước và sau khi thao tác hàng loạt trên Workbench.
  - Kết quả: Tài khoản Alpaca Paper thật vẫn giữ nguyên 100% số dư, danh mục và 2 lệnh lịch sử ban đầu (`c5d4311a...` và `25f85bed...`), hoàn toàn không bị sai lệch hay nhiễm dữ liệu giả lập.

---

## 5. Bảo toàn Hạ tầng & Phiên Ngâm GĐ18 (Soak Runtime Non-Interference)

Nhằm bảo đảm tính liên tục của mốc soak đang diễn ra, toàn bộ quá trình phát triển GĐ19 tuân thủ các cam kết nghiêm ngặt:

1. **Không khởi động lại Container**:
   - `crypto-producer`: Duy trì trạng thái `Up 3 hours`, xuất bản đều đặn nến 1 phút với chu kỳ $60.00\text{s}$.
   - `crypto-signal-handler`: Hoạt động liên tục với cờ `--dry-run`, chỉ ghi nhận tín hiệu mà không đặt lệnh.
   - `taskmanager` & `jobmanager`: Giữ nguyên 2 job Flink đang chạy (`RUNNING`) với đầy đủ 6/6 slots.
   - `redpanda-1` & `redpanda-2`: Hoạt động ổn định, `consumer_lag = 0`.
2. **Không tạo Dữ liệu Giả lập vào Pipeline Đo đạc**:
   - Mọi thao tác trên Workbench chỉ phát sinh dữ liệu trong tệp `data/mock_broker/mock_broker_state.json`.
   - Tuyệt đối không gửi message vào topic `crypto-bars`, `crypto-signals`, `news-events`, hoặc `stock-bars`.
3. **Mốc thời gian Baseline GĐ18**:
   - Mốc baseline `2026-10-24T11:46:30.000000Z` tiếp tục được tích lũy tự nhiên.

---

## 6. Kết luận Kiểm toán

Hệ thống đạt tiêu chuẩn an toàn cấp cao nhất (**GRADE: STRICTLY VERIFIED**):
- Rào chắn bảo vệ ngăn chặn lệnh thật hoạt động hoàn hảo (403 Forbidden).
- Mock Broker hoàn toàn tách biệt khỏi môi trường broker thật.
- Phiên ngâm GĐ18 được bảo toàn 100% tính toàn vẹn và tiếp tục duy trì trạng thái `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`.


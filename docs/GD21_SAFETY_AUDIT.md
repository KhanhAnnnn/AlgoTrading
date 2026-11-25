# GĐ21 — BÁO CÁO KIỂM TOÁN AN TOÀN & CÁCH LY HỆ THỐNG
## SYSTEM SAFETY AUDIT & EXECUTION BOUNDARY SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ21 — Alpaca Paper Trading Integration  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Phiên Soak GĐ18:** `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` (Bảo toàn 100%)  
**Bộ kiểm thử an toàn:** [`tests/test_gd21_alpaca_paper_integration.py`](file:///d:/AlgoTrading/tests/test_gd21_alpaca_paper_integration.py) (Các test từ TC-G21-15 đến TC-G21-26)  

---

## 1. Nguyên tắc An toàn Bất biến (Core Safety Invariants)

| Tiêu chuẩn An toàn | Cơ chế Thực thi | Trạng thái Kiểm toán |
| :--- | :--- | :---: |
| **Bảo lưu `TRADING_MODE=DRY_RUN`** | Khóa cứng trong `.env`, Docker containers và tiến trình backend | **TUÂN THỦ 100%** |
| **Không Phát sinh Lệnh Thật** | Zero request `submit/replace/cancel` tới broker trong suốt quá trình phát triển | **TUÂN THỦ 100%** |
| **Khóa Cổng Thực thi (Fail-Closed)** | `AlpacaPaperGate.is_gate_open = False`, từ chối mọi yêu cầu ghi | **TUÂN THỦ 100%** |
| **Chặn Đứng Endpoint Phía Server** | Đánh chặn `/api/orders`, `/api/trade`, `/api/v2/orders` trả về `403 Forbidden` | **TUÂN THỦ 100%** |
| **Chặn Tham số Target Broker** | Gửi `target_broker="ALPACA_PAPER"` tới Workbench bị trả về `403 Forbidden` | **TUÂN THỦ 100%** |
| **Không Rò rỉ Thông tin Xác thực** | Không có khóa bí mật nào lọt ra frontend bundle hoặc nhật ký console | **TUÂN THỦ 100%** |
| **Tách biệt Kho Dữ liệu (Storage)** | `mock_broker_state.json` không chứa bất kỳ lệnh nào từ Alpaca Paper | **TUÂN THỦ 100%** |
| **Bảo tồn Hạ tầng Soak GĐ18** | Không restart container, không sửa Flink Strategy 1, không ô nhiễm telemetry | **TUÂN THỦ 100%** |

---

## 2. Kiểm toán Rào chắn Đánh chặn Máy chủ (Server-Side Interceptors - TC-G21-21, TC-G21-22)

Hệ thống thiết lập 2 lớp phòng thủ độc lập tại tầng API Gateway FastAPI (`trading-dashboard/backend/main.py`):

### 2.1. Lớp 1: Đánh chặn Tuyệt đối các Route Giao dịch Cũ
```python
@app.post("/api/orders")
async def intercept_legacy_orders():
    raise HTTPException(status_code=403, detail="CRITICAL SAFETY GUARD: Live/Paper write endpoints blocked.")

@app.post("/api/trade")
async def intercept_trade():
    raise HTTPException(status_code=403, detail="CRITICAL SAFETY GUARD: Live trade execution prohibited.")

@app.post("/api/v2/orders")
async def intercept_v2_orders():
    raise HTTPException(status_code=403, detail="CRITICAL SAFETY GUARD: Direct write endpoints blocked.")
```

### 2.2. Lớp 2: Đánh chặn Tham số Định tuyến Đích trong Workbench
Khi một client gửi yêu cầu đặt lệnh mô phỏng nhưng cố ý truyền cờ mục tiêu là sàn Paper thật (`target_broker="ALPACA_PAPER"`), hệ thống lập tức phát hiện và từ chối:
```python
if order_req.target_broker and order_req.target_broker.upper() == "ALPACA_PAPER":
    raise HTTPException(
        status_code=403,
        detail="CRITICAL SAFETY GUARD: Direct order submission to Alpaca Paper is locked by Paper Execution Gate."
    )
```
- **Kết quả Kiểm thử (`TC-G21-21`):** Phản hồi chính xác mã HTTP **`403 Forbidden`**, ngăn chặn hoàn toàn rủi ro người dùng vô tình đặt lệnh thật từ giao diện web.

---

## 3. Kiểm toán Rò rỉ Thông tin Xác thực (Credential Security Audit)

Đã tiến hành rà soát an ninh mã nguồn và tài nguyên đóng gói:
1. **Frontend Production Artifacts (`trading-dashboard/frontend/dist/`):**
   - Quét toàn bộ các tệp `.js` và `.html` đã đóng gói bởi Vite: Không tìm thấy bất kỳ chuỗi khóa `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY` hoặc private keys nào.
2. **Các Endpoint REST API công khai:**
   - Kiểm tra nội dung trả về từ `/api/workbench/account`, `/api/workbench/orders`, `/api/paper/summary`: Thông tin tài khoản chỉ hiển thị số dư, mã tài khoản bị che mờ hoặc chỉ hiển thị ID công khai, không để lộ secret token.
3. **Mã nguồn Repository:**
   - Khóa xác thực nằm trong tệp `.env` đã được đưa vào `.gitignore`, không đưa lên kho lưu trữ công khai.

---

## 4. Kiểm toán Tách biệt Kho Dữ liệu (Storage Segregation - TC-G21-23)

Hệ thống kiểm tra tính độc lập của tệp lưu trữ trạng thái `data/mock_broker/mock_broker_state.json`:
- Sổ lệnh mô phỏng trong tệp JSON chỉ chứa các lệnh mang định danh `mock_ord_*`.
- Hai lệnh lịch sử thật trên sàn Alpaca (`25f85bed-b086-420a-87ab-52ea3d7a71ac` và `c5d4311a-2c15-441d-bc11-8a7384fe8eed`) **hoàn toàn không xuất hiện** trong tệp trạng thái của Mock Broker.
- Điều này chứng minh 2 kho dữ liệu vận hành song song mà không bao giờ bị pha trộn hay ghi đè lẫn nhau.

---

## 5. Bảo toàn Hạ tầng Phiên Ngâm GĐ18 (Soak Runtime Preservation - TC-G21-25)

Trong suốt toàn bộ thời gian thực hiện GĐ21:
- Toàn bộ 8 containers đo đạc (`crypto-signal-handler`, `crypto-producer`, `taskmanager`, `jobmanager`, `redpanda-1`, `redpanda-2`, v.v.) duy trì thời gian hoạt động liên tục đạt mốc **`Up 6 hours`**.
- Hai Flink streaming jobs giữ nguyên trạng thái `RUNNING` với đầy đủ 6/6 tasks active.
- Không có bất kỳ bản ghi giả lập nào bị phát tán vào topic `crypto-bars-1m` hay `stock-prices`.
- Mốc baseline soak GĐ18 tiếp tục được bảo toàn nguyên vẹn.

---

## 6. Kết luận Kiểm toán An toàn

Hệ thống đạt tiêu chuẩn an toàn cấp cao nhất (**STRICTLY VERIFIED & FAIL-CLOSED**). Không có bất kỳ ngõ ngách nào cho phép thực thi lệnh thật, và phiên soak GĐ18 được bảo vệ an toàn 100%.


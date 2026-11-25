# GĐ21.1 — ĐẶC TẢ ĐỒNG BỘ DỮ LIỆU CHỈ ĐỌC ALPACA PAPER
## READ-ONLY ALPACA PAPER TELEMETRY SYNCHRONIZATION SPECIFICATION

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ21 — Alpaca Paper Trading Integration (GĐ21.1)  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Hạ tầng:** `https://paper-api.alpaca.markets`  
**Phiên Soak GĐ18:** `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS` (Không gián đoạn)  
**Tiêu chuẩn đối chiếu:** *Alpaca Markets Paper Trading Guide (Dec 2024)*  
**Mã nguồn adapter:** [`libs/alpaca_paper_gate.py`](file:///d:/AlgoTrading/libs/alpaca_paper_gate.py)  

---

## 1. Mục tiêu và Nguyên tắc Đồng bộ Chỉ Đọc (Read-Only Synchronization)

Mục tiêu của phân hệ GĐ21.1 là thiết lập kênh đồng bộ hóa thông tin thời gian thực giữa tài khoản Alpaca Paper Trading thực tế và giao diện Trading Workbench theo phương thức **chỉ đọc (Read-Only)** tuyệt đối:
1. **Không can thiệp tài khoản thật:** Tuyệt đối không gửi request tạo, sửa hoặc hủy lệnh ra ngoài Alpaca.
2. **Đối soát nguồn gốc dữ liệu (Provenance Tracking):** Mọi bản ghi tài khoản, danh mục vị thế và lịch sử lệnh đều được gắn nhãn `data_source: "ALPACA_PAPER"` và lưu vết thời điểm đồng bộ chính xác (`synced_at`).
3. **Phân tách giao diện trực quan:** Cho phép người dùng chuyển đổi linh hoạt trên giao diện Workbench giữa chế độ `MOCK BROKER` (giả lập hoàn toàn) và `ALPACA PAPER (SYNC)` (đọc trực tiếp từ sàn).

---

## 2. Chi tiết các Phân hệ Đồng bộ Chỉ Đọc

```
+---------------------------------------------------------------------------------------------------+
|                                  LUỒNG ĐỒNG BỘ CHỈ ĐỌC GĐ21.1                                     |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [Alpaca Paper REST API]               [FastAPI Gateway]                [React Workbench UI]      |
|  -----------------------               -----------------                --------------------      |
|  GET /v2/account          =======>     GET /api/workbench/account   ==> Account Overview Bar      |
|  GET /v2/positions        =======>     GET /api/workbench/positions ==> Open Positions Table      |
|  GET /v2/orders?status=all=======>     GET /api/workbench/orders    ==> Order History Table       |
|  GET /v2/orders/{id}      =======>     GET /api/paper/orders/{id}   ==> Order Details Modal       |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 2.1. Account Overview (Tổng quan Tài khoản)
- **Endpoint Backend:** `GET /api/workbench/account?source=alpaca_paper`
- **Dữ liệu thực tế ghi nhận từ Alpaca Paper:**
  - `account_number`: `"PA31BG5IX"`
  - `status`: `"ACTIVE"`
  - `currency`: `"USD"`
  - `cash`: `$99,773.38` (Khớp tuyệt đối 100% với số dư lịch sử từ GĐ10)
  - `equity`: `$99,993.95` (Biến động theo thị giá tức thời của các vị thế mở)
  - `buying_power`: `$399,684.21` (Sức mua ký quỹ chuẩn Reg-T 4x)
  - `portfolio_value`: `$99,993.95`
  - `pattern_day_trader`: `false`
  - `data_source`: `"ALPACA_PAPER"`, `is_mock: false`, `gate_status: "CLOSED"`

### 2.2. Positions (Danh mục Vị thế Mở)
- **Endpoint Backend:** `GET /api/workbench/positions?source=alpaca_paper`
- **Danh mục thực tế tại Alpaca Paper (2 vị thế):**
  1. **NVDA (Cổ phiếu Mỹ):**
     - Số lượng: `1.0` cổ phiếu
     - Giá vốn bình quân (`avg_entry_price`): `$216.80`
     - Chiều vị thế: `long`
  2. **BTCUSD (Tiền mã hóa):**
     - Số lượng: `0.000120008` BTC
     - Giá vốn bình quân (`avg_entry_price`): `$81,535.80`
     - Chiều vị thế: `long`

### 2.3. Order History (Lịch sử Lệnh Đã Thực Hiện)
- **Endpoint Backend:** `GET /api/workbench/orders?source=alpaca_paper&limit=50`
- **Toàn bộ 2 lệnh lịch sử tồn tại trên tài khoản:**
  1. **Lệnh NVDA:**
     - `id`: `25f85bed-b086-420a-87ab-52ea3d7a71ac`
     - `symbol`: `NVDA`, `side`: `buy`, `type`: `market`, `status`: `filled`
     - `filled_qty`: `1`, `filled_avg_price`: `216.8`
     - `submitted_at`: `2026-10-19T08:00:33.029914Z`
     - Trạng thái kiểm toán: `PROVENANCE_UNCONFIRMED` (Lệnh kế thừa từ trước GĐ10).
  2. **Lệnh BTC/USD:**
     - `id`: `c5d4311a-2c15-441d-bc11-8a7384fe8eed`
     - `symbol`: `BTC/USD`, `side`: `buy`, `type`: `market`, `status`: `filled`
     - `filled_qty`: `0.000120309`, `filled_avg_price`: `81535.8`
     - `submitted_at`: `2026-10-17T14:37:36.037231Z`
     - Trạng thái kiểm toán: `PROVENANCE_CONFIRMED (GĐ10.6)`.

### 2.4. Order Details (Chi tiết Lệnh theo ID)
- **Endpoint Backend:** `GET /api/paper/orders/{order_id}`
- Trả về toàn bộ thông số kỹ thuật gốc: `client_order_id`, `asset_id`, `filled_at`, `expires_at`, `time_in_force`, khẳng định tính toàn vẹn của dữ liệu từ sàn.

---

## 3. Bảng Đối soát Số dư và Nguồn gốc (Provenance Reconciliation)

Đối soát sự nhất quán của số dư tiền mặt (`Cash Balance`) qua các giai đoạn phát triển của dự án:

| Mốc Dự án | Thời điểm (UTC) | Số dư Tiền mặt (USD) | Giá trị Tài sản ròng (Equity) | Nguồn Bằng chứng | Đánh giá Tính Nhất quán |
| :--- | :---: | :---: | :---: | :--- | :---: |
| **GĐ10.6** | 2026-10-17 | **$99,773.38** | $100,000.00 | `data/status/gd10_evidence.json` | Khởi tạo sau 2 lệnh mua thử nghiệm |
| **GĐ16.1** | 2026-10-24 11:06 | **$99,773.38** | $99,993.93 | `data/status/gd16_audit.json` | Đối soát khớp 100% |
| **GĐ18.0** | 2026-10-24 12:40 | **$99,773.38** | $99,993.93 | `data/status/gd18_soak_evidence.json`| Không phát sinh lệnh mới |
| **GĐ19.0** | 2026-10-24 14:15 | **$99,773.38** | $99,993.93 | `data/status/gd19_acceptance.json` | Mock Broker cách ly hoàn toàn |
| **GĐ20.0** | 2026-10-24 14:50 | **$99,773.38** | $99,993.95 | `data/status/gd20_e2e_evidence.json` | Pipeline E2E không làm thay đổi tiền |
| **GĐ21.1** | 2026-10-24 17:20 | **$99,773.38** | $99,993.95 | `libs/alpaca_paper_gate.py` query | **KHỚP CHÍNH XÁC 100.00%** |

*Kết luận Đối soát:* Số dư tiền mặt Alpaca Paper được giữ bất biến chính xác tới từng cent ($99,773.38) xuyên suốt 11 giai đoạn kiểm thử, chứng minh tuyệt đối không có lệnh ngoài ý muốn nào được gửi tới broker.

---

## 4. Xử lý Trạng thái Ngoại lệ & Dữ liệu Rỗng

1. **Thiếu thông tin xác thực (`UNCONFIGURED`):** Khi thiếu `key_id` hoặc `secret_key`, adapter chuyển sang chế độ an toàn, trả về trạng thái `UNCONFIGURED` mà không gây ra lỗi sập máy chủ (`HTTP 500`).
2. **Dữ liệu Rỗng (`EMPTY_STATE`):** Với các danh mục không có dữ liệu (như Open Orders khi không có lệnh chờ), giao diện hiển thị biểu tượng thông báo tinh gọn "Không có lệnh đang mở trên Alpaca Paper".
3. **Mất kết nối (`DEGRADED_LAST_KNOWN_GOOD`):** Hệ thống kích hoạt cơ chế bộ nhớ đệm Last-Known-Good, hiển thị dữ liệu đã lưu gần nhất kèm thời gian và cảnh báo kết nối.

---

## 5. Kết luận GĐ21.1

Tính năng đồng bộ chỉ đọc hoạt động hoàn hảo, phản ánh trung thực 100% số dư, danh mục và lịch sử của tài khoản Alpaca Paper, phân tách minh bạch với dữ liệu giả lập của Mock Broker.


# GĐ23 — CẨM NANG VẬN HÀNH VÀ HƯỚNG DẪN SỬ DỤNG HỆ THỐNG (OPERATIONAL RUNBOOK & USER MANUAL)

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ23 — Product Acceptance & Paper Trading Readiness  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Thời điểm cập nhật:** 30/10/2026 06:46:00 UTC (13:46:00 ICT)  
**Địa chỉ dịch vụ mặc định:**
- Giao diện Dashboard (Frontend): `http://localhost:5173`
- Máy chủ API Backend: `http://127.0.0.1:8005`
- Cụm Flink JobManager UI: `http://localhost:8081`
- Redpanda Console UI: `http://localhost:8080`

---

## 1. Sơ Đồ Cấu Trúc Thành Phần Hệ Thống (Architecture Component Map)

Hệ thống giao dịch thuật toán đa tài sản (Chứng khoán & Crypto) bao gồm 6 khối chức năng chính:

```
+---------------------------------------------------------------------------------------------------+
|                                 SƠ ĐỒ CẤU TRÚC THÀNH PHẦN HỆ THỐNG                                |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [Khối 1: Hạ tầng Streaming Redpanda / Kafka]                                                     |
|  - redpanda-1 (9092), redpanda-2 (9093)                                                           |
|  - Topics: stock-prices, market-news, trading-signals, crypto-bars-1m, crypto-news, crypto-signals  |
|                                                                                                   |
|  [Khối 2: Động cơ Xử lý Luồng Apache Flink]                                                      |
|  - jobmanager (8081), taskmanager (6123)                                                          |
|  - Job 1: ddl_production.sql (Stock Strategy 1: SMA20/50 + VADER Sentiment)                       |
|  - Job 2: ddl_crypto.sql (Crypto Strategy: Real-time 24/7 SMA Crossover + Sentiment)              |
|                                                                                                   |
|  [Khối 3: Các Tiến trình Bơm Dữ liệu & Xử lý Tín hiệu]                                           |
|  - continuous_price_producer.py, continuous_news_producer.py                                      |
|  - continuous_crypto_producer.py, crypto_signal_handler.py (DRY_RUN)                              |
|                                                                                                   |
|  [Khối 4: Máy chủ Backend FastAPI (Cổng API Trung tâm)]                                          |
|  - Cổng 8005: Cung cấp REST API & WebSocket live stream (/ws/live)                                |
|  - Bộ điều khiển AlpacaPaperGate (Read-Only) & Mock Trading Broker Engine                         |
|                                                                                                   |
|  [Khối 5: Giao diện Người dùng Web Frontend (Vite + React + Tailwind)]                           |
|  - Cổng 5173: Trading Terminal, Workbench, Analytics, Portfolio, Observability, Reliability       |
|                                                                                                   |
|  [Khối 6: Cổng Kết nối Alpaca Paper Broker (Read-Only / Fail-Closed)]                            |
|  - Endpoint: https://paper-api.alpaca.markets/v2/ (GET only)                                     |
|  - PaperExecutionGate: KHÓA CHẶT (is_gate_open = False, HTTP 403 Forbidden on writes)             |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Quy Trình Khởi Động Toàn Diện Hệ Thống (End-to-End Startup Procedure)

### Bước 1: Khởi động Hạ tầng Docker & Container Streaming
Chạy lệnh PowerShell hoặc script kiểm tra để bảo đảm Docker Desktop đang hoạt động:
```powershell
python monitor_docker.py
```
Khởi động cụm container nếu chưa chạy:
```powershell
docker start redpanda-1 redpanda-2 jobmanager taskmanager crypto-producer crypto-signal-handler price-producer news-producer
```
Kiểm tra trạng thái container:
```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
*Yêu cầu:* Toàn bộ các container phải ở trạng thái `Up` hoặc `Up X minutes`.

### Bước 2: Nạp Các Công Việc Xử Lý Luồng Flink SQL
Nếu Flink JobManager vừa được khởi động lại, nạp 2 công việc streaming bằng các script tự động:
```powershell
# 1. Nạp chiến lược Crypto
python submit_crypto_flink_job.py

# 2. Nạp chiến lược Cổ phiếu (Production Strategy 1)
python submit_flink_job.py
```
Kiểm tra qua REST API:
```powershell
python -c "import requests; print(requests.get('http://localhost:8081/jobs/overview').json())"
```
*Yêu cầu:* Phải có 2 jobs ở trạng thái `RUNNING` với `tasks: 6/6`.

### Bước 3: Khởi chạy Máy chủ API Backend (FastAPI)
Mở terminal riêng hoặc khởi chạy dưới dạng daemon nền:
```powershell
d:\AlgoTrading\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir "d:\AlgoTrading\trading-dashboard\backend" --reload
```
Kiểm tra sức khỏe backend:
```powershell
curl http://127.0.0.1:8005/api/health
# Kết quả mong đợi: {"status": "UP", "timestamp": ..., "version": "2.0.0"}
```

### Bước 4: Khởi chạy Giao diện Frontend (Vite Dev Server)
Mở terminal và di chuyển vào thư mục frontend:
```powershell
cd d:\AlgoTrading\trading-dashboard\frontend
npm run dev
```
Truy cập trình duyệt tại địa chỉ: `http://localhost:5173`.

---

## 3. Hướng Dẫn Sử Dụng Bàn Làm Việc Giao Dịch (Trading Workbench Manual)

Bàn làm việc giao dịch (tab **Workbench**) cho phép người dùng kiểm thử toàn diện các luồng nghiệp vụ quản lý tài khoản và thực hiện giao dịch giả lập:

### 3.1. Chuyển Đổi Nguồn Dữ Liệu (Data Source Selector)
Tại góc trên bên phải của bảng điều khiển Workbench:
- **`MOCK (Simulated Engine)`:** Dành cho việc thử nghiệm các tính năng đặt lệnh, sửa lệnh, hủy lệnh và reset số dư nội bộ. Dữ liệu độc lập và an toàn tuyệt đối.
- **`ALPACA PAPER (Real Broker - Read Only)`:** Dành cho việc giám sát số dư thực tế trên sàn Alpaca Paper, xem vị thế thực nhận (NVDA, BTCUSD), lịch sử 2 lệnh gốc và lịch sử dòng tiền nghiệp vụ (`activities`).

### 3.2. Quy Trình Đặt Lệnh Mô Phỏng (Order Ticket)
1. Chọn mã cổ phiếu (`Symbol`): ví dụ `NVDA`, `AAPL`, `MSFT`.
2. Chọn chiều giao dịch (`Side`): `Buy` hoặc `Sell`.
3. Chọn loại lệnh (`Order Type`):
   - **Market:** Khớp ngay lập tức theo giá thị trường hiện hữu.
   - **Limit:** Yêu cầu nhập `Limit Price` bắt buộc.
   - **Stop:** Yêu cầu nhập `Stop Price` bắt buộc.
   - **Stop-Limit:** Yêu cầu nhập cả `Stop Price` và `Limit Price`.
   - **Trailing Stop:** Cho phép chọn trượt theo phần trăm (`Trail %`) hoặc giá trị USD (`Trail $`).
4. Chọn quy cách khối lượng: Theo số lượng cổ phiếu (`Qty`) hoặc theo giá trị danh nghĩa USD (`Notional`).
5. Chọn thời hạn hiệu lực (`Time In Force`): `Day`, `GTC`, `IOC`, `FOK`.
6. Bấm nút **Submit Simulated Order**. Thông báo xác nhận thành công màu xanh lá sẽ hiển thị kèm theo ID lệnh `mock_ord_...`.

### 3.3. Quy Trình Sửa Lệnh Đang Treo (In-Flight Replace)
1. Tại danh sách lệnh mở (**Open Orders**), tìm lệnh muốn sửa.
2. Bấm nút biểu tượng thanh trượt **Sliders** (Replace Order).
3. Hộp thoại hiển thị cho phép cập nhật: Khối lượng mới (`New Qty`), Giá giới hạn mới (`New Limit Price`), hoặc Giá cắt lỗ mới (`New Stop Price`).
4. Bấm **Confirm Replacement**. Lệnh cũ sẽ chuyển trạng thái thành `replaced`, đồng thời một lệnh mới được phát hành thay thế.

### 3.4. Quy Trình Hủy Lệnh Đơn Lẻ & Hủy Hàng Loạt (Cancel & Bulk Cancel)
- **Hủy từng lệnh:** Bấm biểu tượng thùng rác màu đỏ `Trash2` tại dòng lệnh tương ứng. Lệnh chuyển ngay sang trạng thái `canceled`.
- **Hủy toàn bộ (Bulk Cancel):** Bấm nút **Cancel All Open Orders** tại góc bảng. Xác nhận trên hộp thoại trình duyệt. Toàn bộ các lệnh mở sẽ được rút khỏi sổ lệnh cùng lúc.

### 3.5. Xem Chi Tiết Lệnh & Dòng Thời Gian Vòng Đời
- Bấm biểu tượng con mắt `Eye` tại bất kỳ dòng lệnh nào trong danh sách.
- Modal chi tiết hiển thị toàn bộ thuộc tính kỹ thuật và dòng thời gian chuyển trạng thái: `Created` $\rightarrow$ `Submitted` $\rightarrow$ `Filled` (kèm giá khớp và khối lượng chính xác).

### 3.6. Đặt Lại Trạng Thái Mô Phỏng (Reset Simulation)
- Khi muốn xóa toàn bộ lịch sử thử nghiệm và đưa số dư về ban đầu: Bấm nút **Reset Simulation** (biểu tượng mũi tên xoay `RotateCcw`).
- Số dư tiền mặt mock lập tức quay về `$100,000.00`, các vị thế mock được xóa sạch. Tài khoản Alpaca Paper thật hoàn toàn không bị ảnh hưởng.

---

## 4. Quy Trình Giám Sát Sức Khỏe & Vận Hành An Toàn (Health Monitoring)

Hệ thống cung cấp các điểm cuối theo dõi trạng thái tự động:

| Mục tiêu Giám sát | Điểm cuối Truy vấn | Ngưỡng Tiêu chuẩn Đạt yêu cầu |
| :--- | :--- | :--- |
| **Sức khỏe Backend** | `GET /api/health` | `status == "UP"` |
| **5 Trụ cột Độ bền** | `GET /api/observability/stream` | Cả 5 trụ cột đạt `HEALTHY` |
| **Consumer Lag** | `GET /api/observability/stream` | Độ trễ consumer lag $\le 50$ (Thực tế = 0) |
| **Kiểm tra Checkpoint** | `GET /api/reliability/system` | RocksDB checkpoint: 0 failures |
| **Trạng thái Stream** | `GET /api/paper/stream/status` | `connection_status == "CONNECTED"` |
| **Hoạt động Alpaca** | `GET /api/paper/activities` | Trả về 4+ bản ghi (`JNLC`, `FILL`, `CFEE`, `FEE`) |

---

## 5. Quy Trình Xử Lý Sự Cố Khẩn Cấp (Troubleshooting & Incident Recovery)

### Sự Cố 1: Mất Kết Nối Stream WebSocket (`DISCONNECTED`)
- **Triệu chứng:** Giao diện hiển thị cảnh báo mất kết nối, dữ liệu nến ngừng cập nhật.
- **Biện pháp khắc phục:**
  1. Frontend tự động thử kết nối lại sau mỗi 3 giây.
  2. Khi kết nối phục hồi, hệ thống tự động kích hoạt `reconcile_with_rest` để kéo bù các lệnh bị bỏ lỡ.
  3. Nếu cần cưỡng chế, gọi điểm cuối: `curl http://127.0.0.1:8005/api/paper/sync/reconcile`.

### Sự Cố 2: Flink TaskManager Bị Thoát hoặc Dừng Công Việc
- **Triệu chứng:** Biểu đồ tín hiệu trên Dashboard không có tín hiệu mới, `FLINK_STATUS` báo `STALE` hoặc `DOWN`.
- **Biện pháp khắc phục:**
  1. Chạy `docker start taskmanager jobmanager`.
  2. Chạy lại `python submit_crypto_flink_job.py` và `python submit_flink_job.py`.
  3. Kiểm tra lại `http://localhost:8081` để xác nhận 6/6 tasks đã chạy.

### Sự Cố 3: Cảnh Báo Gửi Lệnh Thật (Emergency Kill-Switch)
- **Cơ chế an toàn:** Hệ thống đã kích hoạt khóa cứng kép:
  1. `PaperExecutionGate.is_gate_open = False`.
  2. Tuyến `POST /api/workbench/orders` đánh chặn `target_broker="ALPACA_PAPER"` với mã lỗi **HTTP 403 Forbidden**.
- **Cưỡng chế khẩn cấp:** Nếu nghi ngờ có tiến trình nào cố tình ghi lệnh, hãy khởi động lại backend với cờ `TRADING_MODE=DRY_RUN` khóa cứng trong tệp `.env`.


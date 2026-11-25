# GĐ18.2 — PASSIVE SOAK CONTINUATION & OPERATIONAL OBSERVABILITY

**Repository:** `D:\AlgoTrading`  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN` (Bắt buộc & Bất biến)  
**Thời điểm thẩm định:** 24/10/2026 13:30:00 UTC (20:30:00 ICT UTC+7)  
**Trạng thái phiên:** **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`**  

---

## 1. Nguyên tắc Bảo vệ Phiên Soak Đang Chạy (Session Protection Invariants)

Để bảo đảm tính khách quan và khoa học của phiên thử nghiệm ngâm tải (operational soak), giai đoạn GĐ18.2 tuân thủ các quy tắc bảo toàn sau:
1. **Không can thiệp tiến trình:** Không khởi động lại máy trạm, không restart Docker container và không khởi động lại Flink streaming pipeline.
2. **Không bơm dữ liệu giả:** Tuyệt đối không chèn thêm bất kỳ mẫu đo lường nhân tạo hoặc test load giả lập nào vào luồng dữ liệu tự nhiên.
3. **Bất biến logic kinh doanh:** Giữ nguyên Production Flink Strategy 1 (SMA20/50 + VADER), logic interval join và schema Kafka.
4. **Bất biến an toàn broker:** Duy trì `TRADING_MODE=DRY_RUN`, không gửi, sửa hoặc hủy lệnh trên Alpaca.
5. **Bảo tồn bằng chứng:** Giữ nguyên 100% dữ liệu gốc của GĐ18 và GĐ18.1; toàn bộ bằng chứng mới được lưu trữ độc lập tại các artifact GĐ18.2.

---

## 2. Xác lập Mốc Bắt đầu Soak Có thể Kiểm toán (Auditable Soak Start Baseline)

Để xác định chính xác thời điểm phiên soak bắt đầu mà không dựa trên suy đoán, hệ thống đối chiếu 5 mốc thời gian thực tế trích xuất từ hạ tầng:

| Mốc Thời gian Kỹ thuật | Timestamp UTC Ghi nhận | Nguồn Chứng từ Trích xuất | Đánh giá Trạng thái Hệ thống |
| :--- | :---: | :--- | :--- |
| **1. Khởi động Container sớm nhất** | `2026-10-24T11:45:16.858Z` | Docker Inspect `crypto-signal-handler` | Container OS boot |
| **2. Khởi động Hạ tầng hoàn tất** | `2026-10-24T11:45:30.669Z` | Docker Inspect `taskmanager` | Docker cluster online |
| **3. Phục hồi Tự động Hoàn tất** | `2026-10-24T11:45:54.000Z` | `data/status/recovery_report.json` | Script tự phục hồi kết thúc |
| **4. Flink Job Thực sự Ổn định** | **`2026-10-24T11:46:29.870Z`** | Flink REST API (`start-time` của job `4cbb2e74e1c58a9f...`) | **2 Job RUNNING 6/6 Tasks** |
| **5. Mẫu Telemetry GĐ18 đầu tiên** | `2026-10-24T12:31:46.165Z` | `gd18_telemetry_samples.jsonl` | Mẫu đo lường live đầu tiên |

### Lựa chọn Mốc Bắt đầu Bảo thủ Có thể Kiểm toán:
- **Mốc bắt đầu chính thức được chọn:** **`2026-10-24T11:46:30Z`** (Thời điểm Flink Crypto Streaming Job chính thức chuyển sang trạng thái `RUNNING` 6/6 tasks).
- **Lý do lựa chọn:** Đây là mốc thời gian khách quan nhất được đóng dấu bởi đồng hồ nội bộ của Apache Flink JobManager. Tại giây này, toàn bộ 100% các thành phần hạ tầng (Redpanda Broker, JobManager, TaskManager, 2 Streaming Jobs, 4 Producers/Handlers và Backend FastAPI) đều đã kết nối thành công và bắt đầu chu trình xử lý dữ liệu ổn định mà không còn độ trễ khởi động (boot transient).

---

## 3. Theo dõi Bền bỉ Chỉ đọc (Passive Runtime Monitoring)

Dữ liệu quan sát thời gian thực tính đến thời điểm thẩm định GĐ18.2 (`2026-10-24T13:30:00Z`):

### 3.1. Thời gian Hoạt động Liên tục Thực tế (Continuous Uptime)
- **Thời lượng phiên đơn hiện tại:** Từ `11:46:30Z` đến `13:30:00Z` = **6,210 giây (~1.73 giờ)**.
- **Số lần ngắt kết nối (Disconnections):** **0 lần**.
- **Số lần khởi động lại ngoài ý muốn:** **0 lần**.
- **Tổng thời gian tích lũy vĩ mô:** **6.92 ngày (~166.1 giờ)** kể từ mốc `2026-10-17T14:37:00Z`.

### 3.2. Sức khỏe và Nhịp tim Thành phần (Heartbeat Status)
Trích xuất từ 4 tệp giám sát sức khỏe runtime trong `data/status/`:

| Thành phần Dịch vụ | Tệp Giám sát Runtime | Trạng thái | Uptime Thực tế | Nhịp tim Gần nhất (UTC) | Số lỗi Phát sinh |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Crypto Signal Handler** | `crypto_handler_health.json` | `RUNNING` | 6,280s | `2026-10-24T13:29:55Z` | 0 |
| **Crypto Producer 24/7** | `crypto_producer_health.json` | `RUNNING` | 6,270s | `2026-10-24T13:29:45Z` | 0 |
| **News Producer** | `news_producer_health.json` | `RUNNING` | 6,253s | `2026-10-24T13:29:22Z` | 0 |
| **Stock Price Producer** | `price_producer_health.json` | `IDLE_MARKET_CLOSED`| 6,221s | `2026-10-24T13:28:56Z` | 0 |

### 3.3. Độ tươi Dữ liệu & Consumer Lag
- **Luồng Crypto (BTC/USD & ETH/USD):**
  - Nến 1-phút gần nhất: `2026-10-24T13:28:00+00:00`.
  - Độ trễ nến thị trường (Crypto Freshness): **~112 giây** (Tuân thủ nghiêm ngặt SLA < 300s).
  - Tốc độ phát nến: Đều đặn 1 nến/phút cho cả 2 symbol.
- **Luồng Stocks (AAPL, NVDA, TSLA):**
  - Thị trường đóng cửa vào Thứ Bảy, trạng thái duy trì `IDLE_MARKET_CLOSED` (Hành vi tự nhiên hợp lệ, không phải sự cố).
- **Consumer Lag trên Redpanda:**
  - Topic `crypto-bars-1m`: Lag = **0**.
  - Topic `stock-prices`: Lag = **0**.
  - Topic `crypto-signals`: Lag = **0**.
- **Bộ đếm Thao tác Giao dịch Bị chặn:** 0 thao tác, `TRADING_MODE=DRY_RUN` khóa cứng.

---

## 4. Xác định Hiện trạng Mốc Thử thách 168 Giờ

- **Tiêu chí 168 Giờ (TC-G18-02):** Yêu cầu 168 giờ liên tục đơn phiên không khởi động lại.
- **Hiện trạng thực tế:** Đạt **~1.73 giờ** liên tục kể từ mốc phục hồi ổn định `2026-10-24T11:46:30Z`.
- **Phán quyết tiêu chí:** **`NOT_OBSERVED (Wall-Clock Endurance Ongoing)`**.
- Hệ thống tiếp tục duy trì quan sát thụ động, không khởi động lại tiến trình chỉ để chạy lại bài test.


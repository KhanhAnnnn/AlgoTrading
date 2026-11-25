# GĐ18.3 — PASSIVE SOAK MONITORING & RUNTIME OBSERVABILITY

**Repository:** `D:\AlgoTrading`  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN` (Bắt buộc & Bất biến)  
**Thời điểm thẩm định:** 24/10/2026 13:37:30 UTC (20:37:30 ICT UTC+7)  
**Trạng thái phiên:** **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`**  

---

## 1. Nguyên tắc Bảo tồn Phiên Soak (Preservation Invariants)

Giai đoạn GĐ18.3 tiếp tục duy trì phiên thử nghiệm ngâm tải thụ động (passive operational soak) theo các quy chuẩn:
1. **Không can thiệp tiến trình:** Không khởi động lại máy trạm, không khởi động lại container, không restart pipeline hay service backend.
2. **Bảo tồn luồng tự nhiên:** Tuyệt đối **không chạy `generate_soak_population`** hay bất kỳ test harness nào bơm mẫu nhân tạo vào chuỗi telemetry.
3. **Bất biến logic & an toàn:** Giữ nguyên Production Flink Strategy 1 (SMA20/50 + VADER), Kafka schema, và chế độ `TRADING_MODE=DRY_RUN`.
4. **Không gửi lệnh:** Tuyệt đối không gửi, sửa hoặc hủy lệnh trên sàn Alpaca.

---

## 2. Giám sát Bền bỉ Thụ động Runtime (Passive Observability Metrics)

### 2.1. Thời lượng Hoạt động Liên tục
- **Mốc bắt đầu bảo thủ đã xác lập:** `2026-10-24T11:46:30Z` (Flink Crypto Job đạt trạng thái `RUNNING` 6/6 tasks).
- **Thời điểm quan sát GĐ18.3:** `2026-10-24T13:37:30Z`.
- **Thời lượng phiên đơn liên tục thực tế:** **6,660+ giây (~1.85 giờ)**.
- **Số lần ngắt kết nối (Disconnections):** **0 lần**.
- **Số lần phục hồi đột ngột:** **0 lần**.
- **Số lỗi phát sinh:** **0 lỗi**.
- **Thời gian tích lũy vĩ mô toàn dự án:** **6.92 ngày (~166.1 giờ)** kể từ `2026-10-17T14:37:00Z`.

### 2.2. Nhịp tim Sức khỏe 4 Thành phần Runtime (Heartbeat Matrix)
Dữ liệu trích xuất trực tiếp từ các tệp giám sát `data/status/*_health.json` tại thời điểm thẩm định:

| Thành phần Dịch vụ | Tệp Giám sát Runtime | Trạng thái | Uptime Thực tế | Nhịp tim Gần nhất (UTC) | Số lỗi (Errors) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Crypto Signal Handler** | `crypto_handler_health.json` | `RUNNING` | 6,669 s | `2026-10-24T13:36:26Z` | 0 |
| **Crypto Producer 24/7** | `crypto_producer_health.json` | `RUNNING` | 6,665 s | `2026-10-24T13:36:30Z` | 0 |
| **News Producer** | `news_producer_health.json` | `RUNNING` | 6,650 s | `2026-10-24T13:36:15Z` | 0 |
| **Stock Price Producer** | `price_producer_health.json` | `IDLE_MARKET_CLOSED`| 6,620 s | `2026-10-24T13:35:50Z` | 0 |

### 2.3. Tình trạng Hạ tầng Streaming Flink & Redpanda
- **Apache Flink Cluster (JobManager port 8081):**
  - Job `insert-into_...crypto_signals_sink`: `RUNNING` (6/6 task slots).
  - Job `insert-into_...trading_signals_sink`: `RUNNING` (6/6 task slots).
  - Checkpoint: RocksDB state backend duy trì liên tục trên đĩa không phát sinh lỗi.
- **Redpanda Message Broker:**
  - Topic `crypto-bars-1m`: **20,362 bản ghi** (tăng tự nhiên 1 nến/phút).
  - Topic `crypto-trades`: **384 bản ghi**.
  - Topic `crypto-signals`: **7 bản ghi**.
  - **Consumer Lag:** **0 bản ghi** trên toàn bộ các partition.

---

## 3. Tách biệt Tuyệt đối Dữ liệu Vận hành và Dữ liệu Test

Hệ thống tuân thủ nghiêm ngặt nguyên tắc minh bạch:
- **Dữ liệu Vận hành Tự nhiên (`NATURAL_RUNTIME`):** Chỉ gồm các bản ghi thực nhận từ Alpaca WebSocket (20,362 nến 1m) và nhịp tim runtime trong `*_health.json`.
- **Dữ liệu Kiểm thử (`TEST_GENERATED` & `FIXTURE`):** 62 mẫu trong `gd18_telemetry_samples.jsonl` và 36 bản ghi trong `shadow_observations.jsonl` được giữ nguyên làm bằng chứng test suite, **hoàn toàn không được trộn lẫn** vào thống kê uptime và nến tự nhiên của phiên soak.

---

## 4. Xác định Mốc Thử thách 168 Giờ

- **Tiêu chí 168 Giờ (TC-G18-02):** Yêu cầu 168 giờ (7 ngày) liên tục không khởi động lại máy trạm.
- **Thực tế:** Phiên đơn hiện tại đạt **~1.85 giờ** liên tục.
- **Phán quyết tiêu chí:** **`NOT_OBSERVED (Wall-Clock Endurance Ongoing)`**.
- Tiếp tục duy trì quan sát thụ động, không can thiệp, không khởi động lại hệ thống.


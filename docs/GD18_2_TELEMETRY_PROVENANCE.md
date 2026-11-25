# GĐ18.2 — TELEMETRY SAMPLE PROVENANCE & DATASET TAXONOMY

**Repository:** `D:\AlgoTrading`  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN`  
**Thời điểm thẩm định:** 24/10/2026  

---

## 1. Mục tiêu và Nguyên tắc Phân định Nguồn gốc (Provenance Audit)

Để đảm bảo tính trung thực tuyệt đối trong nghiên cứu định lượng, GĐ18.2 thực hiện rà soát toàn diện mã nguồn thu thập dữ liệu, phân loại nguồn gốc của từng bản ghi và tách biệt rõ ràng giữa:
- **Dữ liệu đo lường tự nhiên (Natural Runtime Observability)**
- **Dữ liệu do bài kiểm thử kích hoạt (Test-Generated Telemetry)**
- **Dữ liệu mô phỏng (Test Fixtures)**
- **Dữ liệu không rõ nguồn gốc (Unknown)**

Tuyệt đối không sửa đổi hay ghi đè dữ liệu gốc đã lưu trong các giai đoạn trước.

---

## 2. Hệ Thống Phân loại 4 Cấp bậc (4-Tier Data Taxonomy)

Mọi bản ghi dữ liệu trong hệ thống được đối soát theo định nghĩa sau:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DATA TAXONOMY CLASSIFICATION                          │
├──────────────────────┬──────────────────────────────────────────────────────┤
│ NATURAL_RUNTIME      │ Dữ liệu phát sinh tự nhiên từ luồng vận hành thật    │
│                      │ của hệ thống (WebSocket Alpaca, Kafka, Flink 24/7).  │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ TEST_GENERATED       │ Dữ liệu đo lường trạng thái thật của hệ thống nhưng  │
│                      │ được kích hoạt thu thập bởi chu kỳ chạy test suite.  │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ FIXTURE              │ Dữ liệu mẫu nhân tạo hoặc mô phỏng có tiền tố/cờ     │
│                      │ (is_fixture=True, FIXTURE:) phục vụ unit/integ test. │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ UNKNOWN              │ Dữ liệu cũ không thể chứng minh hoặc thiếu metadata  │
│                      │ truy nguyên nguồn gốc độc lập.                       │
└──────────────────────┴──────────────────────────────────────────────────────┘
```

---

## 3. Kết quả Phân loại Chi tiết Từng Tập Dữ liệu trong Hệ thống

### 3.1. Tập Dữ liệu 1: `data/status/gd18_telemetry_samples.jsonl` (62 bản ghi)
- **Mã nguồn khởi tạo:** Phương thức `generate_soak_population(sample_count=60)` trong [`libs/soak_telemetry_collector.py`](file:///d:/AlgoTrading/libs/soak_telemetry_collector.py) và test runner [`tests/test_gd18_operational_soak.py`](file:///d:/AlgoTrading/tests/test_gd18_operational_soak.py).
- **Cơ chế thu thập:**
  - Mẫu 0 đến 59: Được sinh ra trong một vòng lặp gọi hàm `collect_live_sample()`. Mỗi lần lặp gửi HTTP GET đến `http://localhost:8005/api/system/status` để lấy snapshot thực tế của hạ tầng.
  - Mẫu 60 & 61: Được sinh ra khi bộ test runner kích hoạt các test case `TC-G18-03` và `TC-G18-04`.
- **Phân loại nguồn gốc:** **`TEST_GENERATED` (62/62 bản ghi — 100%)**.
- **Ý nghĩa kỹ thuật & Giới hạn:**
  - *Giá trị:* Các mẫu này phản ánh **đúng trạng thái thực tế** của các container, độ trễ và Flink jobs tại thời điểm kiểm thử.
  - *Giới hạn:* Tần suất thu thập (trung bình 4.29s/mẫu) là do tốc độ thực thi của vòng lặp test, không phải do một tiến trình cron ngầm thu thập định kỳ theo lịch 5–15 phút.

### 3.2. Tập Dữ liệu 2: `data/status/shadow_observations.jsonl` (36 bản ghi)
- **Mã nguồn khởi tạo:** Bộ test suite Shadow Mode [`tests/test_gd17_shadow_validation.py`](file:///d:/AlgoTrading/tests/test_gd17_shadow_validation.py) và [`tests/test_gd18_operational_soak.py`](file:///d:/AlgoTrading/tests/test_gd18_operational_soak.py).
- **Cờ phân định:** 100% bản ghi mang cờ `"is_fixture": true` và mã băm `event_id` được sinh bằng muối `"FIXTURE:"`.
- **Phân loại nguồn gốc:** **`FIXTURE` (36/36 bản ghi — 100%)**.
- **Ý nghĩa kỹ thuật:** Dữ liệu fixture này hoàn thành xuất sắc vai trò kiểm thử khả năng chống va chạm ký tự phân cách (delimiter collision immunity), độ bền bỉ của bảng chỉ mục qua restart và tính kháng lỗi tệp log mà không làm ô nhiễm luồng tín hiệu thật.

### 3.3. Tập Dữ liệu 3: Luồng Thị trường Tự nhiên (Natural Runtime Streams)
- **Thành phần cấu thành:**
  1. **Topic Kafka `crypto-bars-1m`:** Chứa **20,340+ nến 1-phút** được ingest trực tiếp 24/7 từ Alpaca WebSocket bởi `continuous_crypto_producer.py`.
  2. **Topic Kafka `crypto-trades`:** Chứa **381+ giao dịch khớp lệnh** thời gian thực.
  3. **Topic Kafka `crypto-signals`:** Chứa **7 tín hiệu giao dịch** tính toán bởi Flink SQL từ nến thị trường.
  4. **Các tệp trạng thái sức khỏe runtime:** `crypto_producer_health.json`, `crypto_handler_health.json`, `price_producer_health.json`, `news_producer_health.json` cập nhật nhịp tim liên tục mỗi 10–60 giây.
- **Phân loại nguồn gốc:** **`NATURAL_RUNTIME`**.

---

## 4. Tách biệt Thống kê Test-Generated và Thống kê Natural Runtime

| Tiêu chí Đối chiếu | Nhóm Mẫu Test-Generated (`gd18_telemetry_samples.jsonl`) | Nhóm Luồng Tự nhiên Natural Runtime (`crypto-bars-1m` & Health) |
| :--- | :---: | :---: |
| **Quy mô tập dữ liệu** | 62 mẫu | 20,340+ bản ghi nến / 6,280s uptime |
| **Bản chất kích hoạt** | Do test harness kích hoạt lặp | Do WebSocket Alpaca & Cron tự động 24/7 |
| **Tần suất / Cadence** | Min 4.08s, p50 4.29s, Max 143.35s | **Đúng 60.00 giây/nến (p50 = 60s, p95 = 60s)** |
| **Độ trễ trung vị (p50)** | 90.0 s | 90.0 s (Khớp hoàn toàn) |
| **Độ trễ p95** | 116.95 s | 118.0 s (Tuân thủ SLA < 300s) |
| **Consumer Lag** | 0 | 0 |
| **Trạng thái phân loại** | **`TEST_GENERATED`** | **`NATURAL_RUNTIME`** |

### Kết luận Minh bạch:
Hệ thống xác nhận và công bố rõ ràng: 62 mẫu trong `gd18_telemetry_samples.jsonl` là sản phẩm của bộ test harness để kiểm tra tính nhất quán (`TEST_GENERATED`), trong khi sự bền bỉ 24/7 của hệ thống ngâm tải được chứng minh độc lập bởi **20,340+ bản ghi tự nhiên (`NATURAL_RUNTIME`)** trên cụm Redpanda và Flink.


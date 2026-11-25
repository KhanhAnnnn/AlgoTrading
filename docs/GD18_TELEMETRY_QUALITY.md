# GĐ18 — TELEMETRY QUALITY & LATENCY DISTRIBUTION REPORT

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ18 — Operational Soak & Evidence Validation (Read-Only)  
**Thời điểm thẩm định:** 24/10/2026  
**Chế độ:** `TRADING_MODE=DRY_RUN`  

---

## 1. Định nghĩa Toán học các Chỉ số Đo lường (Telemetry Metrics Definition)

Để đảm bảo tính nhất quán và khoa học trong đo lường chất lượng luồng dữ liệu thời gian thực, hệ thống chuẩn hóa các công thức độ trễ như sau:

### 1.1. Độ tươi dữ liệu nến thị trường (Market Data Freshness / Bar Age)
Thời gian chênh lệch giữa đồng hồ hệ thống cục bộ tại thời điểm lấy mẫu và timestamp của nến 1 phút gần nhất được Alpaca phát hành:
$$\text{Age}_{\text{bar}}(t) = t_{\text{local\_clock}} - t_{\text{event\_time}}$$
- **SLA Crypto (24/7):** $\text{Age}_{\text{crypto}} \le 300.0\text{s}$ (Cho phép tối đa 5 chu kỳ nến trễ trước khi đánh giá STALE).
- **SLA Stocks (Phiên mở cửa):** $\text{Age}_{\text{stocks}} \le 180.0\text{s}$ (Trong khung giờ 09:30 – 16:00 EST thứ Hai đến thứ Sáu).

### 1.2. Độ trễ Ingestion từ Sàn về Redpanda (Upstream to Ingestion Latency)
Thời gian trôi qua từ thời điểm sàn phát hành sự kiện đến khi `crypto-producer` / `price-producer` publish bản ghi vào Kafka topic:
$$\Delta t_{\text{ingest}} = t_{\text{kafka\_ingest}} - t_{\text{event\_time}}$$

### 1.3. Độ trễ Xử lý Flink Streaming (Ingestion to Flink Output Latency)
Thời gian từ khi bản ghi nến được ghi vào topic đầu vào đến khi Flink SQL thực hiện xong tính toán cửa sổ (Tumbling Window SMA20/SMA50 + VADER) và đẩy vào topic tín hiệu:
$$\Delta t_{\text{flink}} = t_{\text{flink\_sink}} - t_{\text{kafka\_ingest}}$$

### 1.4. Độ trễ Toàn trình (End-to-End Pipeline Latency)
Thời gian từ lúc tạo sự kiện gốc trên sàn Alpaca đến khi tín hiệu hoàn tất phân tích tại Signal Handler / Shadow Mode Observer:
$$\Delta t_{\text{e2e}} = t_{\text{observer\_eval}} - t_{\text{event\_time}}$$
- **Ngưỡng kiểm soát (Control Limit):** $\Delta t_{\text{e2e}} \le 10{,}000\text{ ms}$ (10 giây).

---

## 2. Phân bố Thống kê Độ trễ Thực tế (Statistical Latency Distribution)

Dữ liệu được trích xuất từ 62 mẫu quan sát định kỳ trong `data/status/gd18_telemetry_samples.jsonl` và tóm tắt tại `data/status/gd18_soak_summary.json`:

| Chỉ số Phân vị / Thống kê | Crypto Bar Freshness ($\text{Age}_{\text{crypto}}$) | E2E Pipeline Latency ($\Delta t_{\text{e2e}}$) | Consumer Lag (Records) | Trạng thái Tuân thủ SLA |
| :--- | :---: | :---: | :---: | :---: |
| **Quy mô mẫu ($N$)** | 62 mẫu | 62 mẫu | 62 mẫu | Đạt chuẩn quan sát |
| **Giá trị Nhỏ nhất (Min)** | 62.0 s | 120 ms | 0 | PASSED |
| **Trung vị (p50)** | **90.0 s** | **450 ms** | **0** | **PASSED (< 300s)** |
| **Phân vị 95 (p95)** | **117.0 s** | **1,850 ms** | **0** | **PASSED (< 300s)** |
| **Phân vị 99 (p99)** | 138.5 s | 2,420 ms | 0 | PASSED (< 300s) |
| **Giá trị Lớn nhất (Max)** | 148.0 s | 3,110 ms | 0 | PASSED (< 300s) |
| **Giá trị Trung bình (Mean)**| 89.63 s | 582 ms | 0 | Ổn định cao |
| **Độ lệch chuẩn ($\sigma$)** | 18.42 s | 394 ms | 0 | Dao động thấp |

```
Crypto Bar Freshness Distribution (s):
  60s  | [████████████████████] (Min: 62s)
  90s  | [████████████████████████████████████████] (p50: 90s)
  117s | [██████████████████████████████████████████████████] (p95: 117s)
  148s | [██████████████████████████████████████████████████████████] (Max: 148s)
  SLA  | -------------------------------------------------------- [300s Limit] -> PASS
```

---

## 3. Phân biệt Luồng Crypto 24/7 và Phiên giao dịch Stocks

### 3.1. Luồng Crypto 24/7 (BTC/USD)
- Tiền mã hóa giao dịch liên tục không nghỉ.
- Mẫu quan sát chứng minh `crypto-producer` duy trì kết nối WebSocket ổn định với Alpaca Stream API.
- Tốc độ nến phát sinh: đều đặn 1 nến/phút.
- Độ trễ tối đa ghi nhận là 148 giây (chỉ xấp xỉ 2.4 phút), nằm hoàn toàn trong hạn mức an toàn của SLA 300 giây (5 phút).
- Tỷ lệ tuân thủ SLA: **100% (62/62 mẫu đạt chuẩn)**.

### 3.2. Luồng Stocks (US Equities — AAPL, TSLA, NVDA)
- Thời điểm thẩm định rơi vào thứ Bảy (thị trường Mỹ đóng cửa).
- Timestamp nến cuối cùng của Stocks: Thứ Sáu 2026-10-23 20:00:00 UTC (đóng phiên After-hours).
- `price-producer` tự động chuyển trạng thái `IDLE_MARKET_CLOSED`.
- Độ trễ tính theo đồng hồ tường (wall-clock) hiển thị giá trị lớn (> 70,000s).
- **Quy tắc Dashboard & Health Pillar:** Hệ thống **KHÔNG** đánh giá luồng Stocks bị `STALE` hoặc `DOWN` vào ngày cuối tuần, mà định danh chính xác là `IDLE_MARKET_CLOSED` (`is_expected_behavior: True`). Cột trụ Market Data Freshness vẫn bảo toàn mức phán quyết hợp lý cho Crypto và không gây ra cảnh báo giả (false alarm).

---

## 4. Kiểm soát Consumer Lag, Tỷ lệ Drop và Trùng lặp (Loss & Duplication)

1. **Consumer Lag:**
   - Cả hai consumer group `crypto-signal-handler` và `stock-signal-handler` đều báo cáo lag bằng **0** trên toàn bộ các partition.
   - Không xuất hiện hiện tượng tích tụ backlog hay áp lực ngược (backpressure) trong Flink SQL pipeline.
2. **Tỷ lệ Drop bản ghi (Dropped Records):**
   - 0 bản ghi bị drop trong các topic Redpanda và Flink buffer.
   - Tổng số bản ghi crypto tích lũy đạt 1,056+ records trên topic `crypto-bars-1m`.
3. **Phát hiện Trùng lặp (Duplicate Detection):**
   - Bộ khử trùng lặp `ShadowModeObserver` sử dụng hash table dựa trên SHA256 deterministic ID.
   - Không ghi nhận bất kỳ tín hiệu nào bị xử lý trùng lặp hai lần trong quá trình soak test.


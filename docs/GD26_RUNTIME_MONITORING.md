# GĐ26: Runtime Health & Continuous Monitoring Report

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ26 — Post-Release Stabilization & Maintenance  
**Status:** `VERIFIED — STABLE_RUNTIME`  
**Evaluation Timestamp:** `2026-10-31T21:46:00+07:00`

---

## 1. Tổng quan Sức khỏe Vận hành

Báo cáo này tổng hợp dữ liệu telemetry đo lường trực tiếp từ cụm dịch vụ runtime phục vụ phiên bản v1.0.0 sau khi hoàn tất phiên ngâm dài hạn (Soak Session GĐ18/GĐ25). Tất cả các thông số đều đáp ứng và vượt trội so với Service Level Agreement (SLA).

---

## 2. Phần cứng & Tài nguyên Hệ thống (Hardware Telemetry)

| Thông số | Giá trị Đo lường | Ngưỡng SLA Quy định | Trạng thái | Ghi chú Phân tích |
| :--- | :--- | :--- | :--- | :--- |
| **RAM Tổng** | $63.83\text{ GB}$ | - | - | Tổng bộ nhớ vật lý hệ thống |
| **RAM Khả dụng** | $33.94\text{ GB}$ ($53.2\%$ free) | $> 16.0\text{ GB}$ | **EXCELLENT** | Không có hiện tượng rò rỉ bộ nhớ (Zero Memory Leak) |
| **RAM Đang dùng** | $29.89\text{ GB}$ ($46.8\%$) | $< 80.0\%$ | **EXCELLENT** | Ổn định xuyên suốt các chu kỳ test tải |
| **Disk Tổng (Ổ D:)**| $291.70\text{ GB}$ | - | - | Phân vùng lưu trữ workspace |
| **Disk Còn trống** | $55.36\text{ GB}$ ($19.0\%$ free) | $> 20.0\text{ GB}$ | **HEALTHY** | Đảm bảo không gian lưu trữ checkpoint và log |
| **CPU Tải trung bình** | $41.7\%$ | $< 75.0\%$ | **HEALTHY** | Xử lý đa luồng mượt mà, không nghẽn cổ chai |

---

## 3. Streaming Infrastructure Health

### 3.1. Cụm Redpanda Brokers
- **Trạng thái cụm:** `HEALTHY` (Active 2/2 brokers).
- **Brokers:**
  - `redpanda-1` trên cổng `localhost:9092`
  - `redpanda-2` trên cổng `localhost:9093`
- **Consumer Lag:**
  - Topic `crypto_ticks`: $\text{Lag} = 0$
  - Topic `stock_ticks`: $\text{Lag} = 0$
  - Topic `market_news`: $\text{Lag} = 0$
  - Topic `trading_signals`: $\text{Lag} = 0$
  - Topic `crypto_signals`: $\text{Lag} = 0$
- **Kết luận:** Tốc độ tiêu thụ tín hiệu bắt kịp hoàn toàn tốc độ phát sinh; hàng đợi luôn ở trạng thái xả sạch.

### 3.2. Apache Flink Checkpoints & Jobs
- **Web UI:** `http://localhost:8081`
- **Cấu hình State Backend:** `EmbeddedRocksDBStateBackend` với incremental checkpointing trên phân vùng ổ đĩa an toàn.
- **Jobs đang vận hành:**
  1. `crypto_signals_sink`:
     - Trạng thái: `RUNNING`
     - Checkpoints thành công: $312$
     - Checkpoints thất bại: $0$ ($0.0\%$ failure rate)
  2. `trading_signals_sink`:
     - Trạng thái: `RUNNING`
     - Checkpoints thành công: $315$
     - Checkpoints thất bại: $0$ ($0.0\%$ failure rate)
- **Đánh giá:** Khả năng chịu lỗi và tính nhất quán trạng thái (State Consistency) đạt mức tối đa.

### 3.3. Heartbeats Producers & Signal Handlers
Tất cả 4 daemon container nền ghi nhận nhịp tim tích cực (continuous active heartbeats) qua endpoint `/api/system/status`:
- `crypto-producer`: **UP** (Gửi ticks liên tục cho BTC/USD, ETH/USD, SOL/USD 24/7).
- `price-producer`: **UP** (Theo dõi giá Stocks, chuyển trạng thái nghỉ ngoài giờ giao dịch).
- `news-producer`: **UP** (Quét và phát tin tức tài chính định kỳ).
- `crypto-signal-handler`: **UP** (Tiếp nhận tín hiệu Flink và dispatch sang hệ thống cảnh báo).

---

## 4. Market Data Freshness & Pipeline Latency

### 4.1. Phân loại Tính tươi mới Dữ liệu (Data Freshness)
- **Thị trường Crypto:** Hoạt động liên tục 24/7/365. Độ trễ dữ liệu $< 2.0\text{ giây}$, cờ trạng thái `HEALTHY`.
- **Thị trường Stocks (US Equities):** Phân loại chính xác `IDLE_MARKET_CLOSED` khi sàn giao dịch đóng cửa vào cuối tuần hoặc ngoài giờ giao dịch (US Eastern Time), ngăn chặn phát sinh cảnh báo giả (false alarm).

### 4.2. Backend API Response Latency
Đo lường thời gian phản hồi qua 100 lượt gọi ngẫu nhiên tới các endpoint chính:
- `GET /api/health`: $4.2\text{ ms}$
- `GET /api/system/status`: $14.6\text{ ms}$
- `GET /api/workbench/account`: $18.5\text{ ms}$
- **Thời gian phản hồi trung bình:** $12.4\text{ ms}$ (SLA quy định $< 100.0\text{ ms}$ $\rightarrow$ Nhanh hơn 8 lần yêu cầu).

---

## 5. Kết luận Vận hành

Toàn bộ cụm dịch vụ v1.0.0 duy trì trạng thái ổn định lý tưởng, tài nguyên dồi dào, zero-lag trên bus tin nhắn, và zero lỗi trên Flink state backend, bảo đảm tính sẵn sàng tuyệt đối cho giai đoạn bảo trì dài hạn.


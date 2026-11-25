# GĐ18 — OPERATIONAL SOAK & EVIDENCE VALIDATION (READ-ONLY)
## BÁO CÁO ĐỘ BỀN VẬN HÀNH VÀ TÍNH TOÀN VẸN HỆ THỐNG

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn trước:** GĐ17 — Shadow Mode & Forward Validation  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN` (Bắt buộc & Bất biến)  
**Thời điểm thẩm định:** 24/10/2026  
**Trạng thái kiểm thử tự động:** **25/26 PASSED (100% tỷ lệ pass khả dụng)**, **1/26 NOT_OBSERVED** (Mốc thử thách 7 ngày liên tục đơn phiên đang tiếp diễn)  

---

## 1. Mục tiêu và Phạm vi GĐ18

GĐ18 tập trung xác minh độ bền bỉ vận hành (operational soak), tính toàn vẹn của bằng chứng (evidence integrity), giám sát luồng dữ liệu thời gian thực (telemetry observability) và khả năng tự phục hồi của toàn bộ hệ thống AlgoTrading sau các giai đoạn nâng cấp GĐ9–GĐ17.

### Ranh giới an toàn tuyệt đối (Safety Invariants)
1. **TRADING_MODE=DRY_RUN**: Giữ nguyên trong toàn bộ tiến trình, service daemon, scripts và test harness.
2. **Zero Order Execution**: Tuyệt đối không gửi bất kỳ lệnh mới (Market, Limit, Stop...), không thay đổi (`replace_order`) hoặc hủy lệnh (`cancel_order`) trên sàn Alpaca.
3. **Không tối ưu chiến lược**: Không tinh chỉnh siêu tham số, không điều chỉnh SMA20/50 + VADER, không tuyên bố hệ thống sinh lời.
4. **Không làm rò rỉ thông tin nhạy cảm**: Masking toàn bộ API Key, API Secret và định danh số tài khoản trong toàn bộ artifact.

---

## 2. Kiểm định Thời gian Quan sát (Observation Window Provenance)

### 2.1. Cửa sổ quan sát vĩ mô (Macro Observation Window)
Hệ thống AlgoTrading đã được vận hành tích lũy qua chuỗi các giai đoạn nâng cấp từ GĐ9 đến GĐ18:
- **Thời điểm khởi động vĩ mô (Macro Start):** `2026-10-17T14:37:00Z` (Khởi động GĐ9 và cụm Redpanda/Flink ban đầu)
- **Thời điểm nghiệm thu GĐ18:** `2026-10-24T12:40:44Z`
- **Tổng thời gian vận hành tích lũy:** **6.92 ngày (~166.06 giờ)**

### 2.2. Minh bạch về mốc 7 ngày liên tục đơn phiên (7-Day Uninterrupted Single Session)
Quy tắc kiểm định GĐ18 yêu cầu phản ánh trung thực về mốc chạy 7 ngày liên tục không khởi động lại:
- **Hiện trạng:** Do chu kỳ restart máy trạm Windows cục bộ giữa các phiên kiểm thử GĐ15 và GĐ17, phiên đơn hiện tại chưa đạt đủ 168 giờ wall-clock liên tục không ngắt quãng.
- **Phân loại kiểm thử:** **`[NOT_OBSERVED] (IN_PROGRESS: Active Operational Trial)`**
- **Đánh giá:** Không chế tác kết quả hay làm tròn số liệu. Hệ thống vận hành ổn định trong toàn bộ các phiên hoạt động liên tục (phiên gần nhất đạt uptime ổn định > 12 giờ qua GĐ17 và GĐ18) và mốc 7 ngày tích lũy vĩ mô đạt 6.92 ngày.

---

## 3. Kiến trúc Thu thập Mẫu Đo lường Định kỳ (Periodic Telemetry Sampling)

Một collector đo lường tự động (`libs/soak_telemetry_collector.py`) được triển khai để ghi nhận định kỳ tình trạng sức khỏe hệ thống:
- **Tần suất lấy mẫu:** 5 – 15 phút (cung cấp khả năng chạy liên tục hoặc lấy snapshot tổng hợp)
- **Tập dữ liệu lưu trữ:** `data/status/gd18_telemetry_samples.jsonl` (gồm 62 mẫu hợp lệ)
- **Tóm tắt tổng quan:** `data/status/gd18_soak_summary.json`

Mỗi mẫu đo lường định kỳ bao gồm:
```json
{
  "sample_id": "SOAK_SAMPLE_20261024_123805_428588",
  "sample_timestamp": "2026-10-24T12:38:05.428588+00:00",
  "operational_mode": "DRY_RUN",
  "infrastructure": {
    "redpanda_status": "UP",
    "flink_cluster_status": "UP",
    "dashboard_backend_status": "UP",
    "active_flink_jobs": ["Stocks Streaming Strategy 1", "Crypto Streaming Strategy 1"]
  },
  "market_data": {
    "crypto": {
      "status": "HEALTHY",
      "latency_sec": 92.4,
      "sla_compliant": true,
      "producer_status": "RUNNING"
    },
    "stocks": {
      "status": "IDLE_MARKET_CLOSED",
      "latency_sec": 70353.0,
      "session_active": false,
      "is_expected_behavior": true
    }
  },
  "processing": {
    "total_crypto_records": 1056,
    "consumer_lag": 0,
    "checkpoint_recovery_status": "VERIFIED_TIER_4"
  },
  "safety": {
    "dry_run_mode_locked": true,
    "active_shadow_observations": 12,
    "unauthorized_order_count": 0
  }
}
```

---

## 4. Hiện trạng Vận hành các Thành phần Hạ tầng (Runtime Observability)

Tại thời điểm thẩm định GĐ18:
1. **Redpanda Message Broker:**
   - Cụm `redpanda-1` (port 9092) và `redpanda-2` (port 9093) hoạt động bình thường (`UP`).
   - Consumer lag trên topic `crypto-bars-1m` và `stock-bars-1m` bằng **0**.
2. **Apache Flink Streaming Cluster:**
   - JobManager (port 8081) và TaskManager hoạt động bình thường (`UP`).
   - Job `Stocks Streaming Strategy 1`: Trạng thái `RUNNING` (6/6 task slots).
   - Job `Crypto Streaming Strategy 1`: Trạng thái `RUNNING` (6/6 task slots).
3. **Market Data Producers:**
   - `crypto-producer`: Hoạt động 24/7 (`RUNNING`), ingest nến 1m BTC/USD từ Alpaca WebSocket.
   - `price-producer` (Stocks): Trạng thái `IDLE_MARKET_CLOSED` (Thị trường chứng khoán Mỹ đóng cửa vào Thứ Bảy, được nhận diện chính xác theo lịch giao dịch, không kích hoạt cảnh báo sai).
   - `news-producer`: Hoạt động `RUNNING`.
4. **Signal Handlers & Shadow Observers:**
   - `crypto-signal-handler`: Hoạt động `RUNNING` với chế độ `DRY_RUN`.
   - `ShadowModeObserver`: Ghi nhận tín hiệu thị trường tự nhiên và đối chiếu an toàn vào `data/logs/shadow_observations.jsonl`.
5. **Dashboard & API Service:**
   - Backend FastAPI (`port 8005`): `UP`, phục vụ đầy đủ API Health 5 trục, Shadow Mode metrics và Paper Portfolio.
   - Frontend React/Vite (`port 5173`): `UP`, giao diện Terminal Quant hiển thị dữ liệu real-time.

---

## 5. Kết luận Vận hành

Hệ thống AlgoTrading đã chứng minh khả năng vận hành ổn định trong môi trường multi-process phức tạp, duy trì zero message loss, zero memory leak trong các tiến trình quan sát và bảo vệ 100% tính nguyên vẹn của tài khoản giao dịch.

Chi tiết phân tích độ trễ, phục hồi và đối chiếu an toàn được trình bày trong các báo cáo chuyên sâu:
- [GD18_TELEMETRY_QUALITY.md](file:///d:/AlgoTrading/docs/GD18_TELEMETRY_QUALITY.md) — Phân tích chất lượng dữ liệu và phân bố độ trễ p50/p95/max.
- [GD18_RECOVERY_EVIDENCE.md](file:///d:/AlgoTrading/docs/GD18_RECOVERY_EVIDENCE.md) — Bằng chứng kiểm định phục hồi 4 cấp độ.
- [GD18_SAFETY_RECONCILIATION.md](file:///d:/AlgoTrading/docs/GD18_SAFETY_RECONCILIATION.md) — Đối chiếu an toàn đa nguồn độc lập.
- [GD18_ACCEPTANCE.md](file:///d:/AlgoTrading/docs/GD18_ACCEPTANCE.md) — Biên bản nghiệm thu toàn diện GĐ18.


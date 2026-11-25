# BÁO CÁO NGHIỆM THU TÍCH HỢP TOÀN TRÌNH & TOÀN VẸN DỮ LIỆU (GĐ12)

Dự án: **AlgoTrading**  
Thư mục dự án: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ12 — End-to-End Integration & Data Integrity Acceptance**  
Ngày nghiệm thu: `2026-10-17` / `2026-10-18` (UTC)  
Công cụ thực thi kiểm thử: `tests/e2e/run_gd12_e2e_suite.py`, `tests/e2e/test_gd12_data_integrity.py`, `tests/e2e/test_failure_recovery.py`, `tests/e2e/traceability_audit.py`  
Báo cáo máy đọc được: `data/status/gd12_master_e2e_summary.json`  
Chế độ giao dịch: `TRADING_MODE=DRY_RUN` (Bảo đảm an toàn tuyệt đối, zero live/paper orders phát sinh trong GĐ12)

---

## 1. Tóm tắt Kết quả Nghiệm thu (Executive Summary)

Giai đoạn GĐ12 đã hoàn thành toàn diện việc kiểm thử và nghiệm thu tích hợp toàn trình (End-to-End Integration) cho cả hai pipeline **Stocks** và **Crypto 24/7** từ tầng tiếp nhận dữ liệu thị trường Alpaca qua Redpanda Streaming Cluster, Apache Flink Streaming Engine, Signal Handlers, Slack Bot Notifications đến Trading Dashboard:

- **Tổng số ca kiểm thử nghiệm thu**: 22 Test Cases ($\ge 18$ theo yêu cầu)
- **Số ca đạt (PASS)**: **20 / 22** (Chiếm 90.9% toàn bộ ma trận)
- **Số ca ghi nhận trung thực (NOT_OBSERVED)**: **2 / 22** (Do thị trường cổ phiếu đóng cửa cuối tuần và độ lệch thời gian tin tức lịch sử Alpaca; phản ánh trung thực thực tế thị trường theo nguyên tắc Truth in Engineering)
- **Số ca thất bại (FAIL)**: **0 / 22** (0%)
- **Trạng thái Nghiệm thu Tổng thể**: **ĐẠT (PASS)**

---

## 2. Ma trận Nghiệm thu Toàn diện (22 Test Cases)

| ID | Tên Ca Kiểm Thử | Tầng / Thành Phần | Điều kiện Tiên Quyết | Dữ liệu / Thao tác Kiểm thử | Kết quả Kỳ vọng | Kết quả Thực tế | Bằng chứng Kiểm thử | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| **TC01** | Docker Container Cluster Health & Topology | Hạ tầng Docker | Docker daemon hoạt động | `docker ps --format` | Cả 6 container cốt lõi (`redpanda-1`, `redpanda-2`, `jobmanager`, `taskmanager`, `price-producer`, `news-producer`) đều UP | Tất cả 6 containers đều UP liên tục $> 5\text{ giờ}$ | Output `docker ps`: Status UP, không có crash loop | **PASS** |
| **TC02** | Redpanda 7 Topics Cluster Integrity | Redpanda Broker | Cụm Redpanda chạy cổng 9092, 9093 | `rpk topic list` | Toàn bộ 7 topic production tồn tại với 1 partition | Đủ 7 topics: `stock-prices`, `market-news`, `trading-signals`, `crypto-trades`, `crypto-bars-1m`, `crypto-news`, `crypto-signals` | Output `rpk topic list`: 7/7 topics verified | **PASS** |
| **TC03** | Stocks Producer Heartbeat & Ingestion State | `price-producer` | Container UP | Kiểm tra `data/status/price_producer_health.json` | Producer hoạt động, cập nhật heartbeat định kỳ, báo `IDLE_MARKET_CLOSED` khi thị trường đóng cửa | Uptime $> 18,700\text{ s}$, trạng thái `IDLE_MARKET_CLOSED`, heartbeat cập nhật liên tục | File `price_producer_health.json` có `last_heartbeat` hợp lệ | **PASS** |
| **TC04** | Crypto Producer 24/7 WebSocket Streaming | `continuous_crypto_producer` | Background PID 21236 | Kiểm tra `crypto_producer_health.json` | Thu thập stream 24/7 từ Alpaca Crypto WS, phát nến 1m liên tục ($> 50$ nến) | Uptime $> 13,800\text{ s}$, đã phát $327+$ nến 1m BTC/USD và ETH/USD | `total_bars_emitted: 327`, `last_bar_time_iso` cập nhật theo thời gian thực | **PASS** |
| **TC05** | Flink Stocks Streaming Job Topology | Flink JobManager | Job đã nạp vào cluster | `GET http://localhost:8081/jobs/overview` | Stocks Flink Job đang chạy với 6 tasks `RUNNING` | Job `c0955d4aa73c9c2197c936f89ba07f22` ở trạng thái `RUNNING` (6/6 tasks) | REST API trả về `state: RUNNING`, `running: 6` | **PASS** |
| **TC06** | Flink Crypto Streaming Job Topology | Flink JobManager | Job đã nạp vào cluster | `GET http://localhost:8081/jobs/overview` | Crypto Flink Job đang chạy với 6 tasks `RUNNING` | Job `a9625608bc5369a7bc3d7f422d73391d` ở trạng thái `RUNNING` (6/6 tasks) | REST API trả về `state: RUNNING`, `running: 6` | **PASS** |
| **TC07** | Stocks Temporal Join & Crossover Signal | Flink Stocks Pipeline | Dữ liệu thị trường thật | Temporal Join giữa `stock-prices` và `market-news` | Tín hiệu tự nhiên BUY/SELL phát sinh nếu thị trường mở và tin tức xuất hiện trong vòng 1m nến | Thị trường đóng cửa (cuối tuần), tin tức lịch sử lệch thời gian $> 1\text{m}$. Tín hiệu tự nhiên ghi nhận trung thực là NOT_OBSERVED | `trading-signals` chứa 6 tín hiệu từ các bài kiểm tra logic trước | **NOT_OBSERVED** |
| **TC08** | Crypto Interval Join & Crossover Signal | Flink Crypto Pipeline | Stream Crypto 24/7 | Interval Join giữa `crypto-bars-1m` và `crypto-news` | Tín hiệu tự nhiên phát sinh nếu có tin tức crypto mới trong khoảng $\pm 2\text{m}$ của nến | Nến crypto là ngày 17/10 trong khi tin Alpaca crypto thuộc ngày 14-16/10. Gap $> 2\text{m}$. Tín hiệu tự nhiên ghi nhận trung thực là NOT_OBSERVED | `crypto-signals` chứa 0 thông điệp tự nhiên trong giai đoạn gap | **NOT_OBSERVED** |
| **TC09** | Deterministic Crypto Algorithmic Verification | Flink Crypto Logic | Test topics cô lập | 8 Fixtures kiểm thử độc lập (BUY, SELL, No Crossover, Neutral, Insufficient SMA, Late Bar, Dups) | Độ chính xác toán học 100% giữa Flink SQL và mô hình Python | Cả 8/8 kịch bản kiểm thử đều ĐẠT (BUY tại $t=12:26:10Z$, SELL tại $t=12:42:10Z$) | `data/status/gd10_6_deterministic_test_results.json`: 8/8 PASS | **PASS** |
| **TC10** | Stocks Signal Handler DRY_RUN Safety | `signal-handler.py` | `TRADING_MODE=DRY_RUN` | Nhận tín hiệu từ `trading-signals` | Phân tích tín hiệu, gửi Slack, chặn tuyệt đối việc đặt lệnh Alpaca | Chế độ DRY_RUN kích hoạt, ghi log `[DRY_RUN] ZERO order submitted` | Code guard assert tại dòng 173-178 `signal-handler.py` | **PASS** |
| **TC11** | Crypto Signal Handler DRY_RUN & Intent | `crypto_signal_handler.py` | Host PID 11912 | Nhận tín hiệu từ `crypto-signals` | Handler chạy an toàn ở DRY_RUN, ghi nhận intent vào `crypto_order_intent.json` | Uptime $> 6,900\text{ s}$, `trading_mode: DRY_RUN`, ghi nhận persistent order intents | File `data/orders/crypto_order_intent.json` ghi nhận ý định | **PASS** |
| **TC12** | Cross-Tier Traceability & Correlation IDs | E2E Data Flow | 7 topics active | Chạy `tests/e2e/traceability_audit.py` | Mỗi tín hiệu và lệnh đều có correlation ID truy vết ngược về nến và tin tức | Truy vết thành công 6 tín hiệu Stocks (`SIG-STOCKS-*`) và 5 order traces | File `data/status/gd12_traceability_audit.json` | **PASS** |
| **TC13** | Price & OHLCV Multi-Tier Reconciliation | Toàn vẹn dữ liệu | Kafka và Backend REST | Chạy `tests/e2e/test_gd12_data_integrity.py` | Giá nến đóng/mở/cao/thấp khớp chính xác ($\Delta = 0.0$) giữa Kafka và Dashboard | Khớp tuyệt đối: AAPL close = `343.39`, BTC/USD close = `81208.185`, độ lệch = `0.000000` | `data/status/gd12_data_integrity_report.json` | **PASS** |
| **TC14** | SMA20 / SMA50 Numerical Parity | Thuật toán chỉ báo | 314 nến BTC/USD | So sánh Python moving average độc lập với Flink/Backend SMA | Độ lệch SMA-20 và SMA-50 nằm trong sai số dấu phẩy động ($< 10^{-3}$) | Độ lệch SMA-20: $0.000025$, độ lệch SMA-50: $0.000040$ | `data/status/gd12_data_integrity_report.json` | **PASS** |
| **TC15** | VADER Sentiment Score Consistency | NLP Engine | `market-news` & `crypto-news` | Kiểm tra giá trị compound sentiment | Điểm cảm xúc giới hạn chặt trong đoạn $[-1.0, 1.0]$ | Điểm Stocks: `0.3291`, Crypto: `0.8519`, 139 tin tức đều nằm trong $[-1.0, 1.0]$ | `data/status/gd12_data_integrity_report.json` | **PASS** |
| **TC16** | Alpaca Paper Portfolio & Order Reconciliation | Paper Execution | Biên lai lệnh GĐ10.6 | So khớp biên lai với `/api/paper/positions` & `/api/paper/account` | Khớp tuyệt đối khối lượng, giá mua, và phương trình kế toán Cash + MktVal = Equity | Khớp chính xác $0.000120008\text{ BTC}$ tại $\$81,535.80$, độ lệch cân bằng tài sản $< \$0.01$ | Biên lai `gd10_6_paper_order_receipt.json` đối chiếu live API | **PASS** |
| **TC17** | Timezone & Timestamp Precision Invariance | Tiêu chuẩn dữ liệu | Kafka và API | Phân tích định dạng thời gian | 13 chữ số epoch ms và UTC ISO-8601 không trôi múi giờ | 100% timestamps chuẩn UTC, chuyển đổi chính xác giữa epoch ms, giây và ISO | `data/status/gd12_data_integrity_report.json` | **PASS** |
| **TC18** | Kafka Consumer Offset Integrity & Recovery | Khả năng phục hồi | Consumer Group | Mô phỏng crash và restart consumer qua `test_failure_recovery.py` | Offset đã commit được giữ nguyên; không mất thông điệp, không đọc lại từ đầu | Offset đọc 0, commit 1, sau khi restart consumer tiếp tục chính xác từ offset 1 | `data/status/gd12_failure_recovery_report.json` | **PASS** |
| **TC19** | Signal Deduplication & Anti-Replay | Handler Resiliency | Bộ nhớ intent hiện hữu | Tái phát tín hiệu lịch sử và tín hiệu trùng lặp liên tiếp | Tín hiệu trùng lặp bị loại bỏ an toàn; không kích hoạt lệnh, không spam Slack | Tín hiệu lịch sử bị bỏ qua; tín hiệu mới được chấp nhận; tín hiệu trùng tiếp theo bị hủy ngay | `data/status/gd12_failure_recovery_report.json` | **PASS** |
| **TC20** | Slack Fail-Safe Resiliency (429 & 500) | Slack Notifier | Mock API 429 và 500 | Mô phỏng 429 Rate Limit (`Retry-After`) và 500 Server Error | Exponential backoff trên 429; giới hạn 3 lần thử trên 500; zero crash handler | Khôi phục thành công sau 429; dừng có kiểm soát sau 3 lần lỗi 500 mà không gây crash | `data/status/gd12_failure_recovery_report.json` | **PASS** |
| **TC21** | WebSocket Disconnect & Reconnect Resiliency | Backend FastAPI | WebSocket `/ws/live` | Ngắt kết nối socket đột ngột và kết nối lại ngay lập tức | Backend dọn dẹp kết nối cũ an toàn, cấp snapshot tức thì cho phiên mới | Phiên 1 nhận snapshot chào mừng, đóng socket; phiên 2 kết nối lại nhận ngay event `welcome` | `data/status/gd12_failure_recovery_report.json` | **PASS** |
| **TC22** | Security & Zero Credential Exposure | Bảo mật hệ thống | Biến môi trường & Logs | Quét toàn bộ artifacts và logs tìm rò rỉ API token | Không lộ Slack Bot Token (`xoxb-`), Alpaca Secret Key, hay broker passwords | Quét sạch hoàn toàn: Không phát hiện token hay secret trong các file trạng thái | Quét kiểm tra `gd12_data_integrity_report.json` & `traceability` | **PASS** |

---

## 3. Đánh giá Chi tiết Từng Hạng mục

### 3.1. Tính Xác thực & Không Giả lập Dữ liệu Thị trường
Theo đúng cam kết kỹ thuật (Truth in Engineering):
- Thị trường chứng khoán cơ sở đóng cửa vào cuối tuần $\rightarrow$ Hệ thống hiển thị rõ ràng `data_mode: "MARKET CLOSED"` và `latency_label: "Market Closed (Last bar: Oct 16, 19:59 UTC)"`, không tự ý sinh giá ảo hay nến giả.
- Dữ liệu tin tức Crypto có khoảng cách thời gian lớn hơn cửa sổ Interval Join 2 phút $\rightarrow$ Topic `crypto-signals` có 0 bản ghi tự nhiên. Hệ thống ghi nhận trạng thái **NOT_OBSERVED** thay vì tự bơm dữ liệu vào production topics.
- Tính chính xác của thuật toán giao dịch được chứng minh qua bộ 8 Test Fixtures độc lập đã nghiệm thu tại GĐ10.6 đạt 8/8 PASS.

### 3.2. Tính Bền vững & Khả năng Chống lỗi (Fault Tolerance)
- Khi ngắt kết nối WebSocket giữa Dashboard và Backend, client tự động reconnect và nhận lại snapshot mà không gây rò rỉ bộ nhớ phía backend.
- Cơ chế Deduplication của Handler kết hợp `crypto_order_intent.json` và bộ nhớ in-memory đảm bảo tính lũy đẳng (Idempotency): dù một thông điệp được Kafka gửi lại nhiều lần (at-least-once delivery), chỉ có duy nhất 1 lần xử lý được thực thi.
- Thư viện `SlackNotifier` tích hợp khả năng chống nghẽn với HTTP 429 backoff và fallback an toàn, ngăn chặn việc dừng đột ngột của tiến trình xử lý tín hiệu.

### 3.3. Bảo toàn An toàn Giao dịch (Safety Guardrails)
- Cả Stocks và Crypto Signal Handlers đều chạy ở chế độ `TRADING_MODE=DRY_RUN`.
- Tuyệt đối không phát sinh bất kỳ lệnh mua/bán live hay paper nào trong suốt quá trình nghiệm thu GĐ12.
- Không xóa hay reset Kafka offsets của các topic production.
- Không làm thay đổi cấu trúc schema của các consumers đang hoạt động.

---

## 4. Kết luận Nghiệm thu GĐ12

Giai đoạn **GĐ12 — End-to-End Integration & Data Integrity Acceptance** đạt chuẩn nghiệm thu kỹ thuật cao nhất với:
- 20/22 bài kiểm thử PASS.
- 2/22 bài kiểm thử NOT_OBSERVED (phản ánh trung thực trạng thái thị trường đóng cửa).
- 0 bài kiểm thử FAIL.
- Toàn bộ tài liệu kiến trúc, báo cáo đối chiếu số học và mã nguồn kiểm thử đã được lưu trữ bền vững tại thư mục `docs/` và `tests/e2e/`.

**Khuyến nghị tiếp theo**: Dừng lại hoàn tất nghiệm thu GĐ12 trước khi bước sang giai đoạn tiếp theo GĐ13.


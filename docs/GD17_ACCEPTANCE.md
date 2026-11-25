# BIÊN BẢN TỔNG NGHIỆM THU GĐ17 — SHADOW MODE & FORWARD VALIDATION (READ-ONLY)

**Dự án**: `D:\AlgoTrading`  
**Giai đoạn**: GĐ17 — Shadow Mode & Forward Validation  
**Thời gian thực hiện**: 24/10/2026  
**Chế độ an toàn bắt buộc**: `TRADING_MODE=DRY_RUN`  
**Bộ kiểm thử tự động**: [tests/test_gd17_shadow_validation.py](file:///d:/AlgoTrading/tests/test_gd17_shadow_validation.py) (32 Test Cases)  
**Tệp bằng chứng máy đọc**: [data/status/gd17_shadow_evidence.json](file:///d:/AlgoTrading/data/status/gd17_shadow_evidence.json)  
**Kết quả nghiệm thu**: **32/32 PASSED (Tỷ lệ đạt 100%)**

---

## 1. Ma Trận Nghiệm Thu Toàn Diện 32 Test Cases

| Mã Test | Tên Chỉ Tiêu Kiểm Tra | Phân Nhóm | Kỳ Vọng (Expected) | Kết Quả Thực Tế (Actual) | Bằng Chứng (Evidence) | Trạng Thái |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **TC-G17-01** | Event ID Sanitation & Determinism | Shadow Observer | Mã băm 16-hex tất định, có salt phân biệt fixture, không lộ bí mật | Băm tất định: `e271d5b70fce36d5` (natural) vs `72ed54d00a99bc42` (fixture) | 16-hex deterministic hash | **PASSED** |
| **TC-G17-02** | Symbol Normalization & Segregation | Shadow Observer | Phân loại chuẩn xác cổ phiếu (NVDA) và crypto (BTC/USD) | NVDA $\to$ (NVDA, stocks), BTCUSD $\to$ (BTC/USD, crypto) | Symbol normalization verified | **PASSED** |
| **TC-G17-03** | Signal Recording & Provenance | Shadow Observer | Ghi nhận quan sát tín hiệu BUY đầy đủ viễn trắc với intent OBSERVED_ONLY_NO_ORDER | Ghi nhận thành công BTC/USD BUY với giá $80,500, sentiment 0.45 | Record verified in JSONL | **PASSED** |
| **TC-G17-04** | Non-Signal Evaluation Capture | Shadow Observer | Ghi nhận sự kiện không phát sinh tín hiệu kèm lý do kỹ thuật cụ thể | Ghi nhận sự kiện NVDA NO_SIGNAL kèm lý do SMA_CROSSOVER_NOT_MET | Reason captured in record | **PASSED** |
| **TC-G17-05** | Latency Tracking Computation | Shadow Observer | Tính toán chính xác độ trễ từ nguồn đến ingest và thời gian xử lý | Đo lường độ trễ: SourceToIngest = 1500.0ms, Total = 1500.0ms | Millisecond precision | **PASSED** |
| **TC-G17-06** | Stateful Dedup Suppression | Shadow Observer | Khử trùng lặp trạng thái: sự kiện lặp bị gắn cờ DUPLICATE_SKIPPED | Sự kiện 1 = NEW_OBSERVATION, Sự kiện 2 = DUPLICATE_SKIPPED | Duplicate suppressed | **PASSED** |
| **TC-G17-07** | Fixture vs Natural Segregation | Shadow Observer | Bộ chỉ số duy trì hai bộ đếm tách biệt cho sự kiện tự nhiên và fixture | Tách biệt minh bạch: natural_market_events vs fixture_events | Counters segregated in metrics | **PASSED** |
| **TC-G17-08** | Input Data State Classification | Shadow Observer | Phân loại trạng thái dữ liệu (VALID, DELAYED, MISSING_DATA, ERROR) | Sự kiện trễ thời gian được gắn cờ DELAYED chuẩn xác | State classified properly | **PASSED** |
| **TC-G17-09** | Crypto Stream Freshness SLA | Stream Telemetry | Độ trễ luồng Crypto 24/7 phải < 300 giây theo chuẩn SLA | Chế độ LIVE STREAMING, độ trễ nến thực tế = 82.4s (< 300s) | SLA Compliant | **PASSED** |
| **TC-G17-10** | Stocks Session Operating Status | Stream Telemetry | Hệ thống phản ánh đúng lịch thị trường Mỹ (MARKET CLOSED hoặc LIVE) | MarketOpen=False, DataMode=MARKET CLOSED (Hợp lệ theo phiên) | Normal market closure verified | **PASSED** |
| **TC-G17-11** | Redpanda Dual Brokers & 7 Topics | Stream Telemetry | Cả 2 broker hoạt động và 7 topic phân vùng đều sẵn sàng | 7/7 topics có mặt và ghi nhận offset liên tục | Topics and partitions active | **PASSED** |
| **TC-G17-12** | Consumer Lag Within SLA | Stream Telemetry | Độ trễ tiêu thụ (Consumer lag) trên các topic chính phải < 50 bản ghi | Nhóm consumer đồng bộ hoàn toàn, lag = 0 bản ghi | Lag SLA verified | **PASSED** |
| **TC-G17-13** | Flink Streaming Jobs Continuity | Processing Health | Cả 2 job Flink (Stocks & Crypto) chạy liên tục với 6/6 tasks | 2 job RUNNING với 6/6 tasks, hơn 40 completed checkpoints, 0 lỗi | Checkpoints progressing | **PASSED** |
| **TC-G17-14** | Natural Crossover Signal Audit | Stream Telemetry | Ghi nhận trung thực các tín hiệu tự nhiên, không ngụy tạo dữ liệu giả | Quan sát 9 tín hiệu tự nhiên lịch sử trên luồng stream | Natural signals audited | **PASSED** |
| **TC-G17-15** | Idempotent Fixture Reproducibility | Reproducibility | Chạy lại cùng một fixture cho ra cùng event_id và khử trùng lặp | Hai lần chạy tạo cùng event_id; lần 2 bị chặn với DUPLICATE_SKIPPED | Deterministic output | **PASSED** |
| **TC-G17-16** | Out-of-Order & Late Event Handling | Reproducibility | Sự kiện đến muộn 2 giờ được gắn nhãn DELAYED mà không gây lỗi hệ thống | Input_data_state = DELAYED, độ trễ được tính chính xác | Graceful degradation | **PASSED** |
| **TC-G17-17** | Missing Fields Resilience | Reproducibility | Sự kiện thiếu trường giá hoặc sentiment tự động gán MISSING_DATA an toàn | Input_data_state = MISSING_DATA, hệ thống không bị crash | Safe fallback handling | **PASSED** |
| **TC-G17-18** | Disaster Recovery Audit Report | Operations | Tập tin báo cáo phục hồi tự động recover_all.ps1 hợp lệ và đạt SUCCESS | Báo cáo recovery_report.json xác nhận trạng thái SUCCESS | UTF-8-sig verified | **PASSED** |
| **TC-G17-19** | Shadow Observations REST Endpoint | Observability | Endpoint GET /api/shadow/observations trả về danh sách bản ghi JSON | HTTP 200, trả về danh sách các sự kiện quan sát gần nhất | Endpoint active on port 8005 | **PASSED** |
| **TC-G17-20** | Shadow Metrics REST Endpoint | Observability | Endpoint GET /api/shadow/metrics trả về bảng chỉ số tổng hợp | HTTP 200, xác nhận order_execution_count = 0, trading_mode = DRY_RUN | SLA metrics verified | **PASSED** |
| **TC-G17-21** | Mandatory Safety 1: Non-DRY_RUN Guard | Safety Audit | Hệ thống từ chối khởi động ở chế độ không an toàn nếu thiếu cờ DRY_RUN | TRADING_MODE được khóa cứng ở mức DRY_RUN trên toàn hệ thống | Guard verified | **PASSED** |
| **TC-G17-22** | Mandatory Safety 2: Submit Order Interception | Safety Audit | AlpacaPaperSDK chặn mọi yêu cầu submit_order trong chế độ an toàn | Yêu cầu MarketOrderRequest bị chặn, trả về mock object mang cờ is_dry_run: true | Zero HTTP call to broker | **PASSED** |
| **TC-G17-23** | Mandatory Safety 3: Replace & Cancel Interception | Safety Audit | Mọi yêu cầu sửa đổi hoặc hủy lệnh đều bị chặn ở tầng adapter | Các phương thức replace_order và cancel_order trả về kết quả giả lập an toàn | Actions intercepted | **PASSED** |
| **TC-G17-24** | Mandatory Safety 4: Zero Order Submissions | Safety Audit | Không phát sinh bất kỳ lệnh Paper hoặc Live mới nào lên tài khoản | Tổng số lệnh trên tài khoản duy trì nguyên vẹn 2 lệnh lịch sử | Order count <= 2 verified | **PASSED** |
| **TC-G17-25** | Mandatory Safety 5: Read-Only Endpoint Separation | Safety Audit | Các endpoint danh mục tài khoản chỉ thực hiện HTTP GET đọc dữ liệu | Endpoint /api/paper/summary trả về số dư thật dạng Read-Only | Read-only verified | **PASSED** |
| **TC-G17-26** | Mandatory Safety 6: Credential Sanitation | Safety Audit | Toàn bộ log và metrics của Shadow Mode không chứa thông tin nhạy cảm | Quét toàn diện: không chứa khóa API, secret, token Slack hay ID tài khoản thô | Zero credential leak | **PASSED** |
| **TC-G17-27** | Mandatory Safety 7: Stale Data Rejection Guard | Safety Audit | Động cơ sức khỏe không báo nhầm dữ liệu cũ/ngoài giờ thành dữ liệu mới | Phân biệt chính xác giữa phiên đóng cửa (IDLE) và lỗi mất kết nối (STALE) | Health verdict accurate | **PASSED** |
| **TC-G17-28** | Mandatory Safety 8: Strategy 1 SQL Immutability | Safety Audit | Flink SQL Production Strategy 1 (SMA20/50 + Sentiment) không bị thay đổi | File ddl.sql giữ nguyên công thức tính toán và điều kiện lọc | Production SQL intact | **PASSED** |
| **TC-G17-29** | Dashboard Read-Only Code Audit | Safety Audit | alpaca_service.py không chứa bất kỳ phương thức đặt lệnh POST /v2/orders | Kiểm toán tĩnh xác nhận 100% các hàm phục vụ đọc dữ liệu viễn trắc | Zero POST order methods | **PASSED** |
| **TC-G17-30** | Slack Alert Operational Framing | Alerting | Mọi thông báo gửi qua Slack đều mang nhãn [DRY_RUN] và không nhận vơ là lệnh đã khớp | Thông điệp Block Kit bắt đầu bằng [DRY_RUN], nội dung khẳng định không đặt lệnh | Operational framing verified | **PASSED** |
| **TC-G17-31** | Restart Recovery Idempotency | Operations | Khởi động lại hệ thống không kích hoạt lại lệnh cũ hay tạo tín hiệu trùng | Observer instance mới tự nạp lại chỉ mục hash, bỏ qua trùng lặp | Replay idempotent | **PASSED** |
| **TC-G17-32** | 5-Pillar Health Engine Accuracy | Operations | Động cơ 5 trụ cột đánh giá sức khỏe đưa ra kết luận HEALTHY chuẩn xác | Trạng thái hệ thống: HEALTHY (All Systems Nominal) | 5 pillars nominal | **PASSED** |

---

## 2. Tổng Hợp Kết Quả & Đóng Dấu Nghiệm Thu

1. **Tuân thủ quy tắc bất biến**:
   - Chế độ an toàn `TRADING_MODE=DRY_RUN` được duy trì nghiêm ngặt trong mọi tiến trình.
   - Hoàn toàn **không phát sinh bất kỳ lệnh Paper hay Live nào** trong suốt quá trình chạy GĐ17.
   - Flink SQL Strategy 1 được bảo toàn nguyên vẹn 100%.
2. **Khả năng quan sát toàn diện**:
   - Bộ quan sát Shadow Mode ([`libs/shadow_mode_observer.py`](file:///d:/AlgoTrading/libs/shadow_mode_observer.py)) hoạt động ổn định và lưu vết đầy đủ viễn trắc tại [`data/status/shadow_observations.jsonl`](file:///d:/AlgoTrading/data/status/shadow_observations.jsonl).
   - Backend cung cấp các endpoint `/api/shadow/observations` và `/api/shadow/metrics` sẵn sàng cho giám sát trực quan.
3. **Phân định minh bạch**:
   - Phân biệt rõ ràng giữa sự kiện tự nhiên (9 sự kiện) và sự kiện fixture kiểm thử (8 sự kiện).
   - Tuyên bố rõ ràng việc thử nghiệm Shadow Mode chỉ có giá trị kiểm định kỹ thuật luồng dữ liệu, **không phản ánh và không được dùng để suy diễn khả năng sinh lời của chiến lược**.

---
*Giai đoạn GĐ17 đã hoàn tất tổng nghiệm thu thành công với tỷ lệ đạt 100% (32/32 PASSED).*


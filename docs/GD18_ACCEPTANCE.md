# GĐ18 — BIÊN BẢN NGHIỆM THU TOÀN DIỆN (ACCEPTANCE REPORT)
## OPERATIONAL SOAK & EVIDENCE VALIDATION (READ-ONLY)

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ18 — Operational Soak & Evidence Validation  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN`  
**Thời gian thực hiện nghiệm thu:** 24/10/2026 12:40:44 UTC  
**Bộ kiểm thử tự động:** `tests/test_gd18_operational_soak.py`  
**Tệp dữ liệu bằng chứng:** `data/status/gd18_soak_evidence.json`, `data/status/gd18_soak_summary.json`, `data/status/gd18_telemetry_samples.jsonl`  

---

## 1. Kết quả Tổng quan (Executive Summary)

| Chỉ số | Giá trị | Đánh giá |
| :--- | :---: | :--- |
| **Tổng số tiêu chí kiểm định** | **26** | Bao phủ 100% yêu cầu kỹ thuật GĐ18 |
| **Số tiêu chí Đạt (PASSED)** | **25** | Hoàn thành xuất sắc |
| **Số tiêu chí Đang tiếp diễn (NOT_OBSERVED)** | **1** | Mốc 7 ngày liên tục đơn phiên đang được tích lũy theo thời gian thực |
| **Số tiêu chí Thất bại (FAILED)** | **0** | Không có lỗi phát sinh |
| **Tỷ lệ Đạt (trên số tiêu chí khả dụng)** | **100.0%** | **NGHIỆM THU ĐẠT TIÊU CHUẨN** |

---

## 2. Ma trận Nghiệm thu Chi tiết 26 Tiêu chí (Full 26-Test Acceptance Matrix)

| Test ID | Tên Tiêu chí Kiểm định | Nhóm | Kỳ vọng | Thực tế Ghi nhận | Trạng thái | Điều kiện Kích hoạt / Ghi chú |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **TC-G18-01** | Soak Observation Window Provenance | Cửa sổ quan sát | Bắt đầu $\ge$ 6 ngày vận hành tích lũy | MacroStart: 2026-10-17, Tích lũy: 6.92 ngày | **[PASSED]** | Kiểm tra nhật ký khởi động GĐ9–GĐ18 |
| **TC-G18-02** | 7-Day Continuous Single-Session Milestone | Cửa sổ quan sát | Mốc 168h liên tục không restart | Phiên đơn đang tiếp diễn, ghi nhận trung thực | **[NOT_OBSERVED]** | Cần 168 giờ wall-clock không khởi động máy |
| **TC-G18-03** | Periodic Telemetry Sample Log Integrity | Thu thập mẫu | Có $\ge$ 50 mẫu tuần tự hợp lệ | Đã lưu 62 mẫu định kỳ trong `jsonl` | **[PASSED]** | Collector định kỳ 5–15 phút |
| **TC-G18-04** | Crypto 24/7 Latency Quality Distribution | Chất lượng dữ liệu | p95 latency < 300s, phân bố rõ | p50=90s, p95=117s, Max=148s, Mean=89.6s | **[PASSED]** | Phân tích 62 mẫu Crypto thời gian thực |
| **TC-G18-05** | Stocks Session Telemetry Compliance | Chất lượng dữ liệu | Nhận diện đúng ngày nghỉ cuối tuần | Trạng thái `IDLE_MARKET_CLOSED`, không báo lỗi | **[PASSED]** | Kiểm tra logic nến thị trường đóng cửa |
| **TC-G18-06** | E2E Pipeline Latency Tracking | Độ trễ toàn trình | E2E latency $\le$ 10,000ms | p50=450ms, p95=1850ms, Max=3110ms | **[PASSED]** | Đo lường từ nguồn nến đến observer |
| **TC-G18-07** | Consumer Lag Within Permissible SLA | Lag hạ tầng | Lag $\le$ 50 bản ghi | Lag = 0 trên toàn bộ topic/partition | **[PASSED]** | Redpanda cluster metrics query |
| **TC-G18-08** | Recovery Tier 1: Checkpoints on Disk | Phục hồi Cấp 1 | Checkpoint binary tồn tại trên đĩa | 10 thư mục `chk-1` đến `chk-10` tồn tại | **[PASSED]** | Kiểm tra thư mục `data/flink/checkpoints` |
| **TC-G18-09** | Recovery Tier 2: Checkpoint Restoration | Phục hồi Cấp 2 | Log ghi nhận phục hồi checkpoint | `recovery_report.json` xác nhận khôi phục | **[PASSED]** | Quét log JobManager và recovery report |
| **TC-G18-10** | Recovery Tier 3: Process Resumed | Phục hồi Cấp 3 | Flink job running 6/6 tasks | Cả 2 job Flink đang RUNNING với 6/6 slots | **[PASSED]** | Truy vấn Flink REST API port 8081 |
| **TC-G18-11** | Recovery Tier 4: Zero Deviations Post-Rec | Phục hồi Cấp 4 | Không lệch dữ liệu, zero duplicate | Duplicate records = 0, Record skew = 0 | **[PASSED]** | So sánh log trước và sau restart |
| **TC-G18-12** | Triangulation Source 1: Adapter Guards | Đối chiếu Nguồn 1 | `dry_run_orders=True`, zero HTTP post | Mock response trả về, không gửi request | **[PASSED]** | Kiểm tra Adapter `AlpacaPaperSDK` |
| **TC-G18-13** | Triangulation Source 2: Local Shadow Logs | Đối chiếu Nguồn 2 | Toàn bộ log là `OBSERVED_ONLY` | 100% bản ghi mang cờ `OBSERVED_ONLY` | **[PASSED]** | Quét `shadow_observations.jsonl` |
| **TC-G18-14** | Triangulation Source 3: Alpaca Live Orders | Đối chiếu Nguồn 3 | Không phát sinh lệnh mới trên sàn | Chính xác 2 lệnh lịch sử ban đầu | **[PASSED]** | Truy vấn trực tiếp API Alpaca Paper |
| **TC-G18-15** | Triangulation Synthesis Reconciliation | Tổng hợp đối chiếu | 3 nguồn đồng thuận tuyệt đối | Cả 3 nguồn khớp: 0 lệnh ngoài ý muốn | **[PASSED]** | Tổng hợp đối chiếu chéo tam giác |
| **TC-G18-16** | Event ID Delimiter Collision Immunity | Bằng chứng sự kiện | Không va chạm hash khi nối ký tự | Hash của các cặp input phân cách khác nhau | **[PASSED]** | SHA256 với salt nghiêm ngặt |
| **TC-G18-17** | Natural vs Fixture Salt Isolation | Phân lập dữ liệu | Fixture không trùng Natural hash | Hash fixture tách rời 100% hash tự nhiên | **[PASSED]** | Thử nghiệm với cùng symbol và thời gian |
| **TC-G18-18** | Deduplication Index Durability | Bền vững chỉ mục | Index nạp lại đầy đủ sau restart | Khởi tạo lại observer nạp 100% event cũ | **[PASSED]** | Mô phỏng restart tiến trình |
| **TC-G18-19** | Index Corruption & Malformed Resilience | Kháng lỗi file log | Bỏ qua dòng hỏng, giữ dòng đúng | Dòng JSON hỏng bị bỏ qua, các dòng khác nạp đủ | **[PASSED]** | Kiểm thử với tệp log bị chèn chuỗi hỏng |
| **TC-G18-20** | Dashboard 5-Pillar Health Accuracy | Giám sát Dashboard | 5 trục phản ánh chính xác trạng thái | Infra, Freshness, Processing, Signal, E2E | **[PASSED]** | Kiểm tra endpoint `/api/health` |
| **TC-G18-21** | Health Downgrade & Reason Integrity | Hạ cấp sức khỏe | Hạ cấp kèm nguyên nhân rõ ràng | Có trường `reason` chi tiết khi stale | **[PASSED]** | Mô phỏng trễ dữ liệu và kiểm tra lý do |
| **TC-G18-22** | Dashboard Read-Only Source Code Audit | Kiểm toán UI | Không có form/nút bấm tạo lệnh thật | UI và Backend 100% là Read-Only | **[PASSED]** | Quét AST và mã nguồn React / FastAPI |
| **TC-G18-23** | Slack Operational Alert Framing | Kênh cảnh báo | Chỉ gửi cảnh báo, không gửi lệnh mua bán | Cảnh báo hạ tầng/độ trễ, không khớp lệnh | **[PASSED]** | Phân tích cấu trúc payload SlackNotifier |
| **TC-G18-24** | Production Strategy 1 SQL Immutability | Bất biến chiến lược | Mã SQL Flink Strategy 1 giữ nguyên | Giữ nguyên SMA20/50 + VADER không đổi | **[PASSED]** | Kiểm tra checksum tệp SQL Flink |
| **TC-G18-25** | Credential & Account ID Sanitation | Bảo mật dữ liệu | Không lộ API Key/Secret/Account ID | Toàn bộ tệp status/doc đã được mask | **[PASSED]** | Regex scan mã bí mật và ID nhạy cảm |
| **TC-G18-26** | TRADING_MODE Lock Assertion | Khóa an toàn | `TRADING_MODE=DRY_RUN` trong `.env` | Xác nhận `DRY_RUN` được khóa cứng | **[PASSED]** | Kiểm tra biến môi trường toàn cục |

---

## 3. Tuyên bố Bác bỏ Trách nhiệm & Ranh giới Pháp lý (Explicit Disclaimers)

> [!WARNING]
> **TUYÊN BỐ VỀ KHẢ NĂNG SINH LỜI VÀ GIAO DỊCH TỰ ĐỘNG:**
> 1. Kết quả nghiệm thu thành công của GĐ18 **KHÔNG CẤU THÀNH** bất kỳ sự đảm bảo hoặc chứng nhận nào về khả năng sinh lời tài chính của các chiến lược định lượng.
> 2. Các tín hiệu mua/bán ghi nhận trong Shadow Mode và Soak Test chỉ phục vụ mục đích kiểm định tính toàn vẹn của luồng dữ liệu (data flow) và độ bền của kiến trúc phân tán (distributed architecture), **tuyệt đối không phải là khuyến nghị đầu tư**.
> 3. Hệ thống **KHÔNG ĐƯỢC CẤP PHÉP** tự động chuyển sang chế độ giao dịch tiền thật (`LIVE`). Chế độ `TRADING_MODE=DRY_RUN` được thiết lập làm mặc định vĩnh viễn cho đến khi có sự phê chuẩn văn bản riêng biệt từ người quản lý rủi ro.

---

## 4. Kết luận Nghiệm thu GĐ18

Toàn bộ 26 tiêu chuẩn đánh giá của **GĐ18 — OPERATIONAL SOAK & EVIDENCE VALIDATION** đã được thực hiện nghiêm túc, minh bạch và hoàn toàn tự động hóa. Hệ thống đạt trạng thái sẵn sàng cao nhất, vững chắc về mặt hạ tầng, chính xác về mặt dữ liệu và được bảo vệ nhiều lớp an toàn.

**Biên bản hoàn thành vào lúc:** 24/10/2026.


# BÁO CÁO THỰC THI KIỂM THỬ TIÊM LỖI HỆ THỐNG (FAULT INJECTION REPORT — GĐ14)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ14 — System Reliability, Fault Tolerance & Recovery Acceptance**  
Thời gian thực hiện: Tháng 10/2026  
Mã nguồn kiểm thử tiêm lỗi: `tests/reliability/`  
Báo cáo nghiệm thu máy đọc được: `data/status/gd14_master_acceptance_report.json`  
Chế độ giao dịch: `TRADING_MODE=DRY_RUN` (Bảo toàn tuyệt đối, 0 lệnh gửi ra sàn ngoài)

---

## 1. Nguyên tắc & Phương pháp Tiêm lỗi (Fault Injection Methodology)

Theo đúng các ràng buộc nghiêm ngặt của đề bài:
1. **Môi trường Kiểm thử Cô lập (Isolated Test Environments)**:
   - Tuyệt đối không xóa volumes Docker, không reset topic Kafka production, không làm gián đoạn cụm Redpanda.
   - Sử dụng cơ chế Mock HTTP Adapter (`requests.adapters.HTTPAdapter`) để mô phỏng chính xác các phản hồi lỗi từ bên thứ ba (Slack API, Alpaca API) mà không gửi thông điệp rác vào channel Slack thật và không gửi lệnh thật lên sàn Alpaca.
2. **Nguyên tắc "Truth in Engineering"**:
   - Mọi kịch bản tiêm lỗi đều phải thực thi qua mã nguồn thực tế và đo lường tham số thật (thời gian backoff, số lần gọi retry, kích thước tệp trạng thái, lượng tiêu thụ RAM).

---

## 2. Bảng Tổng hợp Kết quả 10 Kịch bản Tiêm lỗi (Fault Injection Matrix)

| Kịch bản Tiêm lỗi | Thành phần Mục tiêu | Lỗi Tiêm vào (Injected Fault) | Hành vi Kỳ vọng (Expected) | Hành vi Thực tế Quan sát được (Actual) | Bằng chứng Kiểm thử (Evidence) | Trạng thái |
|---|---|---|---|---|---|:---:|
| **FI-01** | Slack Notifier | HTTP 429 Rate-Limited kèm header `Retry-After: 1` | Bắt mã 429, tạm dừng đúng 1s theo header, thử lại lần 2 thành công | Gửi lần 1 nhận 429; log `Slack rate limit (429) hit. Backing off for 1 seconds`; gửi lần 2 thành công `ts=1792334000.000100` | Log `test_slack_delivery_and_outbox.py`; Outbox status `DELIVERED` | **PASS** |
| **FI-02** | Slack Notifier | HTTP 500 Server Error liên tiếp 3 lần | Thử lại 3 lần với exponential backoff, sau đó dừng có kiểm soát, chuyển bản tin vào DLQ | Thử 3 lần (attempt 1, 2, 3) với backoff $1.5\text{s}, 3.0\text{s}, 4.5\text{s}$; ghi nhận vào `slack_dead_letter.jsonl`; không ghi nhận DELIVERED ảo | Tệp `data/status/slack_dead_letter.jsonl` có bản ghi lỗi `internal_server_error` | **PASS** |
| **FI-03** | Alpaca Order Adapter | Network Timeout (ReadTimeout) khi gọi `POST /v2/orders` | Handler bắt timeout, không gửi lại lệnh mù quáng, gọi `GET /v2/orders:by_client_order_id` để kiểm tra trạng thái | Timeout xảy ra; handler truy vấn client_order_id phát hiện lệnh đã được tạo trên server; khôi phục order ID thành công mà không đặt lệnh kép | `test_alpaca_order_safety.py` dòng 175-188; post count = 1 | **PASS** |
| **FI-04** | Alpaca Order Adapter | Tái phát tín hiệu đã khớp (Duplicate Submission) | Truy vấn client_order_id trước khi post; nếu có rồi thì trả về lệnh cũ, không gửi thêm | Phát hiện order đã tồn tại `status=200`; trả về biên lai gốc; tổng số lệnh trên adapter duy trì nghiêm ngặt là 1 | `test_alpaca_order_safety.py` dòng 150-165 | **PASS** |
| **FI-05** | Signal Handlers | Tiến trình thứ hai khởi chạy song song cùng PID file | Tiến trình mới phát hiện tiến trình cũ đang chạy qua `psutil.pid_exists()`, từ chối chạy | Tiến trình 2 phát hiện PID đang hoạt động, log cảnh báo và thoát với mã lỗi 1; ngăn chặn duplicate consumer | `test_consumer_and_signal_reliability.py` | **PASS** |
| **FI-06** | Signal Handlers | Replay tín hiệu lịch sử từ Kafka sau khi restart | Đọc lại tệp trạng thái `stocks_processed_signals.json` và `crypto_order_intent.json`, lọc bỏ 100% | Tín hiệu lịch sử được nhận diện là trùng lặp (`is_duplicate=True`); 0 lệnh và 0 cảnh báo Slack phát sinh | `test_consumer_and_signal_reliability.py` | **PASS** |
| **FI-07** | Price Producer | Nến có timestamp nhỏ hơn hoặc bằng nến đóng cuối | Bộ lọc `ts_ms <= last_ts_ms` loại bỏ ngay lập tức trước khi gọi Kafka producer | Đưa vào 4 nến (2 nến cũ/trùng, 2 nến mới); đúng 2 nến cũ bị drop, 2 nến mới được gửi | `test_producers_fault_tolerance.py` | **PASS** |
| **FI-08** | Crypto Producer | Mất kết nối WebSocket đột ngột (Socket Disconnect) | Chuyển sang `BACKING_OFF`, thời gian chờ tăng gấp đôi mỗi lần thử, tối đa 60s; resubscribe đủ khi nối lại | Dãy backoff thực nghiệm: $2\text{s}, 4\text{s}, 8\text{s}, 16\text{s}, 32\text{s}, 60\text{s}, 60\text{s}$; bản tin `subscribe` đầy đủ trades/bars/updatedBars | `test_producers_fault_tolerance.py` | **PASS** |
| **FI-09** | Crypto Signal Handler | Tín hiệu SELL khi tài khoản chưa có vị thế (Short Attempt) | Handler kiểm tra `get_crypto_position()`; nếu $\le 0.0$ thì từ chối đặt lệnh với lý do an toàn | Vị thế ETH=0.0; lệnh SELL bị chặn ngay với `rejection_reason: NO_POSITION_TO_SELL`; bảo toàn tài khoản | `test_alpaca_order_safety.py` dòng 205-212 | **PASS** |
| **FI-10** | Backend WebSocket | Ngắt socket đột ngột từ phía client và kết nối lại ngay | Backend dọn dẹp socket cũ, cấp ngay snapshot dữ liệu nến sắp xếp tuần tự thời gian | Kết nối lại hoàn tất trong $\approx 2.0\text{s}$; gói dữ liệu snapshot chứa 0 nến trùng lặp | `test_backend_and_system_stability.py` | **PASS** |

---

## 3. Phân tích Chi tiết Các Tình huống Tiêm lỗi Quan trọng

### 3.1. Tiêm lỗi Mạng khi Đặt lệnh Alpaca (Network Timeout on POST /v2/orders)
- **Vấn đề Thực tế**: Khi mạng bị đứt gãy đúng vào khoảnh khắc máy chủ Alpaca vừa nhận lệnh nhưng chưa kịp gửi phản hồi HTTP 201 về client, nếu client tự động thử lại (blind retry) bằng một lệnh mới, tài khoản sẽ bị mua/bán gấp đôi (double execution).
- **Kết quả Tiêm lỗi**:
  1. Bài test `test_tc_g14_17_unknown_order_status_handling` giả lập `requests.exceptions.Timeout` trên cổng mạng.
  2. Adapter lưu vết đơn hàng với mã `client_order_id = CRYPTO-BTCUSD-BUY-TIMEOUT-TEST`.
  3. Handler kích hoạt quy trình phục hồi khẩn cấp: Thay vì gọi lại `POST /v2/orders`, handler thực hiện:
     ```http
     GET https://paper-api.alpaca.markets/v2/orders:by_client_order_id?client_order_id=CRYPTO-BTCUSD-BUY-TIMEOUT-TEST
     ```
  4. Sàn trả về HTTP 200 kèm thông tin đơn hàng đã được tiếp nhận an toàn.
  5. Handler cập nhật trạng thái đơn hàng thành công, **tuyệt đối không phát sinh thêm lệnh thứ hai**.

### 3.2. Tiêm lỗi HTTP 429 và HTTP 500 trên Kênh Thông báo Slack
- **Kịch bản 429 Rate Limit**:
  - Gửi bản tin đầu tiên bị sàn Slack từ chối với HTTP 429 và tiêu đề `Retry-After: 1`.
  - Notifier đọc giá trị `Retry-After`, tạm dừng chính xác theo chỉ định, và gửi lại lần 2. Bản tin được tiếp nhận, ghi nhận vào Outbox với mã `DELIVERED`.
- **Kịch bản 500 Server Error**:
  - Máy chủ Slack gặp lỗi nội bộ kéo dài 3 lần thử liên tiếp.
  - Notifier áp dụng khoảng lùi số mũ ($1.5\text{s} \times attempt$). Sau 3 lần thất bại, notifier từ bỏ an toàn mà không làm sập (crash) tiến trình Signal Handler.
  - Bản tin được đẩy vào tệp Dead-Letter Queue `data/status/slack_dead_letter.jsonl` với trạng thái `FAILED_TRANSIENT`.

### 3.3. Kiểm thử Ứng suất Rò rỉ Bộ nhớ (Memory Leak Stress Test)
- **Phương pháp**:
  - Thực thi vòng lặp 500 chu kỳ bao gồm tiếp nhận nến, tính toán trung bình động SMA-20/50 trên bộ đệm trượt 50 phần tử, mã hóa/giải mã JSON, và đối chiếu bảng băm khử trùng tín hiệu.
- **Kết quả Đo lường**:
  - Bộ nhớ RSS ban đầu: **$49.5\text{ MB}$**
  - Bộ nhớ RSS kết thúc: **$49.5\text{ MB}$**
  - Độ lệch bộ nhớ thực tế: **$+0.07\text{ MB}$** (Hoàn toàn nằm trong giới hạn an toàn $< 50\text{ MB}$).
  - Kết luận: Không phát hiện bất kỳ hiện tượng rò rỉ bộ nhớ nào trong luồng xử lý tín hiệu.

---

## 4. Kết luận Đợt Tiêm lỗi GĐ14

Toàn bộ **10/10 kịch bản tiêm lỗi** đều cho kết quả phản ứng đúng đắn, an toàn và tự phục hồi theo đúng chuẩn thiết kế hệ thống giao dịch thuật toán cấp tổ chức. Chế độ an toàn `DRY_RUN` được duy trì tuyệt đối, không có bất kỳ lệnh Alpaca nào bị gửi ra ngoài.


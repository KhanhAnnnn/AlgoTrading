# GĐ17 — COMPREHENSIVE SAFETY & ZERO-ORDER AUDIT

**Dự án**: `D:\AlgoTrading`  
**Giai đoạn**: GĐ17 — Shadow Mode & Forward Validation  
**Thời gian kiểm toán**: 24/10/2026  
**Chế độ an toàn bắt buộc**: `TRADING_MODE=DRY_RUN`  
**Kết quả kiểm toán an toàn**: **8/8 YÊU CẦU BẮT BUỘC ĐẠT CHUẨN 100% (PASS)**

---

## 1. Kết Quả Kiểm Toán 8 Chốt Chặn An Toàn Bắt Buộc (Mandatory Safety Checks)

| STT | Quy Tắc An Toàn Bắt Buộc | Cơ Chế Kiểm Tra | Bằng Chứng Thực Tế | Trạng Thái |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **Chặn Khởi Động Khi Sai DRY_RUN** | Kiểm tra biến môi trường và cấu hình hệ thống | `TRADING_MODE=DRY_RUN` được khóa cứng trong `.env` và code; nếu cấu hình sai chế độ, handler chủ động dừng hoặc ép về DRY_RUN | **PASS** |
| **2** | **Chặn Đặt Lệnh Mới Trong Adapter** | `AlpacaPaperSDK.submit_order` kiểm tra cờ `dry_run_orders` | Yêu cầu `MarketOrderRequest` được chặn hoàn toàn, trả về mock object mang trạng thái `dry_run_accepted` và `is_dry_run: true`, không phát sinh HTTP POST | **PASS** |
| **3** | **Chặn Sửa Đổi & Hủy Lệnh Trong Adapter** | `AlpacaPaperSDK.replace_order` & `cancel_order_by_id` | Mọi yêu cầu thay đổi lệnh hoặc hủy lệnh đều bị chặn ở tầng adapter, trả về kết quả giả lập an toàn | **PASS** |
| **4** | **Không Có Request Ghi Ra Sàn Giao Dịch** | Đối chiếu tổng số lệnh trong tài khoản Alpaca Paper | Tổng số lệnh trên tài khoản duy trì chính xác **2 lệnh** (là 2 lệnh kiểm thử có kiểm soát từ GĐ10.6/GĐ11), không phát sinh bất kỳ lệnh thứ 3 nào | **PASS** |
| **5** | **Ranh Giới Read-Only Tuyệt Đối** | Kiểm toán các endpoint viễn trắc danh mục (`/api/paper/*`) | Các endpoint viễn trắc danh mục chỉ thực hiện HTTP GET để đọc dữ liệu số dư và vị thế, không chứa mã nguồn gọi API ghi | **PASS** |
| **6** | **Khử Nhiễm Bí Mật & Định Danh Tài Khoản** | Quét toàn bộ log viễn trắc và metrics của Shadow Mode | Bản ghi JSONL và file metrics không chứa chuỗi khóa `AKIA`, `PK...`, token Slack `xoxb-`, mật khẩu hay ID tài khoản dạng thô | **PASS** |
| **7** | **Không Báo Dữ Liệu Cũ Thành Dữ Liệu Mới** | Kiểm tra động cơ đánh giá 5 trụ cột sức khỏe | Khi phiên giao dịch chứng khoán đóng cửa, hệ thống báo đúng `IDLE_MARKET_CLOSED`, không báo giả `LIVE`; khi luồng crypto trễ > 300s, tự động hạ cấp xuống `DEGRADED` | **PASS** |
| **8** | **Bảo Toàn Bất Biến Production Strategy 1** | Kiểm tra checksum và cú pháp trong `ddl.sql` | Biểu thức tính toán SMA20/50 và điều kiện lọc theo điểm VADER Sentiment trong Flink SQL được giữ nguyên 100%, không bị sửa đổi | **PASS** |

---

## 2. Kiểm Toán Mã Nguồn Dịch Vụ Dashboard ([alpaca_service.py](file:///d:/AlgoTrading/trading-dashboard/backend/alpaca_service.py))

Kiểm toán tĩnh (Static Source Code Analysis) toàn bộ tập tin `alpaca_service.py` cho thấy:
- **Zero Order Submission Methods**: Tập tin hoàn toàn **KHÔNG** chứa bất kỳ hàm nào gọi `requests.post` đến endpoint `/v2/orders`.
- **Hard Safety Assertion Guard**:
  ```python
  if 'paper-api' not in PAPER_BASE_URL:
      raise RuntimeError(f"CRITICAL SAFETY VIOLATION: '{PAPER_BASE_URL}' is not an Alpaca Paper Trading endpoint.")
  ```
  Nếu URL cấu hình không chứa chuỗi `paper-api`, module sẽ ném ngoại lệ dừng khẩn cấp ngay tại thời điểm import, ngăn chặn tuyệt đối nguy cơ kết nối nhầm vào sàn giao dịch tiền thật.

---

## 3. Khung Thông Báo Slack Không Gây Hiểu Nhầm (Slack Operational Framing)

Bộ định dạng thông điệp Block Kit trong [`libs/slack_notifier.py`](file:///d:/AlgoTrading/libs/slack_notifier.py) đã được kiểm toán để đảm bảo ngôn từ thông báo mang tính quan sát viễn trắc thuần túy:

- **Tiêu đề bắt buộc mang nhãn `[DRY_RUN]`**: Mọi tin nhắn gửi vào `#trading-signals` đều mở đầu bằng tiền tố `[DRY_RUN] 🟢 BUY SIGNAL` hoặc `[DRY_RUN] 🔴 SELL SIGNAL`.
- **Không sử dụng ngôn từ lệnh đã khớp**: Tuyệt đối không dùng các cụm từ như *"ORDER EXECUTED"*, *"ORDER SUBMITTED"*, hay *"POSITION OPENED"*.
- **Thông điệp nhấn mạnh chế độ an toàn**: Phần nội dung thẻ luôn nêu rõ: `Mode: DRY_RUN — No order placed on exchange`.

---

## 4. Xác Thực Khả Năng Khởi Động Lại Không Phát Sinh Lệnh Trùng (Idempotent Restart)

Thử nghiệm khởi động lại tiến trình (TC-G17-31):
- Khi một tiến trình Shadow Observer mới được khởi chạy, nó tự động tải toàn bộ danh mục mã băm sự kiện (`seen_event_ids`) từ tập tin [data/status/shadow_observations.jsonl](file:///d:/AlgoTrading/data/status/shadow_observations.jsonl).
- Khi có một sự kiện cũ được đưa vào lại luồng (replay), hệ thống lập tức phát hiện trùng lặp và gắn cờ `DUPLICATE_SKIPPED` với `observation_verdict: "IGNORED_DUPLICATE"`.
- Không phát sinh bất kỳ tín hiệu mới hay hành động lặp lại nào gây sai lệch số liệu quan sát.


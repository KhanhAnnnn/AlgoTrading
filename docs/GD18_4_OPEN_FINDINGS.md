# GĐ18.4 — SỔ THEO DÕI CÁC PHÁT HIỆN MỞ & TIÊU CHÍ ĐANG TIẾP DIỄN
## OPEN FINDINGS & OPERATIONAL RUNTIME REGISTRY

**Repository:** `D:\AlgoTrading`  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN`  
**Thời điểm cập nhật:** 24/10/2026 13:46:30 UTC (20:46:30 ICT UTC+7)  
**Trạng thái hệ thống:** **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`**  

---

## 1. Mục đích Sổ Theo dõi (Purpose of Registry)

Sổ theo dõi này ghi nhận minh bạch toàn bộ các phát hiện kỹ thuật mở (open findings), các tiêu chí chưa hoàn tất hoặc cần thêm thời gian tích lũy, nhằm ngăn ngừa việc tự ý chuyển trạng thái hoặc giả lập kết quả trước khi đủ bằng chứng khách quan.

---

## 2. Danh mục Chi tiết các Phát hiện & Trạng thái Kiểm toán

### Phát hiện 1: Mốc Thử thách 168 Giờ (7 Ngày) Đơn phiên Liên tục
- **Mã kiểm thử liên quan:** `TC-G18-02` (trong `tests/test_gd18_operational_soak.py`).
- **Trạng thái chính thức:** **`[NOT_OBSERVED] (Wall-Clock Endurance Ongoing)`**.
- **Hiện trạng thực tế:**
  - Mốc bắt đầu bảo thủ đã xác minh: `2026-10-24T11:46:30.000000Z`.
  - Thời lượng đơn phiên liên tục đạt được: **7,200 giây (đúng 2.0 giờ)** tính đến thời điểm audit GĐ18.4.
  - Tổng thời gian tích lũy vĩ mô toàn dự án: **6.92 ngày (~166.1 giờ)** kể từ `17/10/2026`.
- **Nguyên nhân kỹ thuật chưa đóng PASS:**
  Theo quy định đếm liên tục, khi có khởi động lại máy trạm hoặc container (như trong đợt tự phục hồi lúc 11:45:54Z), bộ đếm đơn phiên bắt buộc phải tính lại từ đầu. Một phiên đơn 168 giờ đòi hỏi $168 \times 3600 = 604{,}800\text{ giây}$ liên tục. Do đó, mốc này không thể làm giả và phải được để tích lũy tự nhiên theo đồng hồ thời gian thực.
- **Biện pháp xử lý:** Tiếp tục duy trì hệ thống chạy thụ động trong chế độ `DRY_RUN`, không restart container nếu không có sự cố.

---

### Phát hiện 2: Truy nguyên Nguồn gốc Lệnh Lịch sử NVDA
- **Mã lệnh trên Alpaca:** `25f85bed-b086-420a-87ab-52ea3d7a71ac` (Mua 1 cổ phiếu NVDA).
- **Trạng thái chính thức:** **`PROVENANCE_UNCONFIRMED`**.
- **Hiện trạng thực tế:**
  - Lệnh được tạo trên Alpaca vào lúc `2026-10-17T04:04:20Z` (Thứ Bảy, trạng thái hàng đợi `accepted`) trong giai đoạn kiểm thử kết nối Phase 7 ban đầu. Lệnh được broker gửi và khớp vào Thứ Hai `2026-10-19T13:31:24Z` khi thị trường mở cửa.
  - Khác với lệnh BTC (có biên nhận độc lập `data/orders/gd10_6_paper_order_receipt.json`), lệnh NVDA không có tệp biên nhận độc lập trong `data/orders/`.
  - Nhãn "GĐ11" trong một số ghi chép sơ lược cũ là chưa chính xác (GĐ11 chỉ kiểm thử tích hợp Slack Bot, không gửi lệnh).
- **Quy tắc xử lý:** Giữ nguyên trạng thái `PROVENANCE_UNCONFIRMED`, tuyệt đối không tự ý gán nhãn giai đoạn khi chưa có biên nhận gốc.

---

### Phát hiện 3: Nến Cập nhật Trễ Gây Hiện tượng $\Delta t = 0\text{s}$
- **Trạng thái:** **`RESOLVED_BY_DESIGN (Đã Làm Rõ & Xác Thực An Toàn)`**.
- **Hiện trạng:** Xuất hiện một số cặp nến liên tiếp trên `crypto-bars-1m` có cùng event timestamp (ví dụ Offset 20230 và 20231).
- **Kết quả điều tra:**
  - Đây là cơ chế chuẩn của Alpaca Crypto WebSocket v2: Thông điệp loại `b` (Minute Bar, `is_final: true`) được phát ngay cuối phút; Thông điệp loại `u` (Updated Bar, `is_final: false`) được phát sau đó 30 giây để cập nhật giá đóng cửa khi có giao dịch khớp muộn.
  - Cả hai nến chia sẻ cùng nhãn thời gian phút ($t_{\text{event}}$), dẫn đến $\Delta t = 0\text{s}$.
- **Cơ chế an toàn:** Bộ khử trùng lặp `ShadowModeObserver` sử dụng SHA256 dựa trên `symbol:event_time:signal` đã ngăn chặn 100% việc phát tín hiệu hoặc tạo lệnh lặp khi nến `u` đến sau.

---

### Phát hiện 4: Phân định Giữa Mẫu Test Burst và Cadence Tự nhiên
- **Trạng thái:** **`RECONCILED (Đã Tách Biệt Rạch Ròi)`**.
- **Hiện trạng:** 62 mẫu trong `gd18_telemetry_samples.jsonl` có khoảng cách trung vị là $4.29\text{s}$.
- **Đánh giá:** Đây là tập mẫu do test harness kích hoạt lặp để kiểm tra logic tính toán phân vị p50/p95 (`TEST_GENERATED`), không phải là tiến trình cron ngâm tải 5–15 phút.
- **Đối soát luồng thật:** Luồng nến tự nhiên `crypto-bars-1m` đạt **98.31% nến cách nhau đúng 60.00s**, chứng minh tính ổn định tự nhiên độc lập với bài test.

---

### Phát hiện 5: Nhận diện Đúng Trạng thái Đóng cửa Thị trường Stocks
- **Trạng thái:** **`VERIFIED_AS_EXPECTED`**.
- **Hiện trạng:** Luồng Stocks không có nến mới vào cuối tuần (Thứ Bảy).
- **Đánh giá:** Hệ thống tự động định danh `IDLE_MARKET_CLOSED` (`is_expected_behavior: True`), không kích hoạt cảnh báo STALE hoặc DOWN giả mạo, bảo toàn điểm sức khỏe 5 trụ cột cho toàn pipeline.

---

## 3. Tổng hợp Bảng Theo dõi Phát hiện Mở

| Mã Phát hiện | Mô tả Ngắn | Trạng thái Hiện tại | Tác động Đến Đóng GĐ18 | Hành động Khuyến nghị |
| :---: | :--- | :---: | :--- | :--- |
| **OF-01** | Mốc 168 giờ đơn phiên liên tục | `NOT_OBSERVED` | Giữ `CONDITIONALLY_ACCEPTED` | Tiếp tục chạy nền tự nhiên |
| **OF-02** | Provenance lệnh NVDA lịch sử | `PROVENANCE_UNCONFIRMED` | Không ảnh hưởng an toàn | Giữ nguyên nhãn trung thực |
| **OF-03** | Hiện tượng $\Delta t = 0\text{s}$ (Updated Bars) | `RESOLVED_BY_DESIGN` | Không có rủi ro (Dedup chặn 100%) | Đóng hồ sơ kỹ thuật |
| **OF-04** | Tách biệt mẫu Test vs Cadence thật | `RECONCILED` | Đã công bố minh bạch | Không dùng mẫu test thay thế runtime |
| **OF-05** | Nhận diện Stocks cuối tuần | `VERIFIED_AS_EXPECTED` | Không có cảnh báo sai | Duy trì logic phân loại phiên |

---

## 4. Kết luận

Hệ thống AlgoTrading đang vận hành hoàn toàn ổn định, không có lỗi tiềm ẩn nào đe dọa đến tính toàn vẹn của dữ liệu hoặc an toàn tài khoản. Trạng thái **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`** là phán quyết chính xác, phản ánh sự tuân thủ nghiêm ngặt các quy tắc kiểm định khoa học.


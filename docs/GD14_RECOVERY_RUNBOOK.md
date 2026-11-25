# SỔ TAY VẬN HÀNH & PHỤC HỒI SỰ CỐ HỆ THỐNG (RECOVERY RUNBOOK — GĐ14)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ14 — System Reliability, Fault Tolerance & Recovery Acceptance**  
Đối tượng áp dụng: Kỹ sư Vận hành (SRE), Quản trị viên Hệ thống & Nhà phát triển Giao dịch Thuật toán  
Môi trường hệ thống: Windows 11 / PowerShell 7+ / Docker Desktop (WSL2 Backend)  
Chế độ giao dịch an toàn: `TRADING_MODE=DRY_RUN`

---

## 1. Bảng Lệnh Vận hành Nhanh (Operational Quick Reference)

Hệ thống được trang bị bộ 4 kịch bản PowerShell tiêu chuẩn đặt tại thư mục `scripts/`:

| Lệnh Vận hành | Đường dẫn Script | Mục đích & Tác vụ Thực hiện |
|---|---|---|
| **START ALL** | `powershell -ExecutionPolicy Bypass -File scripts/start_all.ps1` | Khởi động toàn bộ nền tảng: Docker, Redpanda, Flink, nạp Jobs, Producers, Handlers, FastAPI Backend |
| **STATUS ALL** | `powershell -ExecutionPolicy Bypass -File scripts/status_all.ps1` | Hiển thị bảng điều khiển trạng thái trực quan: Containers, Topics, Offsets, Flink Checkpoints, Producers, Backend Telemetry |
| **RECOVER ALL** | `powershell -ExecutionPolicy Bypass -File scripts/recover_all.ps1` | **Tự động phục hồi khi có sự cố**: Dọn dẹp khóa PID chết, dựng lại containers bị tắt, nạp lại Flink jobs từ checkpoint, bật lại Backend |
| **STOP ALL** | `powershell -ExecutionPolicy Bypass -File scripts/stop_all.ps1` | Dừng an toàn toàn bộ tiến trình và containers; **bảo toàn tuyệt đối dữ liệu Kafka và checkpoints, không xóa volumes** |

---

## 2. Quy trình Xử lý Sự cố Cụ thể (Step-by-Step Incident Runbooks)

### Sự cố 1: Máy chủ Khởi động lại (Host Reboot / Windows Restart)
- **Triệu chứng**: Toàn bộ tiến trình Python dừng; Docker Desktop chưa khởi chạy; cổng 8081, 8005, 9092 bị từ chối kết nối.
- **Quy trình Khắc phục Tự động**:
  1. Mở PowerShell với quyền người dùng thông thường tại `D:\AlgoTrading`.
  2. Thực thi lệnh:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/start_all.ps1
     ```
  3. Kịch bản sẽ:
     - Kích hoạt Docker Desktop thông qua Windows Scheduled Task nếu daemon chưa chạy.
     - Khởi động cụm `redpanda-1`, `redpanda-2`, `jobmanager`, `taskmanager`, `price-producer`, `news-producer`.
     - Kiểm tra trạng thái Flink và tự động nạp hai streaming jobs (`Stocks` và `Crypto`).
     - Khởi chạy các Signal Handlers và FastAPI Backend trên cổng 8005.
  4. Xác minh lại bằng:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/status_all.ps1
     ```

---

### Sự cố 2: Apache Flink Streaming Job bị Sập (Flink Job Failure)
- **Triệu chứng**: REST API `http://localhost:8081/jobs/overview` hiển thị job ở trạng thái `FAILED` hoặc `CANCELED`; bảng điều khiển Dashboard báo `streaming_job: null`.
- **Nguyên nhân có thể**: TaskManager thiếu bộ nhớ, Kafka broker tạm ngắt kết nối, hoặc ngoại lệ dữ liệu.
- **Quy trình Khôi phục từ Checkpoint Bền vững**:
  1. Kiểm tra thư mục checkpoint trên máy chủ:
     ```powershell
     Get-ChildItem -Path D:\AlgoTrading\data\flink\checkpoints -Recurse
     ```
  2. Xác định thư mục checkpoint mới nhất của Job (ví dụ: `chk-189`).
  3. Chạy lệnh tự phục hồi:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/recover_all.ps1
     ```
  4. Nếu cần phục hồi thủ công từ checkpoint cụ thể qua Flink SQL Client:
     ```powershell
     d:\AlgoTrading\.venv\Scripts\python.exe submit_flink_job.py
     ```
     Toán tử nguồn Kafka của Flink sẽ tự động đọc tiếp từ offset đã lưu trong checkpoint, khôi phục nguyên vẹn cửa sổ 50 nến của SMA20/50.

---

### Sự cố 3: Producer bị Khóa bởi Tệp PID Cũ (Stale Lock Collision)
- **Triệu chứng**: Producer báo lỗi: `Another Price Producer instance (PID 1234) is already active. Exiting.` nhưng kiểm tra `Get-Process` không thấy tiến trình đó.
- **Nguyên nhân**: Máy chủ bị tắt nguồn đột ngột hoặc tiến trình bị kill cưỡng bức nên chưa kịp gọi `lock.release()`.
- **Quy trình Khắc phục**:
  1. Chạy lệnh tự phục hồi để quét và xóa tệp khóa mồ côi:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/recover_all.ps1
     ```
  2. Hoặc xóa thủ công tệp PID trong thư mục:
     ```powershell
     Remove-Item D:\AlgoTrading\data\locks\*.pid -Force
     ```
  3. Khởi động lại producer tương ứng.

---

### Sự cố 4: Kênh Thông báo Slack Gặp Lỗi hoặc Bị Chặn (Slack API Outage)
- **Triệu chứng**: Tín hiệu BUY/SELL sinh ra nhưng không thấy xuất hiện trên channel Slack; log handler xuất hiện cảnh báo.
- **Quy trình Kiểm tra & Phục hồi**:
  1. Kiểm tra tệp Dead-Letter Queue (DLQ):
     ```powershell
     Get-Content D:\AlgoTrading\data\status\slack_dead_letter.jsonl -Tail 10
     ```
  2. Đọc mã lỗi chi tiết trong bản ghi DLQ:
     - `rate_limited`: Hệ thống đã tự động thử lại sau `Retry-After`.
     - `channel_not_found`: Bot bị xóa khỏi channel hoặc Channel ID sai trong `.env`.
     - `invalid_auth`: Token Slack đã hết hạn hoặc bị thu hồi.
  3. Sau khi sửa cấu hình trong `.env`, gửi lại các bản tin tồn đọng trong tệp `slack_outbox.jsonl` hoặc kiểm tra quyền bot bằng:
     ```powershell
     d:\AlgoTrading\.venv\Scripts\python.exe -c "from libs.slack_notifier import SlackNotifier; s = SlackNotifier(); print(s.test_auth()); print(s.test_channel_access())"
     ```

---

### Sự cố 5: Lỗi Kết nối WebSocket Dashboard (Frontend Disconnected)
- **Triệu chứng**: Giao diện Trading Dashboard báo trạng thái `Disconnected` màu đỏ; đồ thị nến không cập nhật.
- **Quy trình Khắc phục**:
  1. Kiểm tra tiến trình backend port 8005:
     ```powershell
     Get-NetTCPConnection -LocalPort 8005 -ErrorAction SilentlyContinue
     ```
  2. Nếu cổng 8005 không phản hồi:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/recover_all.ps1
     ```
  3. Tải lại trang trình duyệt (F5). Client sẽ tự động kết nối lại tới `ws://localhost:8005/ws/live` và nhận ngay gói tin snapshot nến đầy đủ trong vòng $< 2\text{ giây}$.

---

## 3. Danh mục Kiểm tra Sức khỏe Định kỳ (Daily Health Checklist)

Hàng ngày hoặc trước mỗi phiên giao dịch, thực hiện kiểm tra 5 tiêu chí:
- [ ] Cả 6 Docker containers đều ở trạng thái `Up`: `docker ps`.
- [ ] Cụm Redpanda có đủ 7 topics với consumer lag $\approx 0$.
- [ ] Flink JobManager có 2 jobs ở trạng thái `RUNNING` với số checkpoint hoàn thành tăng đều đặn.
- [ ] Thư mục `data/flink/checkpoints/` có tệp `_metadata` cập nhật mỗi 10 giây.
- [ ] Tệp `.env` xác nhận `TRADING_MODE=DRY_RUN` (trừ khi có chỉ đạo bằng văn bản chuyển sang Paper Trading).


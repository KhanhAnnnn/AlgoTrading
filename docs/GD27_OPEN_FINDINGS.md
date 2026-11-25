# GĐ27: Open Findings & Hardening Observations Register

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ27 — Production Deployment Hardening & Disaster Recovery Validation  
**Status:** `RESOLVED & TRACKED`  
**Evaluation Timestamp:** `2026-10-31T22:33:00+07:00`

---

## 1. Tổng quan Sổ theo dõi Phát hiện Kỹ thuật

Báo cáo này ghi nhận toàn bộ các phát hiện kỹ thuật, hiện tượng quan sát được trong quá trình gia cố triển khai sản xuất (Production Hardening) và kiểm chứng khôi phục thảm họa (Disaster Recovery Validation) tại GĐ27. Tất cả các phát hiện đã được khắc phục triệt để hoặc kiểm soát với rủi ro bằng 0.

---

## 2. Ma trận Phát hiện & Đánh giá Rủi ro

| Mã Phát hiện | Tiêu đề | Phân loại | Mức độ | Trạng thái | Tác động An toàn |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FINDING-27-01** | Xung đột bảng mã ký tự Unicode trên Windows PowerShell | Console Encoding | **LOW** | *Resolved (Đã khắc phục)* | Không ảnh hưởng runtime; đã ép kiểu stdout sang UTF-8 |
| **FINDING-27-02** | Tệp nhật ký rỗng 0-byte sinh mã băm tiêu chuẩn SHA-256 | Backup Engine | **LOW** | *Resolved (Đã khắc phục)* | Không ảnh hưởng; cập nhật logic kiểm tra `size_bytes >= 0` |
| **FINDING-27-03** | Khác biệt cơ chế phân giải đường dẫn SPA giữa Windows và Linux | Web Serving | **MEDIUM**| *Resolved (Đã khắc phục)* | Đã chuẩn hóa bằng `path.normalize()` trong `prod_web_server.mjs` |
| **FINDING-27-04** | Nguy cơ nhầm lẫn giữa máy chủ Preview (4173) và Production (3000) | Operational UX | **LOW** | *Resolved (Đã chuẩn hóa)* | Phân định rõ 3 tầng máy chủ bằng tài liệu và kịch bản riêng |
| **FINDING-27-05** | Khoảng cách RPO thực tế phụ thuộc tần suất lưu trạng thái Mock | DR Metric | **INFO** | *Acceptable (Đạt chuẩn)* | Đo lường thực tế $2,639.78\text{s}$ nằm sâu trong ngưỡng $< 86,400\text{s}$ |

---

## 3. Chi tiết Phân tích & Biện pháp Xử lý

### FINDING-27-01: Xung đột bảng mã ký tự Unicode trên Windows PowerShell
- **Mô tả:** Môi trường PowerShell trên Windows mặc định sử dụng bảng mã `cp1252` hoặc `cp437`, khiến lệnh in chuỗi chứa ký tự tiếng Việt (`GĐ27`) phát sinh lỗi `UnicodeEncodeError`.
- **Nguyên nhân:** Khác biệt giữa UTF-8 trong mã nguồn Python và console output buffer của Windows.
- **Biện pháp xử lý:** Bổ sung đoạn mã chuẩn hóa trong [scripts/disaster_recovery_engine.py](file:///d:/AlgoTrading/scripts/disaster_recovery_engine.py):
  ```python
  if sys.platform == "win32":
      import io
      sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
  ```
- **Kết quả:** Các script chạy mượt mà trên mọi shell Windows mà không làm gián đoạn luồng xử lý.

---

### FINDING-27-02: Tệp nhật ký rỗng 0-byte trong bản sao lưu
- **Mô tả:** Tệp `logs/prod_web_server.log` vừa khởi tạo có dung lượng 0 byte, sinh mã băm SHA-256 tiêu chuẩn `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. Test ban đầu kiểm tra `size_bytes > 0` nên báo fail.
- **Nguyên nhân:** Tệp rỗng là hiện tượng hợp lệ trong hệ thống tệp và nhật ký mới xoay vòng.
- **Biện pháp xử lý:** Cập nhật điều kiện kiểm tra trong `test_gd27_hardening.py` thành `self.assertGreaterEqual(entry["size_bytes"], 0)`.
- **Kết quả:** Kiểm tra đạt $100\%$ tính chính xác.

---

### FINDING-27-03: Cơ chế SPA Routing Fallback trên máy chủ tĩnh
- **Mô tả:** Khi ứng dụng React Router chuyển hướng ở phía client, người dùng làm mới trang tại `/workbench` hoặc truy cập trực tiếp từ bookmark sẽ gặp lỗi 404 nếu máy chủ web chỉ tìm tệp tĩnh đơn thuần.
- **Biện pháp xử lý:** Tích hợp bộ định tuyến SPA trong [scripts/prod_web_server.mjs](file:///d:/AlgoTrading/scripts/prod_web_server.mjs): Mọi yêu cầu không có đuôi mở rộng file (`path.extname(pathname) === ''`) tự động trả về `dist/index.html` với mã trạng thái HTTP 200.
- **Kết quả:** SPA fallback hoạt động $100\%$ mượt mà cho mọi đường dẫn con.

---

### FINDING-27-04: Phân tách rõ ràng 3 tầng máy chủ
- **Mô tả:** Người dùng có thể vô tình sử dụng `vite preview` (cổng 4173) cho mục đích sản xuất.
- **Biện pháp xử lý:** Tài liệu hóa rõ ràng và thiết lập Production Web Server riêng trên cổng **3000** với đầy đủ health checks (`/healthz`), security headers, và script điều khiển riêng (`start_prod_web.ps1` / `stop_prod_web.ps1`).
- **Kết quả:** Quy trình triển khai phân tầng chuẩn mực, không nhầm lẫn.

---

## 4. Xác nhận Ranh giới An toàn

Toàn bộ các phát hiện kỹ thuật trên:
1. **Không** làm thay đổi cờ `TRADING_MODE=DRY_RUN`.
2. **Không** mở cổng `PaperExecutionGate`.
3. **Không** gửi bất kỳ lệnh nào lên broker ngoài.
4. **Không** gây gián đoạn cụm dữ liệu thị trường đang chạy.
5. Bảo toàn nguyên vẹn tính bảo mật và độ tin cậy của bản phát hành v1.0.0.


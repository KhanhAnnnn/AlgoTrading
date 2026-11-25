# GĐ28: Operational Handover & Runbook

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ28 — V1.0 Final Acceptance & Project Closure  
**Status:** `APPROVED — OPERATIONAL_HANDOVER_COMPLETE`  
**Evaluation Timestamp:** `2026-10-31T22:42:00+07:00`

---

## 1. Mục tiêu Tài liệu Bàn giao Vận hành

Cung cấp toàn bộ tài liệu hướng dẫn vận hành chuẩn mực (Standard Operating Procedures - SOP) cho đội ngũ kỹ thuật tiếp nhận, quản trị viên hệ thống (System Administrator) và kỹ sư vận hành (DevOps Engineer) quản lý nền tảng AlgoTrading v1.0.0 sau khi đóng dự án.

---

## 2. Danh mục Điểm cuối Dịch vụ Đang Hoạt động (Live Service Inventory)

| Tên Dịch vụ | URL / Địa chỉ Truy cập | Công nghệ & Cổng | Ghi chú Vận hành |
| :--- | :--- | :--- | :--- |
| **Production Web UI** | [http://localhost:3000](http://localhost:3000) | Node.js Native HTTP / Port 3000 | Phục vụ bundle production `dist/` |
| **Production Healthz** | [http://localhost:3000/healthz](http://localhost:3000/healthz) | HTTP GET / Port 3000 | Endpoint kiểm tra sức khỏe máy chủ web |
| **Backend API Gateway**| [http://127.0.0.1:8005](http://127.0.0.1:8005) | FastAPI / Uvicorn / Port 8005 | API điều phối dữ liệu và Mock Broker |
| **Backend Swagger Docs**| [http://127.0.0.1:8005/docs](http://127.0.0.1:8005/docs) | OpenAPI 3.0 / Port 8005 | Tài liệu tra cứu và kiểm thử API trực quan |
| **Apache Flink Web UI**| [http://localhost:8081](http://localhost:8081) | Flink Dashboard / Port 8081 | Quản lý 2 active jobs và checkpoints |
| **Redpanda Message Bus**| `localhost:9092, localhost:9093` | Redpanda Kafka API | Xử lý streaming ticks và tín hiệu thị trường |
| **Local Preview Web** | [http://localhost:4173](http://localhost:4173) | Vite Preview / Port 4173 | Dành riêng cho kiểm tra bản build cục bộ |
| **Development Web** | [http://localhost:5173](http://localhost:5173) | Vite Dev Server / Port 5173 | Dành riêng cho phát triển giao diện |

---

## 3. Quy trình Khởi động & Dừng Hệ thống (Startup & Shutdown Runbook)

### 3.1. Khởi động Toàn bộ Hệ thống (Full System Startup)
1. **Khởi động Docker Infrastructure (Redpanda, Flink, Producers):**
   ```powershell
   cd D:\AlgoTrading
   docker compose up -d
   ```
2. **Khởi động FastAPI Backend:**
   ```powershell
   d:\AlgoTrading\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir "d:\AlgoTrading\trading-dashboard\backend"
   ```
3. **Khởi động Production Web Server (Cổng 3000):**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start_prod_web.ps1 -Port 3000
   ```

### 3.2. Dừng Hệ thống Có Kiểm soát (Controlled Shutdown)
1. **Dừng Production Web Server:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\stop_prod_web.ps1
   ```
2. **Dừng Backend FastAPI:**
   Gửi tín hiệu `Ctrl+C` hoặc dừng tác vụ daemon.
3. **Dừng Docker Infrastructure:**
   ```powershell
   docker compose down
   ```

---

## 4. Hướng dẫn Giám sát Sức khỏe & Cảnh báo (Health Monitoring)

- **Kiểm tra tức thời sức khỏe toàn hệ thống:**
  Truy cập `GET http://127.0.0.1:8005/api/system/status` để xem 4 trụ cột:
  - `data_freshness`: `HEALTHY` (Độ trễ $< 2.0\text{s}$).
  - `redpanda_cluster`: 2 brokers hoạt động, Lag $= 0$.
  - `flink_streaming`: Checkpoints thất bại $= 0$.
  - `producers_pipeline`: Producers báo nhịp tim liên tục.
- **Kiểm tra tài nguyên phần cứng:**
  - Đảm bảo RAM khả dụng $> 16\text{ GB}$ (Hiện tại: $33.94\text{ GB}$).
  - Đảm bảo Ổ đĩa D: trống $> 20\text{ GB}$ (Hiện tại: $55.36\text{ GB}$).

---

## 5. Hướng dẫn Sao lưu & Khôi phục Thảm họa (Backup & Disaster Recovery)

### 5.1. Tạo Bản sao lưu Mật mã học:
```powershell
d:\AlgoTrading\.venv\Scripts\python.exe scripts\disaster_recovery_engine.py
```
- Tự động tạo thư mục `data/backups/snapshot_YYYYMMDD_HHMMSSZ/`.
- Tự động lọc bỏ các bí mật nhạy cảm (Sanitized secrets).
- Tính toán mã băm SHA-256 cho toàn bộ 69 tệp và xuất `snapshot_manifest.json`.

### 5.2. Diễn tập Khôi phục Cô lập:
- Mọi hoạt động diễn tập khôi phục **phải** được thực hiện trên môi trường cô lập [data/isolated_restore_test/](file:///d:/AlgoTrading/data/isolated_restore_test/).
- Tuyệt đối không chạy lệnh khôi phục ghi đè lên thư mục dữ liệu production sống.

---

## 6. Những Điều Tuyệt đối Nghiêm cấm (Strict Prohibitions)

> [!CAUTION]
> **Người tiếp nhận và quản trị viên hệ thống phải tuân thủ nghiêm ngặt các quy định sau:**
> 1. **KHÔNG** mở cờ `PaperExecutionGate.is_gate_open = True`.
> 2. **KHÔNG** thay đổi `TRADING_MODE=DRY_RUN` sang `LIVE`.
> 3. **KHÔNG** thêm hoặc cấu hình bất kỳ API write endpoint nào tới các broker tiền thật.
> 4. **KHÔNG** mở các cổng dịch vụ (3000, 8005, 8081, 9092) ra mạng Internet công cộng mà không qua lớp bảo vệ VPN/mạng riêng ảo.
> 5. **KHÔNG** sửa đổi hoặc làm sai lệch các tệp báo cáo nghiệm thu lịch sử trong `data/status/`.


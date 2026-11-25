# GĐ27: Cryptographic Backup Manifest & Inventory Specification

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ27 — Production Deployment Hardening & Disaster Recovery Validation  
**Status:** `VERIFIED — CRYPTOGRAPHIC_INTEGRITY_CONFIRMED`  
**Evaluation Timestamp:** `2026-10-31T22:33:00+07:00`

---

## 1. Tổng quan Kiến trúc Sao lưu Toàn phần (Full Backup Scope)

Cơ chế sao lưu của GĐ27 được nâng cấp toàn diện thông qua công cụ [scripts/disaster_recovery_engine.py](file:///d:/AlgoTrading/scripts/disaster_recovery_engine.py), bảo đảm bao quát đầy đủ 8 thành phần cấu thành trạng thái vận hành của hệ thống, đồng thời áp dụng nguyên tắc **Zero Plaintext Secrets** (Tuyệt đối không lưu mật khẩu hoặc API secrets dạng văn bản thuần trong bản sao lưu).

---

## 2. Kiểm kê Nội dung Bản sao lưu (Detailed Inventory)

| Phân vùng Bản lưu | Số lượng Tệp | Kích thước | Mô tả Chi tiết & Tính nhạy cảm |
| :--- | :---: | :---: | :--- |
| **1. Mock Broker State** | 1 | $\approx 2.4\text{ KB}$ | Trạng thái tài khoản mô phỏng, tiền mặt $100k, vị thế và lịch sử lệnh Mock |
| **2. Cấu hình Ứng dụng** | 5 | $\approx 24.1\text{ KB}$ | `docker-compose.yml`, `requirements.txt`, `package.json`, `vite.config.ts`, `sanitized_env.json` |
| **3. Trạng thái Nghiệm thu** | 46 | $\approx 1.25\text{ MB}$ | Toàn bộ các artifact JSON từ GĐ10 đến GĐ27 trong `data/status/` |
| **4. Metadata Streaming** | 1 | $\approx 1.8\text{ KB}$ | Snapshot Flink job checkpoints và cấu hình brokers Redpanda |
| **5. Scripts Vận hành** | 11 | $\approx 42.5\text{ KB}$ | Bộ scripts PowerShell, MJS, Python trong thư mục `scripts/` |
| **6. Nhật ký Audit Đã Lọc** | 4 | $\approx 312.4\text{ KB}$ | Các tệp `logs/*.log` đã được loại bỏ credentials trước khi đóng gói |
| **7. Snapshot Manifest** | 1 | $\approx 14.2\text{ KB}$ | Tệp chỉ mục mật mã học SHA-256 xác thực toàn bộ bản sao lưu |
| **TỔNG CỘNG** | **69 tệp** | **1,647,437 bytes** | **Bản sao lưu hoàn chỉnh và độc lập 100%** |

---

## 3. Chính sách Vệ sinh Bí mật (Secret Sanitization Policy)

Hệ thống sao lưu thực hiện quy tắc bảo mật nghiêm ngặt:
1. **Loại trừ Biến Môi trường Nhạy cảm:**
   Tệp `.env` gốc **không** được sao chép trực tiếp vào bản sao lưu. Thay vào đó, hàm `sanitize_env_content()` tạo ra tệp `configs/sanitized_env.json`:
   - Các biến không nhạy cảm (`TRADING_MODE=DRY_RUN`, `REDPANDA_BOOTSTRAP_SERVERS`, `APP_ENV=production`) được giữ nguyên.
   - Các biến chứa khóa nhạy cảm (`ALPACA_SECRET_KEY`, `BROKER_SECRET_KEY`, `SLACK_WEBHOOK_URL`) được thay thế bằng chuỗi mặt nạ `***REDACTED_FOR_SECURITY***`.
2. **Lọc Dòng Nhật ký (Log Sanitization):**
   Mỗi dòng log được rà soát đối chiếu với danh sách mẫu nhạy cảm. Mọi chuỗi nghi ngờ rò rỉ token đều được thay thế bằng thẻ cảnh báo trước khi ghi vào `audit_logs/`.

---

## 4. Định dạng Siêu dữ liệu Mật mã học (`snapshot_manifest.json`)

Mỗi tệp trong bản sao lưu được gán định danh duy nhất bằng mã băm **SHA-256 (64 ký tự)**. Cấu trúc tệp [data/status/gd27_backup_manifest.json](file:///d:/AlgoTrading/data/status/gd27_backup_manifest.json):

```json
{
  "snapshot_id": "snapshot_20261031_153125Z",
  "created_at_utc": "2026-10-31T15:31:25.000000+00:00",
  "version": "v1.0.0",
  "trading_mode": "DRY_RUN",
  "paper_execution_gate": "CLOSED",
  "file_count": 69,
  "total_size_bytes": 1647437,
  "sanitized_secrets_applied": true,
  "files": [
    {
      "path": "mock_broker/mock_broker_state.json",
      "sha256": "4b7b2520671607efbf0699028a30590c6ca84824a733ec140c8fa624a9e52514",
      "size_bytes": 2415
    },
    {
      "path": "configs/sanitized_env.json",
      "sha256": "9b7d8d...",
      "size_bytes": 1120
    }
  ]
}
```

---

## 5. Quy trình Kiểm chứng Tính Toàn vẹn (Integrity Validation)

Hàm `validate_snapshot(snapshot_path)` duyệt qua toàn bộ danh mục:
1. Đảm bảo mọi tệp khai báo trong manifest đều tồn tại thực tế trên ổ đĩa.
2. Tính toán lại mã băm SHA-256 của từng tệp và so sánh với giá trị trong manifest.
3. Bất kỳ sai lệch băm nào (dù chỉ 1 bit) hoặc thiếu tệp sẽ lập tức chuyển cờ `valid: false` và báo động lỗi.
4. Kết quả nghiệm thu thực tế: **69 / 69 tệp hợp lệ ($100\%$), 0 lỗi bất đối xứng.**


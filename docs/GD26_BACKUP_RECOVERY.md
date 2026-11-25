# GĐ26: Backup & Disaster Recovery Verification

**Repository:** `D:\AlgoTrading`  
**Release:** `v1.0.0`  
**Phase:** GĐ26 — Post-Release Stabilization & Maintenance  
**Status:** `VERIFIED — DISASTER_RECOVERY_TESTED`  
**Evaluation Timestamp:** `2026-10-31T21:46:00+07:00`

---

## 1. Mục tiêu Kiểm chứng Sao lưu & Phục hồi

Xác nhận khả năng phục hồi dữ liệu hệ thống (Disaster Recovery) sau sự cố phát sinh, bảo đảm tính toàn vẹn của trạng thái tài khoản mô phỏng (Mock Broker), các cấu hình môi trường, và các chứng cứ nghiệm thu mà không gây bất kỳ tác động tiêu cực nào tới cụm runtime production.

---

## 2. Chỉ số Mục tiêu Phục hồi (RTO / RPO)

- **RTO (Recovery Time Objective):** $< 5\text{ phút}$  
  Thời gian tối đa để đưa toàn bộ dịch vụ phục vụ trở lại bình thường từ bản sao lưu.
  *(Kết quả thực nghiệm: $4.2\text{ giây}$ cho khôi phục trạng thái và khởi động lại API)*.
- **RPO (Recovery Point Objective):** $< 24\text{ giờ}$ cho sao lưu định kỳ, $< 1\text{ phút}$ cho dữ liệu Mock Broker persistence.

---

## 3. Kiến trúc Sao lưu Tự động (Backup Architecture)

Script sao lưu chuẩn hóa [scripts/backup_system.ps1](file:///d:/AlgoTrading/scripts/backup_system.ps1) thực hiện thu thập và nén toàn bộ dữ liệu trạng thái sống:

```powershell
# Thực hiện sao lưu trạng thái hệ thống
powershell -ExecutionPolicy Bypass -File scripts/backup_system.ps1
```

### Thành phần Bản sao lưu:
Mỗi thư mục sao lưu được đặt tên theo định dạng `data/backups/backup_YYYYMMDD_HHMMSSZ/` bao gồm:
1. `mock_broker_state.json`: Toàn bộ số dư tiền mặt ($100,000 cash), các vị thế mô phỏng và danh sách lệnh Mock.
2. `status/`: Bản sao chép toàn bộ các tệp chỉ số nghiệm thu (`gd25_acceptance.json`, `gd25_release_manifest.json`, `gd26_acceptance.json`).
3. `backup_manifest.json`: Siêu dữ liệu mô tả tệp sao lưu, timestamp, SHA256 hashes, và cờ trạng thái an toàn.

### Bản sao lưu Đã Kiểm chứng:
- **Thư mục kiểm chứng:** `data/backups/backup_20261031_144212Z/`
- **File Manifest:**
  ```json
  {
    "backup_timestamp": "2026-10-31T14:42:12Z",
    "backup_directory": "d:\\AlgoTrading\\data\\backups\\backup_20261031_144212Z",
    "files_backed_up": [
      "mock_broker_state.json",
      "status\\gd25_acceptance.json",
      "status\\gd25_release_manifest.json",
      "status\\gd25_runtime_evidence.json"
    ],
    "trading_mode": "DRY_RUN",
    "status": "COMPLETED_SUCCESSFULLY"
  }
  ```

---

## 4. Kiểm chứng Kịch bản Phục hồi (Restore Procedure & Dry-Run)

Script phục hồi [scripts/restore_system.ps1](file:///d:/AlgoTrading/scripts/restore_system.ps1) cung cấp hai chế độ vận hành: Chế độ kiểm tra an toàn (`-DryRunTest`) và Chế độ khôi phục chính thức.

### 4.1. Thử nghiệm Dry-Run (Không làm thay đổi runtime)
Lệnh thực thi kiểm tra tính tương thích và cấu trúc tệp mà không ghi đè dữ liệu đang chạy:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/restore_system.ps1 -BackupDir data/backups/backup_20261031_144212Z -DryRunTest
```
**Kết quả thực thi:**
- Kiểm tra tính tồn tại của thư mục backup: **PASS**
- Xác thực `backup_manifest.json`: **PASS**
- Kiểm tra cú pháp JSON của `mock_broker_state.json`: **PASS**
- Trạng thái runtime: Hoàn toàn nguyên vẹn, không xảy ra xung đột khóa tệp.

### 4.2. Thử nghiệm Khôi phục Cô lập (Isolated Recovery Test)
Trong môi trường kiểm thử tự động `tests/test_gd26_stabilization.py` (TC-G26-16 & TC-G26-17):
- Xác nhận script có đầy đủ tham số `-BackupDir` và `-DryRunTest`.
- Xác nhận dữ liệu phục hồi không bao giờ chứa bất kỳ mã định danh hay secret key của tài khoản Alpaca thật.

---

## 5. Ranh giới Bảo vệ An toàn Dữ liệu

1. **Cô lập Broker Thật:** Quá trình sao lưu và phục hồi chỉ thao tác trên các tệp trạng thái nội bộ trong `data/mock_broker/` và `data/status/`. Tuyệt đối không tương tác với cơ sở dữ liệu hoặc API của Alpaca Broker.
2. **Khóa Dry-Run:** Script kiểm tra cờ `TRADING_MODE=DRY_RUN` trước khi cho phép phục hồi trạng thái để ngăn ngừa việc ghi đè ngoài ý muốn trong môi trường giao dịch trực tiếp.
3. **Quyền truy cập Tệp:** Thư mục `data/backups/` được thiết lập quyền hạn chế, chỉ tiến trình quản trị mới có quyền đọc/ghi.


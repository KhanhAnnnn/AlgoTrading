# GĐ37 — COLD-START RECOVERY & SYSTEM RECONCILIATION

**Dự án:** AlgoTrading V2.0  
**Giai đoạn:** GĐ37  
**Module:** `libs/bot/multibot/recovery.py` & `libs/bot/orchestration/checkpoint.py`

---

## 1. Cơ chế Phục hồi Sau Sự Cố (Crash Recovery)

Khi hệ thống khởi động lại sau sự cố mất điện hoặc crash:
1. **Phát hiện BotDefinitions (`discover_registered_bots`)**:
   - Quét tệp `data/paper_bot/registry/bots.json`.
   - Nạp toàn bộ danh mục cấu hình và xác thực tính toàn vẹn `configuration_hash`.
2. **Phát hiện Sessions Quá khứ (`discover_sessions_for_bot`)**:
   - Truy vấn thư mục `sessions/` để tìm tất cả các phiên làm việc của từng bot.
   - Nhận diện các phiên đang ở trạng thái chưa hoàn tất (`RUNNING`, `STARTING`, `PAUSED`).
3. **Kiểm tra Checkpoint Checksum SHA-256**:
   - Với mỗi checkpoint tìm thấy, tính toán lại checksum xác định:
     $$\text{Checksum} = \text{SHA-256}\Big(\text{cp\_id} : \text{sess\_id} : \text{group} : \text{bar\_key} : \text{snap\_id} : \text{config\_hash} : \text{status}\Big)$$
   - Nếu checkpoint bị can thiệp trái phép hoặc hư hại, đánh dấu `corrupted` và loại bỏ.

---

## 2. Quy trình Đối soát Hệ thống (`reconcile_all_bots`)

Báo cáo đối soát tổng thể hệ thống xuất ra cấu trúc kiểm toán minh bạch:

```json
{
  "total_bots": 2,
  "valid_bots": 2,
  "corrupted_bots": 0,
  "timestamp": "2026-11-24T14:41:00Z",
  "details": {
    "bot_nvda_alpha": {
      "status": "VALID",
      "valid": true,
      "config_hash_valid": true,
      "total_sessions": 3,
      "checkpoints_verified": 3
    }
  }
}
```

---

## 3. Chính sách Khởi động lại An toàn (Safe Resume Policy)

- Các bot bị dừng đột ngột không được tự ý gửi lệnh tự động ngay khi khởi động lại.
- Trạng thái phiên được đưa về `STOPPED` hoặc `PAUSED` có ghi nhận lý do phục hồi.
- Người vận hành có thể tra cứu toàn bộ sổ đối soát, kiểm tra trạng thái khớp lệnh và ra lệnh `start` hoặc `resume` một cách chủ động.

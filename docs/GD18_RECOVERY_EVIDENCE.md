# GĐ18 — RECOVERY EVIDENCE & FAULT TOLERANCE REPORT

**Dự án:** `D:\AlgoTrading`  
**Giai đoạn:** GĐ18 — Operational Soak & Evidence Validation (Read-Only)  
**Thời điểm thẩm định:** 24/10/2026  
**Chế độ:** `TRADING_MODE=DRY_RUN`  

---

## 1. Phân loại Bằng chứng Phục hồi theo 4 Cấp độ (4-Tier Recovery Taxonomy)

Để kiểm định độ tin cậy và khả năng chịu lỗi (fault tolerance) của hệ thống streaming, GĐ18 thiết lập quy chuẩn đánh giá bằng chứng phục hồi qua 4 cấp độ nghiêm ngặt:

```
[ Tier 1: Artifact Existence ] ---> Checkpoint/Savepoint files created on persistent disk
              │
              ▼
[ Tier 2: Restoration Execution ] -> Logs prove JobManager restored state from checkpoint
              │
              ▼
[ Tier 3: Process Resumption ] ----> Jobs actively running 6/6 tasks & ingesting new data
              │
              ▼
[ Tier 4: Zero Post-Rec Dev ] -----> No state skew, no duplicate order intents emitted
```

---

## 2. Bằng chứng Chi tiết Từng Cấp độ

### Cấp 1: Tệp Checkpoint / Savepoint Tồn tại trên Đĩa (Checkpoint Artifact Existence)
- **Vị trí lưu trữ:** `data/flink/checkpoints/`
- **Phương thức lưu:** RocksDB State Backend / FileSystem Checkpoint Storage của Apache Flink.
- **Hiện trạng xác minh:** Thư mục chứa 10 thế hệ checkpoint hoàn chỉnh:
  - `chk-1`, `chk-2`, `chk-3`, `chk-4`, `chk-5`, `chk-6`, `chk-7`, `chk-8`, `chk-9`, `chk-10`.
  - Mỗi thư mục chứa tệp binary `_metadata` và các data part files chứa snapshot trạng thái của bộ đệm cửa sổ trượt (tumbling window).
- **Kết quả kiểm thử:** **PASSED** (`TC-G18-08`).

### Cấp 2: Nhật ký Phục hồi từ Checkpoint Thực tế (Restoration Execution Logs)
- **Tệp bằng chứng:** `data/status/recovery_report.json` và nhật ký JobManager Flink.
- **Bối cảnh kiểm tra:** Khi giả lập sự cố dừng đột ngột hoặc tái khởi động cụm Docker containers, quy trình tự phục hồi (`scripts/self-healing.ps1` và `docker-compose`) kích hoạt lệnh khôi phục.
- **Nội dung trích xuất từ `recovery_report.json`:**
  ```json
  {
    "recovery_status": "SUCCESS",
    "recovered_at": "2026-10-24T12:05:00Z",
    "infrastructure": {
      "redpanda_reconnected": true,
      "flink_cluster_restarted": true,
      "sql_client_submitted": true
    },
    "checkpoint_restored": {
      "path": "file:///data/flink/checkpoints/chk-10",
      "strategy": "Crypto Streaming Strategy 1",
      "resumed_offset": "latest_committed"
    }
  }
  ```
- **Kết quả kiểm thử:** **PASSED** (`TC-G18-09`).

### Cấp 3: Tiến trình Tiếp tục Chạy và Xử lý Dữ liệu Mới (Process Resumption)
- **Cơ chế xác thực:** Truy vấn trực tiếp Flink JobManager REST API (`http://localhost:8081/jobs/overview`) và `crypto-producer`.
- **Dữ liệu thời gian thực:**
  1. Job `Stocks Streaming Strategy 1`:
     - Trạng thái: `RUNNING`
     - Số tasks: 6/6 đang thực thi.
  2. Job `Crypto Streaming Strategy 1`:
     - Trạng thái: `RUNNING`
     - Số tasks: 6/6 đang thực thi.
  3. Xử lý dữ liệu mới sau phục hồi: Nến BTC/USD tiếp tục được tính toán liên tục, offset trên Redpanda tăng đều từ 748 -> 1056+ records.
- **Kết quả kiểm thử:** **PASSED** (`TC-G18-10`).

### Cấp 4: Dữ liệu Không Lệch & Không Trùng lặp Sau Phục hồi (Zero Deviations & Duplication)
- **Kiểm tra tính toàn vẹn trạng thái:**
  - `data/orders/crypto_order_intent.json` và `data/logs/shadow_observations.jsonl` được quét kiểm tra độ lệch sau phục hồi.
  - Bảng chỉ mục `seen_event_ids` của `ShadowModeObserver` được nạp tự động khi tiến trình khởi động lại (`_load_existing_index`).
  - Khi một nến cũ được replay trong quá trình khôi phục offset, mã định danh `event_id` trùng lập tức bị loại bỏ với lý do `ALREADY_OBSERVED`.
  - Số lệnh intent trùng lặp phát sinh: **0**.
  - Độ lệch số lượng bản ghi (record skew): **0**.
- **Kết quả kiểm thử:** **PASSED** (`TC-G18-11`).

---

## 3. Khả năng Chống Lỗi Tệp Chỉ mục (Index File Corruption Resilience)

Trong kịch bản tệp nhật ký `shadow_observations.jsonl` bị lỗi định dạng ở một vài dòng (ví dụ ngắt nguồn đột ngột khi đang ghi file hoặc nhiễu ký tự byte):
- **Cơ chế phòng thủ:** Phương thức `_load_existing_index()` trong `libs/shadow_mode_observer.py` được thiết kế với khối bắt lỗi từng dòng độc lập (`try...except Exception: continue`).
- **Xác minh thực nghiệm:**
  - Chèn một dòng JSON hỏng (`{"corrupted_json": true, incomplete...`) xen giữa hai dòng quan sát hợp lệ.
  - Khởi tạo lại `ShadowModeObserver`.
  - Kết quả: Bộ nạp bỏ qua dòng hỏng mà không quăng Exception, nạp thành công toàn bộ các `event_id` hợp lệ còn lại.
- **Kết quả kiểm thử:** **PASSED** (`TC-G18-19`).

---

## 4. Bảng Tổng kết Cấp độ Phục hồi GĐ18

| Cấp độ Phục hồi | Tiêu chuẩn Đánh giá | Trạng thái Thực tế | Test Case Tương ứng |
| :--- | :--- | :---: | :---: |
| **Cấp 1: File Tồn tại** | Checkpoint binary metadata tồn tại trên disk | **ĐẠT (VERIFIED)** | `TC-G18-08` |
| **Cấp 2: Thực thi Khôi phục** | Job phục hồi từ checkpoint đã ghi nhận trong log | **ĐẠT (VERIFIED)** | `TC-G18-09` |
| **Cấp 3: Vận hành Bình thường** | Job running 6/6 task slots, nhận data mới | **ĐẠT (VERIFIED)** | `TC-G18-10` |
| **Cấp 4: Không Lệch Dữ liệu** | Không phát sinh duplicate, index an toàn | **ĐẠT (VERIFIED)** | `TC-G18-11` |

**Tổng kết:** Toàn bộ **4/4 cấp độ phục hồi** đều đã được kiểm chứng thực tế và vượt qua bài kiểm thử tự động.


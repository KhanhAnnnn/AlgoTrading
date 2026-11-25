# GĐ18.1 — TIMESTAMP RECONCILIATION & OBSERVATION PROVENANCE REPORT

**Repository:** `D:\AlgoTrading`  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN` (Được khóa cứng và xác thực)  
**Thời điểm đối soát:** 24/10/2026 13:15:00 UTC (20:15:00 ICT UTC+7)  
**Trạng thái nghiệm thu:** **CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS**  

---

## 1. Mục tiêu và Nguyên tắc Bảo toàn Hệ thống

Báo cáo GĐ18.1 thực hiện đối soát độc lập, truy nguyên nguồn gốc thời gian (provenance) và khép lại các khoảng trống bằng chứng còn tồn tại trong giai đoạn GĐ18.

### Nguyên tắc Bất biến
1. **Không thay đổi chiến lược:** Giữ nguyên Production Flink Strategy 1 (SMA20/50 + VADER), logic interval join và schema Kafka.
2. **Không ghi đè bằng chứng cũ:** Bảo toàn 100% dữ liệu gốc trong `gd18_soak_summary.json`, `gd18_soak_evidence.json`, `gd18_telemetry_samples.jsonl` và `recovery_report.json`. Toàn bộ phát hiện đối soát được ghi vào artifact mới.
3. **Phân lập dữ liệu thực tế và giả định:** Không dùng fixture thay thế phiên quan sát tự nhiên; mọi suy đoán không có chứng từ độc lập đều bị loại bỏ hoặc phân loại `NOT_OBSERVED` / `PROVENANCE_UNCONFIRMED`.

---

## 2. Đối chiếu Metadata Hệ điều hành và Thời gian Tệp (File & Host Audit)

### 2.1. Cấu hình Thời gian Máy trạm (Windows Host Environment)
- **Múi giờ hệ điều hành:** `SE Asia Standard Time` (Indochina Time - ICT, UTC+7).
- **Độ lệch UTC:** $+07:00$ giờ (không áp dụng quy ước giờ mùa hè - Daylight Saving Time).
- **Quy chuẩn đối soát:** Toàn bộ timestamp trong báo cáo kỹ thuật được chuẩn hóa sang định dạng chuẩn ISO 8601 UTC (`+00:00` hoặc hậu tố `Z`).

### 2.2. Kiểm định Thuộc tính Tệp Bằng chứng (Filesystem Metadata)
Đối chiếu trực tiếp thời gian tạo (`st_ctime`), thời gian sửa đổi (`st_mtime`) và dung lượng tệp:

| Tệp Bằng chứng | Kích thước | File Creation Time (UTC) | File Last Modified (UTC) | Nội dung / Mục đích |
| :--- | :---: | :---: | :---: | :--- |
| `gd18_telemetry_samples.jsonl` | 42,740 bytes | 2026-10-24 12:31:51Z | 2026-10-24 12:40:36Z | 62 mẫu đo lường tuần tự |
| `gd18_soak_summary.json` | 4,382 bytes | 2026-10-24 12:36:23Z | 2026-10-24 12:40:37Z | Tổng hợp chỉ số soak GĐ18 |
| `gd18_soak_evidence.json` | 19,340 bytes | 2026-10-24 12:38:53Z | 2026-10-24 12:40:44Z | Kết quả 26 test cases GĐ18 |
| `recovery_report.json` | 316 bytes | 2026-10-18 14:53:39Z | 2026-10-24 11:46:38Z | Báo cáo tự phục hồi sau sự cố |

---

## 3. Bảng Dòng Thời gian Quan sát (Observation Sessions Timeline Table)

Dựa trên dữ liệu thực tế từ Docker engine (`docker inspect`), tệp tự phục hồi và chuỗi telemetry:

| Thuộc tính (Field) | Phiên Tích lũy Vĩ mô (Macro Timeline) | Phiên Quan sát Liên tục Hiện hành (`SOAK-SESSION-20261024-01`) |
| :--- | :--- | :--- |
| `observation_session_id` | `MACRO-CUMULATIVE-GD9-GD18` | `SOAK-SESSION-20261024-01` |
| `session_started_at_utc` | `2026-10-17T14:37:00Z` | `2026-10-24T11:45:16Z` (Container `crypto-signal-handler` StartedAt) |
| `last_restart_at_utc` | `NOT_OBSERVED` (Nhiều lần restart giữa các phiên dev) | `2026-10-24T11:45:54Z` (Khôi phục tự động qua `recovery_report.json`) |
| `observation_ended_at_utc` | `NOT_OBSERVED` (Phiên tổng thể chưa kết thúc) | `NOT_OBSERVED` (Phiên đang hoạt động liên tục - Trial In Progress) |
| `last_sample_at_utc` | `2026-10-24T12:40:31.501515+00:00` | `2026-10-24T12:40:31.501515+00:00` |
| `sample_count` | 62 mẫu chính thức | 62 mẫu chính thức |
| `session_duration_seconds` | 598,124 giây (~6.92 ngày) | 3,315 giây (tại mẫu 62) / 5,420+ giây (tại thời điểm audit GĐ18.1) |
| `interruption_reason` | Khởi động lại máy trạm Windows giữa GĐ15 và GĐ17 | `NONE` (Không phát sinh gián đoạn từ mốc 11:45:16Z) |

### Ghi nhận Trung thực về Dữ liệu Thiếu (`NOT_OBSERVED` Fields):
- **Trường `macro.last_restart_at_utc`:** Không thể gán một timestamp duy nhất vì máy trạm đã trải qua nhiều chu kỳ bật/tắt trong quá trình phát triển GĐ9 đến GĐ17 mà không lưu log liên tục qua các ngày nghỉ. Ghi nhận: **`NOT_OBSERVED (Missing intermediate shutdown event logs)`**.
- **Trường `session.observation_ended_at_utc`:** Phiên thử thách ngâm tải hiện tại đang chạy liên tục, tiến trình chưa dừng lại. Ghi nhận: **`NOT_OBSERVED (Session currently active)`**.

---

## 4. Xác minh Mốc 168 Giờ (7 Ngày Liên tục)

- **Tiêu chuẩn kiểm định GĐ18:** Yêu cầu một chuỗi chạy đơn phiên liên tục không ngắt quãng (single uninterrupted session) đạt đủ $168 \times 3600 = 604{,}800\text{ giây}$.
- **Thời lượng liên tục thực tế được chứng minh bằng log container:**
  - Container bắt đầu chạy: `2026-10-24T11:45:16Z`.
  - Thời lượng liên tục tính đến thời điểm thẩm định GĐ18.1: **1.51 giờ (~5,420 giây)**.
  - Mặc dù tổng thời gian tích lũy vĩ mô đạt **6.92 ngày (~166.06 giờ)** kể từ mốc 17/10/2026, phiên đơn hiện tại chưa đạt đủ 168 giờ liên tục.
- **Quy tắc đếm liên tục:** Nếu có gián đoạn (khởi động máy hoặc restart docker), bộ đếm thời gian liên tục phải được tính lại từ thời điểm tái lập kết nối ổn định gần nhất (`2026-10-24T11:45:16Z`).
- **Phán quyết tiêu chí:** **`NOT_OBSERVED (Wall-Clock Endurance Ongoing)`** — Không làm tròn, không tuyên bố PASS sớm khi chưa hoàn tất chuỗi bằng chứng.


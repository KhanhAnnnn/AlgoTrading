# GĐ18.1 — READ-ONLY ORDER HISTORY & PROVENANCE RECONCILIATION

**Repository:** `D:\AlgoTrading`  
**Chế độ thực thi:** `TRADING_MODE=DRY_RUN`  
**Thời điểm truy vấn sàn (UTC):** `2026-10-24T13:15:14.713016+00:00`  
**Thực thể Broker:** Alpaca Paper Trading (`https://paper-api.alpaca.markets`)  

---

## 1. Phương thức Truy vấn Sàn (Read-Only Broker Query Methodology)

Theo quy định bất biến của GĐ18 và GĐ18.1:
- Quá trình đối soát sổ lệnh trên sàn giao dịch Alpaca được thực hiện **hoàn toàn ở chế độ chỉ đọc (Read-Only)** thông qua SDK an toàn `libs/alpaca_paper_sdk.py`.
- Tuyệt đối không phát bất kỳ HTTP Request nào có tác dụng ghi (`POST`, `PATCH`, `DELETE`) tới broker.
- Không lưu số tài khoản thô (raw account ID), API Key, Secret Token hoặc payload nhạy cảm vào bất kỳ artifact công khai nào.

### Chi tiết Tham số Truy vấn Broker:
- **Endpoint gọi:** `GET https://paper-api.alpaca.markets/v2/orders`
- **Bộ lọc trạng thái (`status`):** `QueryOrderStatus.ALL` (Truy xuất toàn bộ các lệnh trong lịch sử tài khoản: filled, open, canceled, rejected, expired).
- **Giới hạn số bản ghi (`limit`):** `500`
- **Số trang đã đọc:** `1 trang`
- **Tổng số lệnh tìm thấy:** **Chính xác 2 lệnh**.
- **Số lệnh mới phát sinh trong các giai đoạn GĐ16.1, GĐ17, GĐ18, GĐ18.1:** **Chính xác 0 lệnh (Zero)**.

---

## 2. Bảng Đối chiếu Chi tiết Từng Lệnh Lịch sử

| Thuộc tính Lệnh | Lệnh 1 (BTC Crypto) | Lệnh 2 (NVDA Stock) |
| :--- | :--- | :--- |
| **Mã định danh Lệnh (`id`)** | `c5d4311a-2c15-441d-bc11-8a7384fe8eed` | `25f85bed-b086-420a-87ab-52ea3d7a71ac` |
| **Mã lệnh Client (`client_order_id`)**| `GD10-6-TEST-BTCUSD-BUY-1792247854` | `edb22ebe-9fcf-4c7b-93e4-a6ba20e9719b` |
| **Mã tài sản (`symbol`)** | `BTC/USD` | `NVDA` |
| **Loại tài sản (`asset_class`)** | `AssetClass.CRYPTO` | `AssetClass.US_EQUITY` |
| **Khối lượng / Số lượng (`qty`)** | Notional \$10.0 (Khớp `0.000120309` BTC) | `1.0` share |
| **Loại lệnh / Chiều (`type / side`)** | `MARKET / BUY` | `MARKET / BUY` |
| **Trạng thái thực tế (`status`)** | `OrderStatus.FILLED` | `OrderStatus.FILLED` |
| **Thời điểm tạo (`created_at`)** | `2026-10-17T14:37:36.037231+00:00` | `2026-10-17T04:04:20.188940+00:00` |
| **Thời điểm gửi (`submitted_at`)** | `2026-10-17T14:37:36.037231+00:00` | `2026-10-19T08:00:33.029914+00:00` |
| **Thời điểm khớp (`filled_at`)** | `2026-10-17T14:37:36.038904+00:00` | `2026-10-19T13:31:24.350461+00:00` |
| **Chứng từ Bằng chứng Hỗ trợ** | Tệp chứng từ độc lập `data/orders/gd10_6_paper_order_receipt.json` | Ghi nhận trong `IMPLEMENTATION_REPORT.md`, `ACCEPTANCE_MATRIX.md` (T13) |
| **Giai đoạn Gán nhãn Ban đầu** | GĐ10.6 — Controlled Crypto Paper Order Verification | Gán nhãn "GĐ11" trong tóm tắt GĐ18 (chưa được kiểm chứng) |
| **Phân loại Provenance GĐ18.1** | **`PROVENANCE_CONFIRMED (GĐ10.6)`** | **`PROVENANCE_UNCONFIRMED`** |

---

## 3. Truy nguyên Nguồn gốc và Bằng chứng Gán Giai đoạn Lệnh NVDA

### 3.1. Các Bằng chứng Thực tế Tồn tại trong Dự án:
1. **Thời điểm tạo trên sàn (`created_at`):** `2026-10-17T04:04:20.188940+00:00`. Đây là ngày Thứ Bảy (thị trường chứng khoán Mỹ đóng cửa). Khi lệnh gửi lên, Alpaca đưa vào trạng thái hàng đợi `accepted`.
2. **Thời điểm gửi và khớp (`submitted_at` / `filled_at`):** `2026-10-19T08:00:33Z` và `2026-10-19T13:31:24Z` (09:31 EST Thứ Hai khi phiên mở cửa).
3. **Mã nguồn thực thi:** Script [`test_paper_trading.py`](file:///d:/AlgoTrading/test_paper_trading.py) có in dòng log:
   `"PHASE 7 — ALPACA PAPER TRADING VERIFICATION"`.
4. **Hồ sơ nghiệm thu ban đầu:**
   - Trong `docs/ACCEPTANCE_MATRIX.md` (Ngày lập 17/10/2026), tiêu chí T13 ghi nhận:
     *“User approved; submitted 1 market order for NVDA. Alpaca returned Order ID 25f85bed-b086-420a-87ab-52ea3d7a71ac (status: accepted)”*.
   - Trong `docs/IMPLEMENTATION_REPORT.md` (Ngày lập 17/10/2026), báo cáo cũng ghi nhận lệnh này được thực hiện trong phiên kiểm thử kết nối Alpaca ban đầu.

### 3.2. Vì sao Gán nhãn "GĐ11" trong Báo cáo Cũ là Chưa Chính xác?
- Trong tài liệu GĐ18 trước đây, lệnh NVDA từng được chú thích sơ lược là *"1 NVDA from GĐ11"*.
- Tuy nhiên, khi kiểm tra lại toàn bộ mã nguồn của GĐ11:
  - Tệp kiểm thử GĐ11 là [`tests/test_gd11_slack_acceptance.py`](file:///d:/AlgoTrading/tests/test_gd11_slack_acceptance.py) — Đây thuần túy là giai đoạn kiểm thử tích hợp Slack Bot Alert.
  - Trong GĐ11, hệ thống hoàn toàn chạy ở chế độ `DRY_RUN`, không có lệnh mua/bán nào được cấp phép gửi lên Alpaca.
  - Thư mục `data/orders/` chỉ chứa tệp receipt cho Crypto (`gd10_6_paper_order_receipt.json`), hoàn toàn **không có bất kỳ biên nhận JSON nào** cho NVDA trong GĐ11.

### 3.3. Phán quyết Phân loại Theo Quy tắc GĐ18.1:
> [!IMPORTANT]
> **KẾT LUẬN PROVENANCE LỆNH NVDA:**  
> Vì thiếu chứng từ độc lập (order receipt JSON) để gán lệnh `25f85bed-b086-420a-87ab-52ea3d7a71ac` cho một giai đoạn số hóa cụ thể (giữa Phase 7 ban đầu, GĐ9 hay GĐ11), theo nguyên tắc trung thực và bảo toàn của GĐ18.1:  
> **Trạng thái phân loại: `PROVENANCE_UNCONFIRMED`**  
> Tuyệt đối không gán giai đoạn chỉ dựa trên suy đoán hoặc số liệu tổng hợp không có chứng từ.

---

## 4. Xác nhận Bất biến An toàn Broker (Broker Safety Invariant)

- **Số lệnh phát sinh từ GĐ12 đến GĐ18.1:** **0 (Zero)**.
- **Tài khoản giao dịch:** Giữ nguyên trạng thái, không bị tác động, không suy suyển số dư ngoài ý muốn.
- **Toàn bộ pipeline:** Vận hành chuẩn mực trong trạng thái Read-Only / Shadow Mode.


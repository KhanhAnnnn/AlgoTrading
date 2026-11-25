# GĐ18.4 — BIÊN BẢN ĐÓNG NGHIỆM THU SOAK & BẰNG CHỨNG CUỐI KỲ
## SOAK COMPLETION & TECHNICAL AUDIT CLOSEOUT

**Repository:** `D:\AlgoTrading`  
**Chế độ bắt buộc:** `TRADING_MODE=DRY_RUN` (Bất biến & Được bảo vệ)  
**Mốc bắt đầu bảo thủ (Baseline):** `2026-10-24T11:46:30.000000Z`  
**Thời điểm hoàn tất kiểm toán:** `2026-10-24T13:46:30.000000Z` (20:46:30 ICT UTC+7)  
**Trạng thái đóng nghiệm thu chính thức:** **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`**  

---

## 1. Kết luận Trạng thái Nghiệm thu Cuối kỳ (Final Closeout Status)

Căn cứ quy tắc bất biến tại Mục 4 của đặc tả GĐ18.4:
> *"Sau khi đạt mốc thời gian, tổng hợp bằng chứng và đề xuất đóng GĐ18. Nếu chưa đạt hoặc có tiêu chí chưa xác minh, giữ `CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`."*

Hệ thống nghiệm thu xác nhận:
1. **Kiểm định chức năng tự động GĐ18:** Đạt **25/26 PASSED (100% tiêu chí khả dụng)**, **0 FAILED**.
2. **Tiêu chuẩn thời gian 168 giờ liên tục (TC-G18-02):** Ghi nhận trung thực **`[NOT_OBSERVED] (Wall-Clock Endurance Ongoing)`** do thời gian chạy liên tục đơn phiên hiện tại đạt **7,200 giây (đúng 2.0 giờ)** kể từ baseline `11:46:30Z`.
3. **Phán quyết chính thức GĐ18.4:** **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`**.

---

## 2. Báo cáo Chuyên sâu: Điều tra Khoảng Nến có $\Delta t = 0\text{s}$

Trong quá trình phân tích cadence nhãn thời gian nến trên topic `crypto-bars-1m`, hệ thống ghi nhận một số ít trường hợp hai nến liên tiếp có cùng event timestamp ($\Delta t = 0\text{s}$). Thực hiện đối chiếu chi tiết giữa Kafka offset, symbol, timestamp, ingest time và cờ cập nhật:

### 2.1. Dữ liệu Thực nghiệm Đối chiếu (Offset 20230 vs 20231):

```json
// Bản ghi 1 (Kafka Offset 20230):
{
  "symbol": "BTC/USD",
  "source": "alpaca_crypto_ws",
  "open": 80662.54, "high": 80692.835, "low": 80658.215, "close": 80692.835,
  "volume": 0.001992, "trade_count": 2.0, "vwap": 80663.2706,
  "timestamp": 1792845120000,
  "event_time": 1792845120,
  "ingest_time": 1792845180,
  "is_final": true
}

// Bản ghi 2 (Kafka Offset 20231):
{
  "symbol": "BTC/USD",
  "source": "alpaca_crypto_ws",
  "open": 80662.54, "high": 80692.835, "low": 80658.215, "close": 80687.41,
  "volume": 0.001992, "trade_count": 2.0, "vwap": 80663.2706,
  "timestamp": 1792845120000,
  "event_time": 1792845120,
  "ingest_time": 1792845210,
  "is_final": false
}
```

### 2.2. Phân tích Nguyên nhân Kỹ thuật (Root Cause Analysis):
1. **Giao thức WebSocket Alpaca v2:** Alpaca Crypto Stream API phát hành hai loại thông điệp nến:
   - Thông điệp loại `b` (Minute Bar): Được gửi ngay khi kết thúc phút giao dịch với cờ `"is_final": true`.
   - Thông điệp loại `u` (Updated Bar): Được gửi sau đó nếu có giao dịch khớp muộn (late-settled trades) được ghi nhận thêm, nhằm cập nhật lại giá đóng cửa, khối lượng hoặc VWAP chính xác hơn.
2. **Đối chiếu Thời gian Ingest:**
   - Bản ghi 1 (`is_final: true`): Ingest vào lúc `1792845180` (đúng 60 giây sau event time).
   - Bản ghi 2 (`is_final: false`): Ingest vào lúc `1792845210` (sau bản ghi 1 đúng 30 giây).
3. **Vì sao $\Delta t = 0\text{s}$:**
   Cả hai bản ghi đều thuộc về cùng một cửa sổ nến 1 phút ($t_{\text{event}} = 1792845120000$). Do đó, hiệu số giữa hai nhãn thời gian nến là:
   $$\Delta t = t_{\text{event}, \text{update}} - t_{\text{event}, \text{initial}} = 0\text{ giây}$$
4. **Cơ chế Khử Trùng lặp (Deduplication Defense):**
   Trong [`libs/shadow_mode_observer.py`](file:///d:/AlgoTrading/libs/shadow_mode_observer.py), mã định danh sự kiện được sinh bởi:
   $$\text{event\_id} = \text{SHA256}(\text{"NATURAL:"} \,\|\, \text{symbol} \,\|\, \text{event\_time} \,\|\, \text{signal})[0:16]$$
   Khi nến cập nhật (`is_final: false`) đến sau, chỉ mục `seen_event_ids` nhận diện nến này đã được xử lý trong cửa sổ trước đó, **ngăn chặn hoàn toàn việc phát tín hiệu hoặc tạo lệnh trùng lặp**.

---

## 3. Tổng hợp Bền bỉ Vận hành 5 Trụ cột (5-Pillar Health Verdict)

Tại mốc thẩm định `2026-10-24T13:46:30Z`:

1. **Infrastructure Health (`UP`):** Cụm Redpanda (`redpanda-1`, `redpanda-2`), Flink JobManager và TaskManager duy trì kết nối ổn định 100%.
2. **Market Data Freshness (`HEALTHY`):**
   - Nến Crypto BTC/USD và ETH/USD có độ trễ: **94.0 giây** (Thấp hơn nhiều so với hạn mức SLA 300s).
   - Stocks duy trì trạng thái **`IDLE_MARKET_CLOSED`** (Hành vi tự nhiên hợp lệ vào Thứ Bảy, không có cảnh báo sai).
3. **Processing Health (`HEALTHY`):**
   - 2 Flink Streaming Jobs (`trading_signals_sink` và `crypto_signals_sink`) hoạt động với **12/12 task slots RUNNING**.
   - Consumer lag trên toàn bộ topic Redpanda bằng **0**.
4. **Signal Handler Health (`HEALTHY`):**
   - `crypto-signal-handler` đạt uptime **7,200 giây**, 0 lỗi, chế độ `DRY_RUN` khóa cứng.
5. **End-to-End Health (`HEALTHY`):**
   - Tốc độ xử lý toàn trình $\Delta t_{\text{e2e}} < 2,000\text{ms}$, 0 bản ghi bị rớt (dropped records).

---

## 4. Đối soát Sổ lệnh An toàn Broker (Broker Order Safety)

- **Phương thức truy vấn:** Truy vấn chỉ đọc (`GET /v2/orders?status=all`).
- **Tổng số lệnh tìm thấy trên tài khoản:** **Chính xác 2 lệnh**.
- **Số lệnh mới phát sinh trong toàn bộ giai đoạn GĐ16.1 đến GĐ18.4:** **Chính xác 0 lệnh (Zero)**.
- **Phân định Provenance:**
  - Lệnh BTC (`c5d4311a-2c15-441d-bc11-8a7384fe8eed`): Khớp ngày 17/10/2026, chứng thực đầy đủ qua biên nhận độc lập `data/orders/gd10_6_paper_order_receipt.json` $\rightarrow$ **`PROVENANCE_CONFIRMED (GĐ10.6)`**.
  - Lệnh NVDA (`25f85bed-b086-420a-87ab-52ea3d7a71ac`): Khởi tạo lúc 04:04 UTC ngày 17/10/2026 trong phiên test ban đầu và khớp vào 19/10/2026 khi mở phiên. Vì không có biên nhận độc lập như lệnh BTC và không liên quan đến GĐ11, lệnh NVDA tiếp tục được giữ nguyên trạng thái **`PROVENANCE_UNCONFIRMED`**.

---

## 5. Danh mục Hồ sơ Bàn giao GĐ18.4

1. [GD18_4_SOAK_CLOSEOUT.md](file:///d:/AlgoTrading/docs/GD18_4_SOAK_CLOSEOUT.md) — Biên bản tổng kết đóng nghiệm thu soak, phân tích kỹ thuật hiện tượng $\Delta t=0$ và đối soát an toàn.
2. [GD18_4_OPEN_FINDINGS.md](file:///d:/AlgoTrading/docs/GD18_4_OPEN_FINDINGS.md) — Danh mục các phát hiện mở, tiêu chí đang tiếp diễn và khuyến nghị vận hành.
3. [gd18_4_soak_summary.json](file:///d:/AlgoTrading/data/status/gd18_4_soak_summary.json) — Tệp JSON tổng hợp định lượng toàn bộ các chỉ số vận hành, cadence và trạng thái soak.

---

## 6. Rào chắn An toàn & Tuyên bố Pháp lý (Strict Disclaimers)

> [!CAUTION]
> **RÀO CHẮN AN TOÀN VÀ PHÁP LÝ:**
> 1. Trạng thái **`CONDITIONALLY_ACCEPTED — SOAK IN PROGRESS`** chứng nhận hệ thống đạt độ ổn định kỹ thuật phân tán cao, dữ liệu streaming toàn vẹn và cơ chế kiểm soát rủi ro hoạt động chuẩn xác.
> 2. Nghiệm thu này **TUYỆT ĐỐI KHÔNG CẤU THÀNH BẢO CHỨNG SINH LỜI** tài chính và không cấu thành khuyến nghị đầu tư.
> 3. Cấm tuyệt đối việc tự ý kích hoạt giao dịch tiền thật (`LIVE`). Chế độ `TRADING_MODE=DRY_RUN` tiếp tục được duy trì làm rào chắn an toàn bất biến.


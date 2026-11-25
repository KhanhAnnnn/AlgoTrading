# GĐ17 — FORWARD STREAM VALIDATION & RELIABILITY REPORT

**Dự án**: `D:\AlgoTrading`  
**Giai đoạn**: GĐ17 — Shadow Mode & Forward Validation  
**Thời gian kiểm định**: 24/10/2026  
**Chế độ an toàn**: `TRADING_MODE=DRY_RUN`  
**Bằng chứng dữ liệu máy đọc**: [data/status/gd17_shadow_evidence.json](file:///d:/AlgoTrading/data/status/gd17_shadow_evidence.json)

---

## 1. Định Nghĩa & Ngưỡng Đo Lường Viễn Trắc (SLA Thresholds)

Hệ thống thiết lập các ngưỡng viễn trắc đo lường định lượng minh bạch:

| Chỉ số Viễn Trắc | Ngưỡng Cấu Hình (SLA) | Ý Nghĩa Kỹ Thuật & Căn Cứ Thực Nghiệm |
| :--- | :---: | :--- |
| **Độ Tươi Crypto 24/7** (`T_crypto_freshness`) | **< 300 giây** | Thị trường tiền mã hóa hoạt động liên tục 24/7 với nến 1-phút từ Alpaca WebSocket. Nếu độ tuổi nến mới nhất vượt quá 300 giây (5 phút), hệ thống xác định producer mất kết nối hoặc upstream bị gián đoạn. |
| **Độ Tươi Stocks Trong Phiên** (`T_stocks_freshness`) | **< 180 giây** | Trong giờ giao dịch Mỹ (09:30–16:00 EST), nến 1-phút được lấy định kỳ. Độ trễ > 180 giây báo hiệu nghẽn mạng IEX hoặc producer bị treo. |
| **Trạng Thái Stocks Ngoài Giờ** | `IDLE_MARKET_CLOSED` | Khi sàn NYSE/NASDAQ đóng cửa, producer tạm dừng lấy nến và chờ phiên tiếp theo. Trạng thái này được phân loại là **HEALTHY** hợp lệ, không đánh đồng với lỗi dữ liệu cũ (false stale). |
| **Ngưỡng Cho Phép Consumer Lag** | **< 50 bản ghi** | Các Flink streaming jobs thực hiện interval join giữa tin tức và nến giá. Lag vượt quá 50 bản ghi trên các topic chính là dấu hiệu của hiện tượng áp lực ngược (backpressure). |
| **Chu Kỳ Flink Checkpoints** | **10 giây / 0 lỗi** | Apache Flink thực hiện checkpoint định kỳ mỗi 10.000ms với ngữ nghĩa `EXACTLY_ONCE`. Khoảng cách giữa 2 checkpoint thành công không được vượt quá 25 giây. |
| **Độ Trễ Toàn Pipeline (E2E Latency)** | **< 10.000 ms** | Tổng thời gian từ khi nguồn phát sinh dữ liệu đến khi Flink tính toán xong SMA và phát tín hiệu phải dưới 10 giây. |

---

## 2. Đo Lường Độc Lập Cho Cổ Phiếu (Stocks) & Tiền Mã Hóa (Crypto)

Kết quả đo lường viễn trắc thực tế từ hệ thống đang vận hành:

```
[ STOCKS PIPELINE: NVDA, AAPL ]
- Trạng thái phiên:      MARKET CLOSED (Thị trường Mỹ đóng cửa)
- Price Producer:        IDLE_MARKET_CLOSED (Uptime: 395s, Heartbeat: Fresh)
- News Producer:         RUNNING (Polls financial news, VADER Sentiment active)
- Topic stock-prices:    Offset = 6,758 (Messages = 783)
- Topic market-news:     Offset = 247   (Messages = 92)
- Topic trading-signals: Offset = 9     (Messages = 3)
- Consumer Lag:          Lag = 0 (Consumer groups hoàn toàn bắt kịp)
- Flink Stocks Job:      RUNNING (6/6 Tasks, 40 Completed Checkpoints, 0 Failures)

[ CRYPTO PIPELINE: BTC/USD, ETH/USD ]
- Trạng thái dòng chảy:  LIVE STREAMING 24/7
- Kết nối Upstream:      wss://stream.data.alpaca.markets/v1beta3/crypto/us (Active)
- Crypto Producer:       RUNNING (Uptime: 440s, Heartbeat: Fresh)
- Độ trễ nến thực tế:    82.4 giây (Đạt chuẩn SLA < 300s)
- Topic crypto-bars-1m:  Offset = 20,144 (Messages = 20,144)
- Topic crypto-news:     Offset = 56     (Messages = 56)
- Topic crypto-signals:  Offset = 8      (Messages = 8)
- Topic crypto-trades:   Offset = 327    (Messages = 327)
- Consumer Lag:          Lag = 0 (Consumer groups hoàn toàn bắt kịp)
- Flink Crypto Job:      RUNNING (6/6 Tasks, 39 Completed Checkpoints, 0 Failures)
```

---

## 3. Thống Kê Sự Kiện Quan Sát (Natural vs Fixture Observations)

Trong suốt thời gian forward validation, Shadow Mode phân định rạch ròi giữa dữ liệu thực nghiệm và dữ liệu thị trường tự nhiên:

| Danh Mục Phân Loại | Số Lượng Sự Kiện | Tỷ Lệ | Ghi Chú Đánh Giá |
| :--- | :---: | :---: | :--- |
| **Sự Kiện Thị Trường Tự Nhiên (Natural)** | **9** | **52.9%** | Tín hiệu lịch sử và nến tự nhiên sinh ra từ Flink streaming jobs |
| **Sự Kiện Kiểm Thử (Fixture Events)** | **8** | **47.1%** | Dữ liệu kiểm thử có gắn cờ `is_fixture: true` để thẩm định logic |
| **Trùng Lặp Đã Bị Chặn (Duplicates Suppressed)** | **4** | — | Khử trùng lặp thành công qua mã băm 16-hex `event_id` |
| **Tín Hiệu BUY Được Ghi Nhận** | 5 | — | Quan sát độc lập, không phát sinh lệnh ra sàn môi giới |
| **Tín Hiệu SELL Được Ghi Nhận** | 4 | — | Quan sát độc lập, không phát sinh lệnh ra sàn môi giới |
| **Sự Kiện NO_SIGNAL Được Ghi Nhận** | 8 | — | Ghi nhận nguyên nhân cụ thể (`SMA_CROSSOVER_NOT_MET`, `DELAYED`) |
| **Lệnh Giao Dịch Thực Sự Được Phát Sinh** | **0** | **0.0%** | **Tuyệt đối tuân thủ quy tắc an toàn DRY_RUN** |

---

## 4. Kiểm Định Tính Nhất Quán & Tái Hiện (Idempotency & Reproducibility)

1. **Khả Năng Tái Hiện Tuyệt Đối (Determinism)**:
   - Chạy lại cùng một payload fixture tại cùng một mốc thời gian luôn tạo ra cùng một `event_id` 16 ký tự hexa (TC-G17-01 & TC-G17-15).
   - Lần gọi đầu tiên được chấp nhận với trạng thái `NEW_OBSERVATION`, lần gọi thứ hai bị chặn tự động với trạng thái `DUPLICATE_SKIPPED`.
2. **Khả Năng Chống Chịu Sự Kiện Đến Muộn / Sai Thứ Tự**:
   - Các sự kiện đến muộn hơn 10 giây so với mốc thời gian nguồn được gắn nhãn `input_data_state = "DELAYED"` (TC-G17-08 & TC-G17-16) mà không làm gián đoạn vòng lặp xử lý.
3. **Khả Năng Chống Chịu Thiếu Trường Dữ Liệu**:
   - Sự kiện thiếu giá hoặc thiếu điểm sentiment được xử lý an toàn và phân loại là `MISSING_DATA` (TC-G17-17), không gây crash chương trình.

---

## 5. Tuyên Bố Bác Bỏ Khả Năng Sinh Lời (Non-Profitability Disclaimer)

> [!WARNING]
> ### TUYÊN BỐ NGUYÊN TẮC QUAN TRỌNG:
> **Giai đoạn GĐ17 là giai đoạn kiểm định kỹ thuật (Technical Forward Validation) về tính toàn vẹn của luồng dữ liệu, khả năng khử trùng lặp và tính liên tục của hệ thống quan sát.**
> 
> - Số lượng tín hiệu quan sát được trong Shadow Mode **KHÔNG THỂ** và **TUYỆT ĐỐI KHÔNG ĐƯỢC PHÉP** sử dụng để suy diễn về hiệu quả sinh lời, tỷ lệ thắng (Win Rate), hay khả năng kiếm tiền của chiến lược trong thực tế.
> - Bất kỳ kết luận nào cho rằng "hệ thống có khả năng sinh lời" dựa trên dữ liệu kiểm định GĐ17 đều vi phạm nghiêm trọng quy chuẩn kỹ thuật và nguyên tắc vận hành định lượng.


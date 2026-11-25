# BÁO CÁO KIỂM TOÁN TÍNH ĐÚNG ĐẮN VỀ THỜI GIAN & THIÊN LỆCH NHÌN TRƯỚC (GĐ13)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Mã giai đoạn: **GĐ13 — Section C: Temporal Correctness & Look-Ahead Bias Audit**  
Báo cáo kiểm thử: `tests/test_gd13_acceptance_suite.py` (TC-G13-06, TC-G13-07, TC-G13-08, TC-G13-10)

---

## 1. Bản chất Trục Thời gian trong Hệ thống Giao dịch Thời gian thực

Trong các hệ thống phân tích dòng dữ liệu phức tạp (Complex Event Processing - CEP), sự khác biệt giữa các mốc thời gian là yếu tố quyết định giữa một hệ thống giao dịch khả thi trong thực tế và một mô hình bị "nhiễm dữ liệu tương lai" (Look-Ahead Bias / Data Snooping):

```
       Trục Thời Gian Sự Kiện (Event Time vs Processing Time)
       =======================================================
       
[16:40:00.000] ─── Nến 1 phút bắt đầu tích lũy giao dịch
      │
      │ (Khoảng thời gian 60 giây giao dịch diễn ra trên sàn)
      ▼
[16:40:59.999] ─── Giao dịch cuối cùng của nến; Giá CLOSE được chốt
      │
      ▼
[16:41:00.000] ─── Alpaca hoàn tất nến và phát hành qua WebSocket/REST
      │ (Độ trễ mạng & WebSocket: ~50ms - 200ms)
      ▼
[16:41:00.150] ─── continuous_crypto_producer tiếp nhận (Ingest Time)
      │ (Đẩy vào Redpanda: ~5ms)
      ▼
[16:41:00.155] ─── Redpanda lưu trữ thông điệp (Kafka Offset Timestamp)
      │ (Flink xử lý nến, tính SMA20, kiểm tra Watermark: ~100ms)
      ▼
[16:41:00.255] ─── Tín hiệu BUY/SELL được Flink phát ra
      │ (Signal Handler nhận tín hiệu: ~15ms)
      ▼
[16:41:00.270] ─── THỜI ĐIỂM SỚM NHẤT CÓ THỂ ĐẶT LỆNH RA THỊ TRƯỜNG!
                   (Giá khớp thực tế chỉ có thể là OPEN của nến 16:41:00 trở đi)
```

---

## 2. Kiểm toán Rủi ro Nhìn trước (Look-Ahead Bias Audit)

### 2.1. Thiên lệch Nến Dở dang (Unfinalized Candle Look-Ahead)
- **Vấn đề tiềm ẩn**: Nếu một thuật toán kiểm tra điều kiện $Close_t < SMA20_t$ tại thời điểm $16:40:15$, mức giá Close đó chỉ là giá tạm thời của giây thứ 15. Giá có thể đảo chiều hoàn toàn vào giây thứ 59. Nếu hệ thống cho rằng nến đã hoàn tất, đó là thiên lệch nhìn trước giả định.
- **Biện pháp khắc phục trong Pipeline**:
  - Tại `continuous_crypto_producer.py`: Thêm cờ `is_final = TRUE` và chỉ đánh dấu nến hoàn tất khi timestamp bước sang phút mới.
  - Tại `ddl_crypto.sql`: View tính SMA bổ sung ràng buộc `WHERE is_final = TRUE`, loại bỏ hoàn toàn các nến trung gian chưa chốt.

### 2.2. Thiên lệch Khớp Lệnh Lập tức (Instant Execution Look-Ahead in Backtest)
- **Vấn đề tiềm ẩn**: Rất nhiều bài backtest ngây thơ giả định rằng khi tín hiệu xuất hiện ở nến $t$, lệnh được khớp ngay tại mức giá $Close_t$.  
  Điều này là **bất khả thi trong thực tế**, vì giá Close của nến $t$ chỉ được biết ở mili-giây cuối cùng của nến. Sau đó còn độ trễ tính toán và gửi lệnh mạng.
- **Biện pháp bắt buộc trong Backtest Engine (`backtest/engine.py`)**:
  - Tín hiệu sinh ra từ giá Close của nến $t$ chỉ được phép khớp vào mức giá **$Open_{t+1}$** (nến tiếp theo), cộng thêm trượt giá (Slippage) và phí giao dịch.
  - Kiểm thử `TC-G13-07` chứng minh: Tín hiệu tại thanh nến 10 chỉ được vào vị thế tại thanh nến 11 Open, bảo đảm **Zero Look-Ahead Bias**.

---

## 3. Kiểm toán Độ trễ Tin tức (News Ingestion vs Event Time Latency)

### 3.1. Sự chênh lệch giữa `published_at` và `received_at`
Khi kiểm toán dữ liệu tại `market_news.csv` và `crypto_news.csv`:
- Trường `timestamp_ms` lưu trữ thời điểm bài báo được tạo trên hệ thống Benzinga/Alpaca (`created_at`).
- Tuy nhiên, script `news-producer.py` và `continuous_news_producer.py` thu thập tin tức qua cơ chế định kỳ Polling 60 giây.
- Một bài báo xuất bản lúc `14:22:10` có thể chỉ được tải về và đẩy vào Kafka lúc `14:23:05` (chậm 55 giây).

### 3.2. Rủi ro về Watermark trong Apache Flink
Apache Flink sử dụng cơ chế Watermark để kiểm soát dữ liệu đến muộn (Late Events):
```sql
WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
```
- Ngưỡng trễ tối đa cho phép là **5 giây**.
- Nếu Flink đang xử lý dòng giá với Watermark đã tiến đến `14:23:00`, và một bài báo có `event_time = 14:22:10` đến sau (do chu kỳ polling 60 giây):
  $$t_{\text{news}} = 14:22:10 < \text{Watermark} (14:22:55)$$
- Flink coi đây là **sự kiện đến muộn (LATE EVENT)** và âm thầm loại bỏ (DROP), không đưa vào Temporal Join!
- **Hệ quả thực tế**: Đây chính là một trong những nguyên nhân khiến tin tức thật từ Alpaca bị Flink bỏ qua trong quá trình streaming thời gian thực!

---

## 4. Kiểm toán Cửa sổ Temporal Join (Interval Join Windows)

### 4.1. Cơ chế Ghép cặp trong Flink
1. **Đối với Stocks (`ddl_production.sql`)**:
   ```sql
   n.event_time BETWEEN p.event_time - INTERVAL '1' MINUTE AND p.event_time
   ```
   Điều kiện này tương đương với:
   $$n.\text{event\_time} \le p.\text{event\_time} \le n.\text{event\_time} + 1\text{ phút}$$
   Nghĩa là: Nến giá $p$ phải xảy ra trong vòng 60 giây sau khi bài báo xuất hiện. Nếu không có nến giá nào rơi đúng vào khoảng 60 giây này (ví dụ: thị trường đóng cửa hoặc cổ phiếu thanh khoản thấp không có giao dịch trong phút đó), kết quả join là **RỖNG (0 bản ghi)**.

2. **Đối với Crypto (`ddl_crypto.sql`)**:
   ```sql
   n.event_time BETWEEN p.event_time - INTERVAL '2' MINUTE AND p.event_time + INTERVAL '2' MINUTE
   ```
   Điều kiện mở rộng sang $\pm 2\text{ phút}$ ($120\text{ giây}$). Tuy nhiên, tần suất phát hành tin tức crypto trên Alpaca là rất thưa (trung bình vài tiếng mới có 1 bài báo). Khoảng cách thời gian trung vị giữa các bài báo là hơn 30 phút. Do đó, xác suất để một bài báo xuất hiện đúng trong cửa sổ 120 giây của một nến 1 phút là cực kỳ thấp ($< 0.5\%$).

---

## 5. Đề xuất Kiến trúc Cải tiến: Decoupled Stateful Sentiment

Để giải quyết triệt để sự xung đột thời gian giữa dòng nến liên tục (mỗi 60 giây có 1 nến) và dòng tin tức không liên tục (vài giờ mới có 1 tin), kiến trúc tối ưu không nên sử dụng Interval Join hữu hạn thời gian, mà cần áp dụng:

1. **Flink Temporal Table Join (Bảng Trạng Thái Lịch Sử)**:
   - Coi `market_news` như một Versioned Table duy trì `latest_sentiment` cho từng symbol.
   - Mỗi khi có nến giá mới, nến giá sẽ join với trạng thái cảm xúc gần nhất tại thời điểm đó.
2. **Exponential Decay (Hàm Phân rã Cảm xúc)**:
   - Điểm cảm xúc giảm dần theo hàm số mũ theo thời gian:
     $$S(t) = S_0 \cdot e^{-\lambda (t - t_0)}$$
   - Với chu kỳ bán rã (Half-life) $t_{1/2} = 60\text{ phút}$.
   - Tin tức mới có tác động mạnh mẽ nhất trong 15-30 phút đầu, sau đó mờ nhạt dần và trở về trung tính ($0.0$), phản ánh chính xác tâm lý thị trường tài chính thực tế.


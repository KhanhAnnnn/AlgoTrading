# GĐ10 — CONTINUOUS MARKET DATA STREAMING ARCHITECTURE & SPECIFICATION

## 1. Executive Summary

Giai đoạn 10 hoàn thiện cơ chế thu thập dữ liệu thị trường liên tục từ Alpaca vào Redpanda, xử lý qua Apache Flink streaming engine và cập nhật thời gian thực lên Quant Terminal Dashboard thông qua WebSocket. 

Hệ thống được thiết kế theo tiêu chuẩn sản xuất (production-grade):
- **Tự động hóa toàn diện**: Hoạt động bền bỉ, không cần kích hoạt script thủ công.
- **Chống trùng lặp tuyệt đối**: Checkpoint lưu trữ bền vững trên đĩa, bootstrap từ Kafka topic, đảm bảo không duplicate nến hay tin tức.
- **Khả năng tự phục hồi (Self-Healing)**: Tự động reconnect Kafka/Alpaca, exponential backoff khi gặp lỗi mạng/rate limit, tự động backfill dữ liệu bỏ lỡ sau khi khởi động lại.
- **Nhận biết trạng thái thị trường chính xác**: Truy vấn Alpaca Market Clock để phân biệt chính xác 6 trạng thái (`LIVE STREAMING`, `DELAYED DATA`, `MARKET CLOSED`, `STALE`, `RECONNECTING`, `ERROR`).
- **An toàn tuyệt đối**: Bảo vệ hoàn toàn dữ liệu Redpanda/Flink hiện hữu, cách ly tuyệt đối với các container của dự án khác, không phát sinh lệnh Paper Trading ngoài ý muốn.

---

## 2. Kiến trúc Luồng Dữ liệu Liên tục (Continuous Streaming Pipeline)

```
[Alpaca Market Data API]
       │
       ├── (1-min IEX Bars, 60s cycle) ──────► [continuous_price_producer.py] ───► Topic: 'stock-prices'
       └── (Financial News & REST, 90s cycle) ─► [continuous_news_producer.py]   ───► Topic: 'market-news'
                                                                                            │
                                                                                            ▼
                                                                                [Apache Flink Engine]
                                                                                (Watermark, SMA20/50, Join)
                                                                                            │
                                                                                            ▼
                                                                                Topic: 'trading-signals'
                                                                                            │
                                                                                            ▼
                                                                                [FastAPI Ingestion Engine]
                                                                                (kafka_consumer_service.py)
                                                                                            │
                                                                                            ▼
                                                                                [WebSocket Server: /ws/live]
                                                                                            │
                                                                                            ▼
                                                                                [React Quant Terminal UI]
                                                                                (Merge / Append / Dedup)
```

---

## 3. Continuous Price Producer (`continuous_price_producer.py`)

### 3.1. Cơ chế Polling & Giới hạn API
- **Chu kỳ polling**: 60 giây (tương thích nến 1 phút).
- **Feed**: Alpaca IEX feed (`DataFeed.IEX`).
- **Độ trễ dữ liệu**: Dữ liệu free IEX có độ trễ 15 phút. Producer tính toán cửa sổ truy vấn an toàn:
  $$\text{end\_date} = \text{now}_{\text{UTC}} - 15\text{ phút}$$
  $$\text{start\_date} = \text{last\_candle\_timestamp} + 1\text{ phút}$$
- **Tuân thủ Rate Limit**: Tối đa 200 requests/phút theo giới hạn Alpaca API.

### 3.2. Checkpoint & Khôi phục Sau Restart
- **Vị trí lưu trữ**: `data/checkpoints/price_checkpoint.json`.
- **Cấu trúc Checkpoint**:
  ```json
  {
    "symbols": {
      "NVDA": {
        "last_candle_timestamp_ms": 1792180740000,
        "last_candle_time_iso": "2026-10-16T19:59:00+00:00",
        "last_close": 214.125,
        "total_bars_emitted": 0
      },
      "AAPL": {
        "last_candle_timestamp_ms": 1792180740000,
        "last_candle_time_iso": "2026-10-16T19:59:00+00:00",
        "last_close": 343.39,
        "total_bars_emitted": 0
      }
    },
    "producer_id": "continuous-price-producer-v1",
    "last_updated_at": "2026-10-17T11:46:43.584481+00:00"
  }
  ```
- **Cơ chế Kafka Bootstrap**: Nếu file checkpoint chưa tồn tại hoặc bị xóa, producer quét ngược Redpanda topic `stock-prices` để tìm nến mới nhất đã ingest cho từng symbol, ngăn chặn việc re-ingest và duplicate dữ liệu lịch sử.
- **Ghi nguyên tử (Atomic Write)**: Ghi ra file `.tmp` trước khi đổi tên thay thế file chính thức, tránh rủi ro corrupt file khi mất nguồn đột ngột.

### 3.3. Xử lý Trạng thái Thị trường Đóng cửa (Market Closed)
- Producer truy vấn `TradingClient.get_clock()`.
- Khi `is_open == False`:
  - Chuyển trạng thái health thành `IDLE_MARKET_CLOSED`.
  - Log thời điểm mở cửa tiếp theo (`next_open`).
  - Tạm dừng và sleep `poll_interval_sec` (60s) thay vì spam API hoặc báo lỗi giả.
  - Ngay khi thị trường mở cửa trở lại, producer tự động kích hoạt polling và backfill nến mới.

### 3.4. Khả năng Chịu lỗi & Exponential Backoff
- Khi gặp lỗi mạng hoặc HTTP 429 (Rate Limit):
  $$\text{backoff\_sec} = \min(60, 2^{\min(\text{fail\_count}, 6)})$$
  (Chuỗi backoff: 2s, 4s, 8s, 16s, 32s, tối đa 60s).
- Trạng thái telemetry chuyển sang `BACKING_OFF`.
- Bảo mật thông tin xác thực: Log không bao giờ ghi lộ API Key hay Secret Key.

---

## 4. Continuous News Producer (`continuous_news_producer.py`)

### 4.1. Polling & Chống trùng theo News ID
- **Chu kỳ polling**: 90 giây.
- **REST Endpoint**: Alpaca News API `/v1beta1/news` với `sort=desc`.
- **Chống trùng (Deduplication)**:
  - Tập hợp `seen_ids` lưu giữ tối đa 2,000 ID bài viết gần nhất.
  - Tự động bootstrap `seen_ids` từ Kafka topic `market-news` nếu khởi động lần đầu.
  - Bỏ qua lập tức các tin tức đã tồn tại trong `seen_ids`.

### 4.2. Phân tích Sentiment VADER
- Sử dụng NLTK `SentimentIntensityAnalyzer`.
- Tính toán compound sentiment score trên tiêu đề (`headline`) và tóm tắt (`summary`).
- Phân loại:
  - $\text{score} > 0.05 \implies \text{POSITIVE}$
  - $\text{score} < -0.05 \implies \text{NEGATIVE}$
  - Còn lại $\implies \text{NEUTRAL}$
- Ghi vào topic `market-news` kèm event timestamp gốc.

---

## 5. WebSocket Live Updates & Đồng bộ Nến trên React

### 5.1. Luồng Dữ liệu
$$\text{Alpaca} \xrightarrow{\text{Polling}} \text{Producer} \xrightarrow{\text{Kafka}} \text{Redpanda} \xrightarrow{\text{Consumer Thread}} \text{FastAPI} \xrightarrow{\text{asyncio Queue}} \text{WebSocket} \xrightarrow{} \text{React Client}$$

### 5.2. Thuật toán Đồng bộ Nến Client-Side
Trên component React (`App.tsx` & `TradingChart.tsx`):
1. **Cùng timestamp ($T_{\text{new}} == T_{\text{last}}$)**:
   - Cập nhật nến hiện tại (intra-bar update).
   - $\text{high} = \max(\text{high}_{\text{last}}, \text{high}_{\text{new}})$
   - $\text{low} = \min(\text{low}_{\text{last}}, \text{low}_{\text{new}})$
   - $\text{close} = \text{close}_{\text{new}}$
   - $\text{volume} = \text{volume}_{\text{last}} + \text{volume}_{\text{new}}$
2. **Timestamp mới ($T_{\text{new}} > T_{\text{last}}$)**:
   - Append nến mới vào cuối mảng `candles`.
3. **Timestamp cũ ($T_{\text{new}} < T_{\text{last}}$)**:
   - Bỏ qua, ngăn chặn nến quá hạn chèn sai thứ tự.
4. **Không reload toàn bộ chart**:
   - `TradingChart.tsx` sử dụng `candleSeries.setData()` và `update()` tối ưu của Lightweight Charts, giữ nguyên zoom và pan position.

### 5.3. Cơ chế Backfill / Resync Sau Reconnect
- Khi WebSocket ngắt kết nối tạm thời và tái kết nối (`ws.onopen`):
  - Kích hoạt song song `fetchCandles(symbol, timeframe)`, `fetchSignals()`, `fetchNews()`, `fetchSystemStatus()`.
  - Bù đắp toàn bộ nến và tín hiệu phát sinh trong thời gian mất kết nối.

---

## 6. Ma trận Trạng thái Dữ liệu Thị trường (Market Data Status Matrix)

Hệ thống phân biệt rạch ròi 6 trạng thái hoạt động dựa trên dữ liệu thực tế:

| Trạng thái | Điều kiện Kỹ thuật | Hiển thị Dashboard | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| **LIVE STREAMING** | Market Open = True, Latency < 180s | Badge Xanh lục nhấp nháy (`LIVE STREAMING`) | Pipeline đang nhận và phát dữ liệu thời gian thực |
| **DELAYED DATA** | Market Open = True, 180s $\le$ Latency $\le$ 1500s | Badge Hổ phách (`DELAYED DATA (Xm)`) | Dữ liệu hợp lệ theo độ trễ feed IEX (~15m) |
| **MARKET CLOSED** | Alpaca Clock `is_open == False` | Badge Xám chì (`MARKET CLOSED`) | Ngoài giờ giao dịch hoặc cuối tuần |
| **STALE** | Market Open = True, Latency > 1500s | Badge Đỏ hồng (`STALE DATA`) | Nguồn dự kiến có dữ liệu nhưng không cập nhật |
| **RECONNECTING** | Redpanda/Kafka disconnected hoặc WS reconnecting | Badge Vàng xoay (`RECONNECTING`) | Đang tái lập kết nối tầng mạng/broker |
| **ERROR** | Producer health = `BACKING_OFF` hoặc crash | Badge Đỏ cảnh báo (`PRODUCER ERROR`) | Có lỗi kết nối hoặc xử lý API |

> [!NOTE]
> Độ trễ dữ liệu (`data_latency_sec`) được tính động từ hiệu số giữa thời gian máy chủ backend và timestamp nến thực tế ($\text{now} - \text{last\_candle\_ts}$). Tuyệt đối không hardcode con số 20 phút.

---

## 7. Cơ chế Khởi động & Quản lý Dịch vụ (Service Management)

### 7.1. Tích hợp Docker Compose (`docker-compose.yml`)
Bổ sung 2 container services chuyên biệt:
```yaml
  price-producer:
    container_name: price-producer
    build:
      context: .
      dockerfile: Dockerfile-producers
    command: python continuous_price_producer.py
    restart: unless-stopped
    stop_grace_period: 15s
    depends_on:
      - redpanda-1
      - redpanda-2
    environment:
      - REDPANDA_BROKERS=redpanda-1:29092,redpanda-2:29093
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
    networks:
      - algotradingenvju

  news-producer:
    container_name: news-producer
    build:
      context: .
      dockerfile: Dockerfile-producers
    command: python continuous_news_producer.py
    restart: unless-stopped
    stop_grace_period: 15s
    depends_on:
      - redpanda-1
      - redpanda-2
    environment:
      - REDPANDA_BROKERS=redpanda-1:29092,redpanda-2:29093
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
    networks:
      - algotradingenvju
```

### 7.2. Script Quản lý Host (`run-producers.ps1`)
Cung cấp công cụ dòng lệnh đa năng cho môi trường Windows:
```powershell
.\run-producers.ps1 -Action start    # Khởi động continuous producers trên host
.\run-producers.ps1 -Action status   # Kiểm tra trạng thái health và PID
.\run-producers.ps1 -Action stop     # Dừng an toàn (Graceful shutdown)
.\run-producers.ps1 -Action restart  # Tái khởi động producers
```

### 7.3. Khóa Đơn Thể (Single-Instance Lock)
Cơ chế file PID tại `data/locks/price_producer.pid` và `data/locks/news_producer.pid` ngăn chặn việc chạy nhiều bản sao producer đồng thời, tránh xung đột offset và lãng phí quota API.

### 7.4. Log Rotation
- File log: `logs/price_producer.log` và `logs/news_producer.log`.
- Định mức: 5 MB/file, lưu trữ tối đa 3 file backup (`backupCount=3`).


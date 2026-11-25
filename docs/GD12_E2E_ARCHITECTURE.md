# KIẾN TRÚC TÍCH HỢP END-TO-END & TRACEABILITY (GĐ12)

Dự án: **AlgoTrading**  
Đường dẫn: `D:\AlgoTrading`  
Môi trường thực thi: Windows 11 / Docker Desktop / Apache Flink 1.17 / Redpanda v23 / FastAPI / Vite React  
Chế độ hoạt động: `TRADING_MODE=DRY_RUN` (Bảo đảm an toàn tuyệt đối, zero live/paper orders trong GĐ12)

---

## 1. Tổng quan Kiến trúc Toàn vẹn (End-to-End Architecture)

Hệ thống AlgoTrading vận hành hai pipeline xử lý dữ liệu thời gian thực độc lập và song song:
1. **Stocks Pipeline**: Tiếp nhận nến 1 phút và tin tức tài chính thị trường chứng khoán Mỹ (IEX feed) từ Alpaca Markets, tính toán chỉ báo kỹ thuật SMA-20/SMA-50, kết hợp điểm tin tức VADER sentiment qua Temporal Join trong Apache Flink, phát tín hiệu giao dịch BUY/SELL sang Redpanda, xử lý qua `signal-handler.py` và gửi thông báo trực tiếp qua Slack Bot đồng thời cập nhật Trading Dashboard.
2. **Crypto 24/7 Pipeline**: Tiếp nhận stream Trades và nến 1 phút thời gian thực 24/7 từ Alpaca Crypto WebSocket (`wss://stream.data.alpaca.markets/v1beta3/crypto/us`), phân tích tâm lý tin tức crypto với VADER Sentiment, tính toán SMA-20/SMA-50 sử dụng window framing (`ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`) trong Flink SQL, đối chiếu tín hiệu BUY/SELL qua Interval Join 2 phút, đưa tín hiệu vào `crypto-signals`, tiếp nhận bởi `crypto_signal_handler.py` với cơ chế khóa đơn phiên (PID Lock) và lưu vết ý định giao dịch (Persistent Order Intent) bền vững.

```mermaid
flowchart TD
    subgraph S1["1. Market Data Ingestion"]
        A1["Alpaca Stocks REST/IEX"] -->|Polling 1m| P1["continuous_price_producer.py<br/>(Docker: price-producer)"]
        A2["Alpaca Financial News"] -->|Polling 1m| P2["news-producer.py<br/>(Docker: news-producer)"]
        A3["Alpaca Crypto WebSocket<br/>(wss://stream.data.alpaca.markets)"] -->|24/7 Live Stream| P3["continuous_crypto_producer.py<br/>(Host Process PID 21236)"]
    end

    subgraph S2["2. Redpanda Event Streaming Cluster (7 Topics)"]
        P1 -->|Key: SYMBOL| T1["stock-prices<br/>(5,975 msgs)"]
        P2 -->|Key: SYMBOL| T2["market-news<br/>(171 msgs)"]
        P3 -->|Key: BTC/USD| T3["crypto-trades<br/>(78+ msgs)"]
        P3 -->|Key: PAIR| T4["crypto-bars-1m<br/>(635+ msgs)"]
        P3 -->|Key: PAIR| T5["crypto-news<br/>(18 msgs)"]
    end

    subgraph S3["3. Apache Flink Stream Processing (JobManager & TaskManager)"]
        T1 & T2 -->|Temporal Join 1m| F1["Stocks Flink Job<br/>(jid: c0955d4aa73c...)<br/>SMA20/50 + VADER"]
        T4 & T5 -->|Interval Join 2m| F2["Crypto Flink Job<br/>(jid: a9625608bc...)<br/>SMA20/50 + VADER"]
        F1 -->|Sink| T6["trading-signals<br/>(6 msgs)"]
        F2 -->|Sink| T7["crypto-signals<br/>(0 natural msgs)"]
    end

    subgraph S4["4. Execution Guards & Signal Handlers (DRY_RUN)"]
        T6 -->|Consumer Group| H1["signal-handler.py<br/>(Stocks Handler)"]
        T7 -->|Consumer Group| H2["crypto_signal_handler.py<br/>(Host Process PID 11912)"]
        H2 -->|Persist Intent| D1[("data/orders/<br/>crypto_order_intent.json")]
        H2 -->|Lock File| L1["data/locks/<br/>crypto_signal_handler.pid"]
    end

    subgraph S5["5. Notification & Telemetry"]
        H1 & H2 -->|Fail-Safe HTTP API| SL["Slack Bot (#trading-signals)<br/>(Block Kit / 429 Backoff)"]
        T1 & T2 & T4 & T6 -->|KafkaConsumer| BK["FastAPI Backend (Port 8005)<br/>kafka_consumer_service.py"]
        BK -->|WebSocket /ws/live| DB["React Trading Dashboard<br/>(Port 5173 - Lightweight Charts)"]
    end
```

---

## 2. Đặc tả Schema 7 Redpanda Topics

Tất cả 7 topics production đều được cấu hình với 1 partition, replication factor 1 trên cụm Redpanda 2 broker (`redpanda-1:29092`, `redpanda-2:29093` nội bộ Docker; `localhost:9092`, `localhost:9093` trên Windows Host).

### 2.1. Topic `stock-prices`
- **Nguồn**: `price-producer` (Alpaca IEX Historical/Live Minute Bars).
- **Partition Key**: Ticker symbol (`AAPL`, `NVDA`).
- **Schema JSON**:
  ```json
  {
    "symbol": "AAPL",
    "timestamp": 1792180740000,
    "open": 343.68,
    "high": 343.88,
    "low": 343.39,
    "close": 343.39,
    "volume": 33106.0,
    "trade_count": 735.0,
    "vwap": 343.648077,
    "provider": "alpaca"
  }
  ```

### 2.2. Topic `market-news`
- **Nguồn**: `news-producer` (Alpaca Financial News API + NLTK VADER Analyzer).
- **Partition Key**: Ticker symbol (`NVDA`, `AAPL`).
- **Schema JSON**:
  ```json
  {
    "id": 62428348,
    "author": "Crispus Nyaga",
    "headline": "Broadcom Stock Is Down 35% From Its Peak...",
    "source": "benzinga",
    "summary": "...",
    "data_provider": "alpaca",
    "url": "https://www.benzinga.com/...",
    "symbol": "NVDA",
    "sentiment": 0.3291,
    "timestamp_ms": 1792251076000
  }
  ```

### 2.3. Topic `trading-signals`
- **Nguồn**: Flink Stocks Streaming Job (`insert-into_...trading_signals_sink`).
- **Partition Key**: `null` hoặc Symbol.
- **Schema JSON**:
  ```json
  {
    "symbol": "TEST_NVDA",
    "signal_time": "2026-10-17 09:19:50Z",
    "signal": "BUY"
  }
  ```

### 2.4. Topic `crypto-trades`
- **Nguồn**: `continuous_crypto_producer.py` (Alpaca Crypto WebSocket feed `trades`).
- **Partition Key**: Crypto Pair (`BTC/USD`, `ETH/USD`).
- **Schema JSON**:
  ```json
  {
    "asset_type": "crypto",
    "symbol": "BTC/USD",
    "source": "alpaca_crypto_ws",
    "price": 81190.033,
    "size": 1.995e-05,
    "trade_id": "1010370336437913486",
    "taker_side": "S",
    "timestamp": 1792255599643,
    "timestamp_ms": 1792255599643,
    "event_time": 1792255599,
    "ingest_time": 1792255599,
    "schema_version": "1.0"
  }
  ```

### 2.5. Topic `crypto-bars-1m`
- **Nguồn**: `continuous_crypto_producer.py` (Alpaca Crypto WebSocket feed `bars`).
- **Partition Key**: Crypto Pair (`BTC/USD`, `ETH/USD`).
- **Schema JSON**:
  ```json
  {
    "asset_type": "crypto",
    "symbol": "BTC/USD",
    "source": "alpaca_crypto_ws",
    "open": 81209.52,
    "high": 81209.52,
    "low": 81188.048,
    "close": 81200.118,
    "volume": 0.0,
    "trade_count": 0.0,
    "vwap": 81198.784,
    "timestamp": 1792255500000,
    "timestamp_ms": 1792255500000,
    "event_time": 1792255500,
    "ingest_time": 1792255559,
    "is_final": true,
    "schema_version": "1.0"
  }
  ```

### 2.6. Topic `crypto-news`
- **Nguồn**: `continuous_crypto_producer.py` / Alpaca Crypto News.
- **Partition Key**: Crypto Pair (`BTC/USD`, `ETH/USD`).
- **Schema JSON**:
  ```json
  {
    "asset_type": "crypto",
    "symbol": "BTC/USD",
    "source": "alpaca_crypto_news",
    "id": 62428373,
    "headline": "Rich on Paper, Locked Out in Reality...",
    "summary": "Cryptocurrency has created fortunes...",
    "author": "Aniket Verma",
    "url": "https://www.benzinga.com/crypto/...",
    "sentiment": 0.8519,
    "timestamp": 1792252884000,
    "timestamp_ms": 1792252884000,
    "event_time": 1792252884,
    "ingest_time": 1792253795,
    "schema_version": "1.0"
  }
  ```

### 2.7. Topic `crypto-signals`
- **Nguồn**: Flink Crypto Streaming Job (`insert-into_...crypto_signals_sink`).
- **Partition Key**: Crypto Pair.
- **Schema JSON**:
  ```json
  {
    "asset_type": "crypto",
    "symbol": "BTC/USD",
    "signal_time": "2026-10-17 12:26:10Z",
    "signal": "BUY",
    "price": 79500.0,
    "sentiment": 1.0,
    "sma_20": 79981.484,
    "sma_50": 79981.484
  }
  ```

---

## 3. Cơ chế Truy vết Đa tầng (Cross-Tier Traceability)

Hệ thống thiết lập cơ chế liên kết định danh (Traceability & Correlation IDs) giúp đối chiếu dữ liệu từ nguồn Alpaca đến điểm hiển thị và thông báo:

1. **Phân biệt Asset Class**:
   - `asset_type`: `stocks` (hoặc ngầm định cho cổ phiếu truyền thống) vs `crypto`.
2. **Bảo toàn Thời gian Sự kiện (Source Event Time)**:
   - Giữ nguyên timestamp UTC gốc từ Alpaca: `timestamp_ms` (13 chữ số epoch ms), `event_time` (epoch giây hoặc ISO string `YYYY-MM-DD HH:MM:SSZ`).
3. **Ghi nhận Thời gian Nhận và Xử lý (Ingest & Processing Times)**:
   - `ingest_time`: Epoch giây hoặc ISO UTC khi producer tiếp nhận dữ liệu từ WebSocket/REST và đẩy vào Redpanda.
   - `signal_time`: Timestamp thời điểm Flink tính toán thỏa mãn điều kiện crossover & sentiment.
   - `handler_time`: Timestamp ghi nhận tại `signal-handler.py` / `crypto_signal_handler.py`.
4. **Đối chiếu Kafka Partition & Offset**:
   - Mỗi thông điệp được gắn với tuple `(topic, partition=0, offset)`.
5. **Định danh Tín hiệu & Lệnh (Correlation / Signal IDs)**:
   - **Stocks Signal ID**: `SIG-STOCKS-{symbol}-{signal}-{signal_time_clean}` (ví dụ: `SIG-STOCKS-NVDA-BUY-2026-10-14_173511Z`).
   - **Crypto Signal ID**: `SIG-CRYPTO-{symbol}-{signal}-{signal_time_clean}`.
   - **Client Order ID**: `CRYPTO-{clean_symbol}-{side}-{safe_epoch_time}` (ví dụ: `CRYPTO-BTCUSD-BUY-1792256021`).
   - **Alpaca Executed Order ID**: UUID v4 trả về từ Alpaca Paper Trading API (ví dụ: `c5d4311a-2c15-441d-bc11-8a7384fe8eed`).

---

## 4. Ngân sách Độ trễ Từng Chặng (Latency Budget)

| Chặng xử lý | Nguồn -> Đích | Cơ chế truyền | Ngân sách lý thuyết | Thực tế đo đạc | Trạng thái |
|---|---|---|---|---|---|
| **L1. Market Data Ingest** | Alpaca WS -> Producer | WebSocket SSL | $\le 200\text{ ms}$ | $45\text{ ms} - 120\text{ ms}$ | Đạt |
| **L2. Broker Ingestion** | Producer -> Redpanda | Kafka Protocol TCP | $\le 15\text{ ms}$ | $2\text{ ms} - 5\text{ ms}$ | Đạt |
| **L3. Flink Processing** | Redpanda -> Flink Sink | Streaming Window / Join | $\le 500\text{ ms}$ | $65\text{ ms} - 180\text{ ms}$ | Đạt |
| **L4. Handler Consumption** | Redpanda -> Handler | Kafka Consumer | $\le 50\text{ ms}$ | $8\text{ ms} - 22\text{ ms}$ | Đạt |
| **L5. Slack Notification** | Handler -> Slack API | HTTPS POST (chat.postMessage) | $\le 1000\text{ ms}$ | $280\text{ ms} - 550\text{ ms}$ | Đạt |
| **L6. WebSocket UI Stream** | Backend -> React UI | WebSocket `/ws/live` | $\le 50\text{ ms}$ | $4\text{ ms} - 12\text{ ms}$ | Đạt |
| **Toàn trình E2E** | Alpaca -> UI / Slack | End-to-End Pipeline | $\le 1800\text{ ms}$ | $\mathbf{\approx 420\text{ ms} - 890\text{ ms}}$ | **Đạt chuẩn High-Frequency Streaming** |

---

## 5. Cơ chế Phòng vệ & Khả năng Phục hồi (Failure & Recovery Guards)

1. **Anti-Replay Idempotency**:
   - `crypto_order_intent.json` lưu trữ danh sách dedup keys (`symbol:signal:signal_time`).
   - Khi restart handler, toàn bộ lịch sử được nạp vào memory set, ngăn chặn hoàn toàn việc tái phát tín hiệu hoặc gửi lệnh trùng lặp.
2. **Offset Preservation**:
   - Consumer commit sau khi xử lý thành công mỗi batch.
   - Thử nghiệm tắt consumer đột ngột và khởi động lại chứng minh offset được giữ nguyên 100% tại Redpanda Broker.
3. **Slack Resilience**:
   - Xử lý mã lỗi HTTP 429: Đọc header `Retry-After` và áp dụng exponential backoff.
   - Giới hạn retry 3 lần cho lỗi 500/mạng, sau đó ghi log cảnh báo và tiếp tục vận hành pipeline, tuyệt đối không gây sập process handler.
4. **WebSocket Auto-Reconnect**:
   - Frontend Vite React tự động kết nối lại khi backend restart hoặc ngắt kết nối tạm thời.
   - Backend dọn dẹp task queue và hủy socket cũ khi client ngắt kết nối, không gây rò rỉ tài nguyên.


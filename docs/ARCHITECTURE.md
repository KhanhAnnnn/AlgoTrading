# System Architecture — Real-Time Algorithmic Trading

## 1. Overview & High-Level Design

The Real-Time Algorithmic Trading System ingests financial news and 1-minute candlestick price data from the **Alpaca API**, performs sentiment analysis using **NLTK VADER**, computes moving averages and crossover conditions in **Apache Flink**, and outputs trading signals into **Redpanda** topics. An event-driven Python **Signal Handler** consumes these signals, dispatches real-time alerts to **Slack**, and safely triggers paper trade orders on the **Alpaca Paper Trading API**.

```
                           +----------------------+
                           |   Alpaca News API    |
                           +----------+-----------+
                                      |
                                      v
                        +----------------------------+
                        | news-producer.py           |
                        | (NLTK VADER Sentiment:     |
                        |  compound score -1.0..+1.0)|
                        +-------------+--------------+
                                      |
                                      v (JSON)
+------------------------+  [market-news topic]   +---------------------------+
| Alpaca Market Data API |                        | Apache Flink 1.19.3       |
+-----------+------------+                        | (JobManager + TaskManager)|
            |                                     |                           |
            v                                     | 1. source tables          |
+------------------------+                        | 2. sma_20 & sma_50 views  |
| prices-producer.py     |                        | 3. price_with_movavg view |
| (1-min OHLCV bars)     |                        | 4. news_and_prices join   |
+-----------+------------+                        | 5. trading_signals view   |
            |                                     | 6. INSERT streaming job   |
            v (JSON)                              |                           |
   [stock-prices topic] ------------------------> +-------------+-------------+
                                                                |
                                                                v (JSON)
                                                    [trading-signals topic]
                                                                |
                                                                v
                                                  +---------------------------+
                                                  | signal-handler.py         |
                                                  | (DRY_RUN / PAPER_TRADING) |
                                                  +-------------+-------------+
                                                                |
                                             +------------------+------------------+
                                             |                                     |
                                             v                                     v
                                    +-----------------+                  +--------------------+
                                    | Slack Channel   |                  | Alpaca Paper API   |
                                    | Bot Alert       |                  | Order Execution    |
                                    +-----------------+                  +--------------------+
```

---

## 2. Component Specifications

### 2.1 Redpanda Cluster (Kafka-Compatible Messaging)
- **Engine**: Redpanda v23.1.8 (C++ storage engine, Kafka protocol compatible).
- **Cluster Topology**: 2 broker nodes forming a Raft consensus cluster.
  - `redpanda-1`:
    - Internal listener: `redpanda-1:29092`
    - External (Host) listener: `localhost:9092`
    - RPC: `redpanda-1:33145`
  - `redpanda-2`:
    - Internal listener: `redpanda-2:29093`
    - External (Host) listener: `localhost:9093`
    - RPC: `redpanda-2:33146`
    - Seed node: `redpanda-1:33145`
- **Management UI**: `redpanda-console` (v2.2.4) at `http://localhost:8080`.
- **Topics**:
  - `market-news` (1 partition, replication factor 1)
  - `stock-prices` (1 partition, replication factor 1)
  - `trading-signals` (1 partition, replication factor 1)

### 2.2 Stream Processing: Apache Flink 1.19.3
- **JobManager**: Cluster coordinator, exposes Flink REST API and Web Dashboard at `http://localhost:8081`.
- **TaskManager**: Worker node allocated with 20 Task Slots for streaming operators.
- **SQL Client**: Preloaded with:
  - `flink-sql-connector-kafka-3.2.0-1.19.jar`
  - `flink-json-1.19.0.jar`
- **Time Semantics**: Event-Time with Watermarks (`event_time - INTERVAL '5' SECOND`).

### 2.3 Python Ingestion & Execution Workers
- **Runtime**: Python 3.14 on Windows Host / Virtual Environment (`D:\AlgoTrading\.venv`).
- **`news-producer.py`**:
  - Fetches news from Alpaca REST API.
  - Computes compound sentiment score using `nltk.sentiment.vader.SentimentIntensityAnalyzer`.
  - Emits JSON payloads with millisecond event timestamps to `market-news`.
- **`prices-producer.py`**:
  - Requests 1-minute historical bars for specified symbols (e.g., `NVDA`).
  - Serializes OHLCV bars with Unix timestamps to `stock-prices`.
- **`signal-handler.py`**:
  - Subscribes to `trading-signals` via Kafka consumer group `signal-handler-group`.
  - Dispatches formatted alert messages to Slack webhook / chat API.
  - Interacts with Alpaca Paper Trading REST endpoint (`https://paper-api.alpaca.markets`).
  - Dual-mode operation: `DRY_RUN` (log only) vs `PAPER_TRADING` (active order placement).

---

## 3. Data Flow & Topic Schemas

### 3.1 Topic: `market-news`
```json
{
  "id": 42109823,
  "author": "Dow Jones Newswires",
  "headline": "NVIDIA Partners with Major Cloud Providers for Next-Gen AI Infrastructure",
  "source": "benzinga",
  "summary": "NVIDIA announced expanded agreements with global hyperscalers...",
  "url": "https://www.benzinga.com/news/...",
  "symbol": "NVDA",
  "timestamp": "2026-10-17 09:30:00",
  "timestamp_ms": 1792200600000,
  "data_provider": "alpaca",
  "sentiment": 0.6369
}
```

### 3.2 Topic: `stock-prices`
```json
{
  "symbol": "NVDA",
  "open": 138.50,
  "high": 139.20,
  "low": 138.10,
  "close": 138.85,
  "volume": 25420.0,
  "trade_count": 182.0,
  "vwap": 138.75,
  "provider": "alpaca",
  "timestamp": 1792200600000
}
```

### 3.3 Topic: `trading-signals`
```json
{
  "symbol": "NVDA",
  "signal_time": "2026-10-17T09:30:00Z",
  "signal": "BUY"
}
```

---

## 4. Streaming Transformations & Signal Generation Logic

### 4.1 Moving Average Calculation (Over Windows)
Two rolling simple moving averages are computed over stock prices partitioned by `symbol`:
- **SMA 20**:
  ```sql
  AVG(`close`) OVER (
      PARTITION BY symbol
      ORDER BY event_time
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
  ) AS sma_20
  ```
- **SMA 50**:
  ```sql
  AVG(`close`) OVER (
      PARTITION BY symbol
      ORDER BY event_time
      ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
  ) AS sma_50
  ```

### 4.2 Stream-Stream Interval Join
News articles are correlated with stock prices within a 1-minute backward window:
```sql
FROM market_news n
JOIN price_with_movavg p
  ON n.symbol = p.symbol
 AND n.event_time BETWEEN p.event_time - INTERVAL '1' MINUTE AND p.event_time
```

### 4.3 Trading Signal Evaluation Rules
Signals are triggered when price interacts with `sma_20` under prevailing news sentiment:

| Signal | Sentiment Condition | Current Price vs SMA 20 | Previous Price vs SMA 20 (LAG 1) | Financial Rationale |
|---|---|---|---|---|
| **BUY** | `sentiment > 0` | `close < sma_20` | `LAG(close, 1) >= sma_20` | Downward crossover below SMA under bullish sentiment (dip-buying). |
| **SELL** | `sentiment < 0` | `close > sma_20` | `LAG(close, 1) <= sma_20` | Upward crossover above SMA under bearish sentiment (profit-taking / shorting). |
| **HOLD** | Other combinations | - | - | Emits `NULL`, filtered out before Kafka sink. |

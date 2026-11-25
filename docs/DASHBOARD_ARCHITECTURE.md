# Technical Architecture: Live Trading Visualization Dashboard

## 1. System Overview

The **Live Trading Visualization Dashboard** is a high-performance, real-time quant monitoring terminal engineered to observe streaming stock prices, VADER-evaluated news sentiment, Apache Flink algorithmic signals, and Alpaca Paper Trading portfolio execution.

```
                      +-----------------------------------+
                      |      Market Ingestion Engine      |
                      |   prices-producer & news-producer |
                      +-----------------+-----------------+
                                        |
                                        v
  +-------------------------------------------------------------------------------+
  |                        Redpanda Kafka Streaming Cluster                       |
  |   +-------------------+     +-------------------+     +-------------------+   |
  |   |   stock-prices    |     |    market-news    |     |  trading-signals  |   |
  |   +---------+---------+     +---------+---------+     +---------^---------+   |
  +-------------|-------------------------|-------------------------|-------------+
                |                         |                         |
                v                         v                         |
  +-------------------------------------------------------------+   |
  |              Apache Flink Real-Time SQL Engine              |   |
  |   - 1-Minute Candlestick Aggregation                        |   |
  |   - Moving Averages (SMA-20, SMA-50) & Crossover Logic      |   |
  |   - News Sentiment Weighting                                +---+
  +-------------------------------------------------------------+
                                        |
                                        | (Kafka Ingestion)
                                        v
  +-------------------------------------------------------------------------------+
  |                    FastAPI Dashboard Streaming Backend                        |
  |                           (Port 8005)                                         |
  |                                                                               |
  |   +-----------------------+   +-----------------------+   +---------------+   |
  |   | Kafka Consumer Thread |   | Timeframe Aggregator  |   | Alpaca Service|   |
  |   | (Dynamic Group ID)    |   | (1m, 5m, 15m, 1h)     |   | (Read-Only)   |   |
  |   +-----------+-----------+   +-----------+-----------+   +-------+-------+   |
  |               |                           |                       |           |
  |               +---------------------------+-----------------------+           |
  |                                           |                                   |
  |                     +---------------------+---------------------+             |
  |                     |                     |                     |             |
  |                     v                     v                     v             |
  |               WebSocket Server       REST API Engine     Replay Engine        |
  |                 (/ws/live)            (/api/*)          (/api/replay/*)       |
  +---------------------|---------------------|---------------------|-------------+
                        |                     |                     |
                        | (JSON Frames)       | (HTTP GET)          | (Scrubber)
                        v                     v                     v
  +-------------------------------------------------------------------------------+
  |               React 19 + TypeScript + Vite Quant Terminal                     |
  |                           (Port 5173)                                         |
  |                                                                               |
  |   +-----------------------+   +-----------------------+   +---------------+   |
  |   | TradingView TV Chart  |   | News Sentiment Feed   |   | Paper Trading |   |
  |   | Candlestick + SMA +   |   | Bullish/Bearish/Neut  |   | Portfolio &   |   |
  |   | BUY/SELL Markers      |   | Multi-filter Search   |   | Read-Only Safe|   |
  |   +-----------------------+   +-----------------------+   +---------------+   |
  +-------------------------------------------------------------------------------+
```

---

## 2. Component Design & Responsibilities

### 2.1 Backend Services (`trading-dashboard/backend`)

1. **`kafka_consumer_service.py`**:
   - Spawns a dedicated background thread consuming `stock-prices`, `market-news`, and `trading-signals`.
   - Employs a dynamic group ID (`dashboard-session-{pid}-{timestamp}`) with `auto_offset_reset='earliest'` to ensure immediate recovery and in-memory replay of historical candles on backend launch.
   - Maintains an in-memory chronological event buffer indexed by symbol and timestamp.
   - Distributes incoming events asynchronously to all connected WebSocket clients via an `asyncio.Queue` broadcast fan-out architecture.

2. **`timeframe_aggregator.py`**:
   - Converts standard 1-minute Alpaca / Kafka bars into 5-minute, 15-minute, and 1-hour candles on exact UTC boundaries.
   - Maintains open/high/low/close/volume integrity across candle buckets without creating phantom candles or interpolating missing periods.

3. **`sma_calculator.py`**:
   - Calculates Simple Moving Averages ($\text{SMA}_N = \frac{1}{N}\sum_{i=0}^{N-1} Close_{t-i}$) for $N=20$ and $N=50$.
   - Implements data sufficiency validation: suppresses invalid SMA points when sample count $< N$.

4. **`alpaca_service.py`**:
   - Connects strictly to Alpaca Paper Trading endpoint (`https://paper-api.alpaca.markets/v2`).
   - Hardcoded to **READ-ONLY** operations: fetches `/v2/account`, `/v2/positions`, and `/v2/orders`.
   - Contains **zero order creation endpoints** (`POST /v2/orders` is strictly absent) preventing unintended market executions.

5. **`main.py` (FastAPI Application)**:
   - Runs on port **8005** (avoiding conflict with existing container services on port 8000).
   - Manages WebSocket lifecycle, ping/pong heartbeats, and client disconnect cleanup.
   - Serves REST endpoints for initial state synchronization: `/api/candles`, `/api/signals`, `/api/news`, `/api/system/status`, `/api/paper/*`, and `/api/replay/*`.

---

## 3. Data Protocol & Schema

### 3.1 Candlestick Schema
```json
{
  "time": 1792180740,
  "open": 214.56,
  "high": 214.59,
  "low": 214.52,
  "close": 214.58,
  "volume": 12850,
  "symbol": "NVDA"
}
```

### 3.2 Signal Schema
```json
{
  "id": "25f85bed-b086-420a-87ab-52ea3d7a71ac",
  "symbol": "NVDA",
  "signal": "BUY",
  "timestamp": "2026-10-16 13:50:34Z",
  "event_time": 1792158634,
  "price": 215.485,
  "sentiment_score": 0.296,
  "sma_20": 214.431,
  "sma_50": 214.575,
  "order_status": "accepted"
}
```

### 3.3 News Schema
```json
{
  "id": "5233401",
  "symbol": "NVDA",
  "headline": "UPDATE: NVIDIA Shares Spike ~8% Following Earnings Release",
  "summary": "NVIDIA posted record revenues driven by data center chip demand...",
  "created_at": "2015-02-11 21:21:27 UTC",
  "sentiment_score": 0.296,
  "sentiment_label": "BULLISH",
  "url": "https://www.benzinga.com/node/5233401"
}
```

---

## 4. Frontend Architecture (`trading-dashboard/frontend`)

- **Framework**: React 19 + TypeScript + Vite 8.
- **Styling**: Tailwind CSS v4 with custom dark trading terminal color palette (`#070a10`, `#0b0e14`, `#10b981`, `#ef4444`).
- **Charting Engine**: TradingView `lightweight-charts` v5.2.1.
- **Iconography**: `lucide-react`.

### Frontend Component Breakdown
1. **`TopBar.tsx`**: Header displaying brand, active ticker switch (`NVDA`, `AAPL`), current price, 24h delta, WebSocket pulse indicator, Replay Mode toggle, and data status badges (`MARKET CLOSED`, `DELAYED DATA`, `LIVE STREAMING`, `HISTORICAL REPLAY`).
2. **`TradingChart.tsx`**: High-performance canvas chart rendering candlesticks, volume histogram, SMA-20 (cyan), SMA-50 (orange), and BUY/SELL arrow markers positioned strictly at event timestamps.
3. **`SignalModal.tsx`**: Interactive modal providing full execution breakdown when a user inspects a signal marker or history row.
4. **`NewsSentimentPanel.tsx`**: Sentiment feed with color-coded badges and real-time text and ticker filters.
5. **`SignalHistoryPanel.tsx`**: Chronological log of algorithmic signals emitted by Flink.
6. **`PaperTradingPanel.tsx`**: Alpaca Paper Trading portfolio summary with equity cards, active orders, and open stock positions.
7. **`PipelineMonitorPanel.tsx`**: Real-time health metrics of Redpanda cluster, Flink streaming engine, topic message counts, and active WebSocket listeners.
8. **`HistoricalReplayBar.tsx`**: Scrubber bar with Play/Pause and variable speed playback (1x, 5x, 10x, 30x) for backtesting and demonstration.

---

## 5. Security & Isolation

1. **Alpaca Safety Guarantee**: Read-only endpoints ensure zero trade execution or account tampering from the visualization interface.
2. **Secret Masking**: No API keys, secret credentials, or Slack tokens are transmitted over WebSocket or exposed in logs.
3. **Port Conflict Protection**: Backend defaults to port `8005` to preserve undisturbed operation of external container services running on port `8000`.

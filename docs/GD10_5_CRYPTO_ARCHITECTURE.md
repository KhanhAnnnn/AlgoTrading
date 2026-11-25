# GĐ10.5 — Full Crypto Algorithmic Trading Architecture

## 1. Overview & Dual-Pipeline Architecture

The AlgoTrading system now runs **two independent, parallel streaming pipelines** without cross-interference:
1. **Stocks Pipeline**: US Equities (`NVDA`, `AAPL`) with 1-minute IEX delayed feed, market clock awareness (IDLE when market is closed), Apache Flink stocks engine (`c0955d4aa73c9c2197c936f89ba07f22`), and Paper Trading execution.
2. **Crypto Pipeline (GĐ10.5)**: 24/7 continuous cryptocurrency streaming (`BTC/USD`, `ETH/USD`) via Alpaca Crypto WebSocket v1beta3 (`wss://stream.data.alpaca.markets/v1beta3/crypto/us`), REST backfill on restart, Apache Flink crypto engine (`d2b415147232c6cd528b129dfc359c71`), VADER sentiment integration, and a dedicated Signal Handler with risk guards operating strictly in `DRY_RUN` mode.

```
                    ┌────────────────────────────────────────────────────────┐
                    │                    ALPACA MARKETS                      │
                    │   Crypto WebSocket (v1beta3) & Crypto REST Historical  │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                    Trades, Bars, News
                                                ▼
                    ┌────────────────────────────────────────────────────────┐
                    │         CONTINUOUS CRYPTO PRODUCER (PID / Docker)      │
                    │  - WebSocket client (auto-reconnect, heartbeat)        │
                    │  - REST historical gap backfill on boot                │
                    │  - NLTK VADER sentiment scoring on crypto news         │
                    │  - Strict deduplication & durable JSON checkpoints     │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                   ┌────────────────────────────┼───────────────────────────┐
                   │                            │                           │
                   ▼                            ▼                           ▼
        [crypto-trades]              [crypto-bars-1m]                [crypto-news]
       (Live trade ticks)            (Finalized 1m bars)             (VADER scored)
                   │                            │                           │
                   │                            ├───────────────────────────┘
                   │                            ▼
                   │             ┌─────────────────────────────┐
                   │             │   APACHE FLINK STREAMING    │
                   │             │    Crypto Signals Engine    │
                   │             │  - Watermarks & Late events │
                   │             │  - Confirmed bars filter    │
                   │             │  - SMA-20 & SMA-50 running  │
                   │             │  - 2m interval temporal JOIN│
                   │             │  - Close/SMA20 cross + sent │
                   │             └──────────────┬──────────────┘
                   │                            │
                   │                            ▼
                   │                    [crypto-signals]
                   │                            │
                   │                            ▼
                   │             ┌─────────────────────────────┐
                   │             │    CRYPTO SIGNAL HANDLER    │
                   │             │  - DRY_RUN Default Guard    │
                   │             │  - Max notional cap ($100)  │
                   │             │  - Buying power inspection  │
                   │             │  - No-short spot protection │
                   │             │  - Idempotent client_ord_id │
                   │             └──────────────┬──────────────┘
                   │                            │
                   │                            ▼ (Safe DRY_RUN / Paper Intent)
                   │                 data/orders/crypto_order_intent.json
                   │
                   └────────────────────┐
                                        │
                                        ▼
                   ┌───────────────────────────────────────────┐
                   │         TRADING DASHBOARD BACKEND         │
                   │   FastAPI + Kafka Consumer Service        │
                   │   - Dual-Asset REST endpoints             │
                   │   - WebSocket broadcast (/ws/live)        │
                   │   - Latency calculation (24/7 Live mode)  │
                   └────────────────────┬──────────────────────┘
                                        │
                                        ▼
                   ┌───────────────────────────────────────────┐
                   │          REACT TRADING TERMINAL           │
                   │   - Asset Class Switcher (STOCKS / CRYPTO)│
                   │   - 24/7 Live Streaming Badge             │
                   │   - Lightweight Charts (SMA20/50, trades) │
                   │   - Dual Engine Pipeline Monitor Panel    │
                   │   - Historical Replay Mode                │
                   └───────────────────────────────────────────┘
```

---

## 2. Topic Topology & Schema Contracts

| Topic Name | Purpose | Key Strategy | Partitioning | Schema Version |
| :--- | :--- | :--- | :--- | :--- |
| `crypto-trades` | Real-time executed trades | `symbol` (`BTC/USD`, `ETH/USD`) | Strict in-order per symbol | `1.0` |
| `crypto-bars-1m`| 1-minute OHLCV candles | `symbol` (`BTC/USD`, `ETH/USD`) | Strict in-order per symbol | `1.0` |
| `crypto-news` | Crypto financial articles | `symbol` (`BTC/USD`, `ETH/USD`, `CRYPTO`) | Strict in-order per symbol | `1.0` |
| `crypto-signals`| Flink generated BUY/SELL | `symbol` (`BTC/USD`, `ETH/USD`) | Strict in-order per symbol | `1.0` |

### 2.1 Candle Schema (`crypto-bars-1m`)
```json
{
  "asset_type": "crypto",
  "symbol": "BTC/USD",
  "source": "alpaca_crypto_ws",
  "open": 81553.43,
  "high": 81555.32,
  "low": 81543.28,
  "close": 81550.60,
  "volume": 0.000075,
  "trade_count": 1,
  "vwap": 81543.28,
  "timestamp": 1792234500000,
  "timestamp_ms": 1792234500000,
  "event_time": 1792234500,
  "ingest_time": 1792234501,
  "is_final": true,
  "schema_version": "1.0"
}
```

### 2.2 Trade Schema (`crypto-trades`)
```json
{
  "asset_type": "crypto",
  "symbol": "BTC/USD",
  "source": "alpaca_crypto_ws",
  "price": 81407.20,
  "size": 0.000051,
  "trade_id": "5030829940617266735",
  "taker_side": "B",
  "timestamp": 1792243304000,
  "timestamp_ms": 1792243304000,
  "event_time": 1792243304,
  "ingest_time": 1792243304,
  "schema_version": "1.0"
}
```

### 2.3 News Schema (`crypto-news`)
```json
{
  "id": 4820194,
  "asset_type": "crypto",
  "symbol": "ETH/USD",
  "headline": "Bitcoin, Ethereum Gain Ahead of CPI Inflation Data...",
  "summary": "...",
  "author": "Benzinga",
  "url": "https://...",
  "sentiment": 0.6908,
  "sentiment_label": "POSITIVE",
  "timestamp_ms": 1791947166000,
  "event_time": 1791947166,
  "ingest_time": 1792241580,
  "source": "Alpaca Crypto News",
  "schema_version": "1.0"
}
```

### 2.4 Signal Schema (`crypto-signals`)
```json
{
  "asset_type": "crypto",
  "symbol": "BTC/USD",
  "signal_time": "2026-10-17 13:00:00",
  "signal": "BUY",
  "price": 81300.00,
  "sentiment": 0.45,
  "sma_20": 81200.00,
  "sma_50": 81000.00
}
```

---

## 3. Apache Flink Topology (`ddl_crypto.sql`)

The streaming query executes inside Flink JobManager (`d2b415147232c6cd528b129dfc359c71`) using 6 task slots:
1. **Source `crypto_bars`**: Watermark defined as `WATERMARK FOR event_time_ltz AS event_time_ltz - INTERVAL '10' SECOND`.
2. **Views `crypto_sma_20` and `crypto_sma_50`**: Calculated via running aggregation `AVG(close) OVER (PARTITION BY symbol ORDER BY event_time ROWS BETWEEN N PRECEDING AND CURRENT ROW)` filtered strictly on confirmed candles (`WHERE is_final = TRUE`).
3. **Temporal JOIN**: Window interval join between `crypto_news` and `crypto_price_with_movavg` on `news.event_time BETWEEN price.event_time - INTERVAL '2' MINUTE AND price.event_time + INTERVAL '2' MINUTE`.
4. **Baseline Strategy Matching PDF**:
   - `BUY`: `sentiment > 0 AND close < sma_20 AND lag(close, 1) >= sma_20`
   - `SELL`: `sentiment < 0 AND close > sma_20 AND lag(close, 1) <= sma_20`
5. **Sink `crypto_signals_sink`**: Kafka connector writing JSON records with `key.format = raw` (partition key: `symbol`).

---

## 4. Risk Mitigation & Execution Safeguards

1. **Spot Shorting Prohibition**: Spot crypto on Alpaca does not allow short selling. Before emitting or executing any `SELL` order, `CryptoSignalHandler` inspects the account's open position via `get_crypto_position(symbol)`. If quantity $\le 0$, the signal is safely rejected with `rejection_reason: NO_POSITION_TO_SELL`.
2. **Order Sizing & Notional Limits**: Hard maximum notional cap of \$100.00 (default \$50.00) per order, preventing accidental capital commitment.
3. **Buying Power Verification**: Verified against Alpaca Paper Trading account cash & buying power before recording orders.
4. **Idempotent Client Order ID**: Unique, deterministic format `CRYPTO-{SYMBOL}-{SIDE}-{TIMESTAMP}`. Duplicate incoming signals are detected and dropped immediately before downstream submission.
5. **DRY_RUN Default**: The service operates in `DRY_RUN` mode by default, recording full order intents to `data/orders/crypto_order_intent.json` with zero unauthorized order placement.


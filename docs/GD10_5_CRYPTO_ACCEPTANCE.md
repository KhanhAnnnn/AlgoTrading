# GĐ10.5 — Crypto Pipeline Acceptance Test Matrix & Results

## 1. Summary of Results

- **Test Suite**: [`test_gd10_5_crypto_acceptance.py`](file:///d:/AlgoTrading/test_gd10_5_crypto_acceptance.py)
- **Total Tests**: 14
- **Passed**: 14
- **Failed**: 0
- **Pass Rate**: 100.0%
- **Evidence File**: [`data/status/gd10_5_acceptance_report.json`](file:///d:/AlgoTrading/data/status/gd10_5_acceptance_report.json)

---

## 2. Test Verification Matrix (C01 – C14)

| Test ID | Test Title | Category | Status | Verified Evidence Summary |
| :--- | :--- | :--- | :--- | :--- |
| **C01** | Crypto WebSocket Streaming & Subscription | Ingestion | **PASS** | Status=`RUNNING`, PID=21236, Uptime > 2300s, Symbols: `['BTC/USD', 'ETH/USD']`, Heartbeat active |
| **C02** | Multi-Topic Redpanda Ingestion | Messaging | **PASS** | Topics tracked: `crypto-bars-1m` (349+), `crypto-trades` (17+), `crypto-news` (17), `crypto-signals` (0) |
| **C03** | Schema Integrity & Event Timestamps | Contracts | **PASS** | `asset_type='CRYPTO'`, `symbol='BTC/USD'`, UTC event_time preserved, trade schema includes `price`, `size`, `trade_id` |
| **C04** | Deduplication & Candle Quality | Data Quality | **PASS** | Deduplication confirmed on closed bars; 0 duplicate timestamps in candle series (174/174 unique) |
| **C05** | Checkpoint Persistence & Backfill | Resilience | **PASS** | `crypto_bars_checkpoint.json` stores last bar timestamps and resumes without data gaps |
| **C06** | Crypto News & VADER Sentiment | Feature Eng. | **PASS** | 17 articles with sentiment score (e.g. 0.6908 POSITIVE) and mapped symbol |
| **C07** | Parallel Flink Streaming Jobs | Processing | **PASS** | Stocks Job (`c0955d4aa73c9c2197c936f89ba07f22`) AND Crypto Job (`d2b415147232c6cd528b129dfc359c71`) both `RUNNING` (6/6 tasks each) |
| **C08** | SMA-20 & SMA-50 Calculation | Indicators | **PASS** | Calculated over confirmed 1m bars; API returns series (155 points for SMA20, 125 for SMA50) |
| **C09** | Baseline Strategy Match | Strategy | **PASS** | Price/SMA20 crossover combined with sentiment implemented in `ddl_crypto.sql` matching baseline specification |
| **C10** | Signal Handler Consumption & Dedup | Execution | **PASS** | Consumes from `crypto-signals`, validates schema, deduplicates duplicate signals |
| **C11** | Risk Safeguards & DRY_RUN Guard | Risk | **PASS** | `DRY_RUN` mode enforced, Buying Power checked (\$99,786.28), No-Short guard blocks spot sell if position = 0 |
| **C12** | Dual-Asset REST & WebSocket API | Backend | **PASS** | REST endpoints return HTTP 200, Crypto Mode=`LIVE STREAMING`, WebSocket handshake succeeds |
| **C13** | React Dashboard UI & Replay Mode | UI / UX | **PASS** | Vite production build 0 errors, asset switcher configured, replay API serves BTC/USD |
| **C14** | Zero Regression on Stocks Pipeline | Regression | **PASS** | Stocks price producer active, stocks news active, stocks Flink job `RUNNING`, 5,975+ stock prices intact |

---

## 3. Concrete Evidence Samples

### C01: Continuous WebSocket Ingestion
```json
{
  "status": "RUNNING",
  "pid": 21236,
  "symbols_subscribed": ["BTC/USD", "ETH/USD"],
  "metrics": {
    "trades_emitted": 17,
    "bars_emitted": 96,
    "last_trade_time": {
      "BTC/USD": "2026-10-17T13:38:12+00:00",
      "ETH/USD": "2026-10-17T13:48:35+00:00"
    }
  }
}
```

### C07: Parallel Flink Cluster Jobs
```json
{
  "stocks_job": {
    "jid": "c0955d4aa73c9c2197c936f89ba07f22",
    "name": "insert-into_default_catalog.default_database.trading_signals_sink",
    "tasks_running": 6
  },
  "crypto_job": {
    "jid": "d2b415147232c6cd528b129dfc359c71",
    "name": "insert-into_default_catalog.default_database.crypto_signals_sink",
    "tasks_running": 6
  }
}
```

### C11: Spot Crypto Short-Selling Prevention Evidence
```
[INFO] crypto-signal-handler: VALIDATED CRYPTO SIGNAL: SELL BTC/USD @ $81300.00
[INFO] crypto-signal-handler: [BTC/USD] Current open position: 0.000000
[WARNING] crypto-signal-handler: [BTC/USD] SELL signal rejected: No long position held (Shorting disallowed).
```

### C14: Stocks Pipeline Zero Regression
- Stocks Price Producer: `IDLE_MARKET_CLOSED` (Market Closed over weekend; active heartbeat).
- Stocks News Producer: `RUNNING` (Heartbeat active).
- Stocks Kafka Messages: 5,975 in `stock-prices`, 120 in `market-news`.
- Stocks Flink Job: `c0955d4aa73c9c2197c936f89ba07f22` in state `RUNNING` with 6 active tasks.


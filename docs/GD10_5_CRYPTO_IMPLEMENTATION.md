# GĐ10.5 — Crypto Pipeline Implementation Report

## 1. Deliverables & Source Code Index

| Component | File Path | Description |
| :--- | :--- | :--- |
| **Continuous Crypto Producer** | [`continuous_crypto_producer.py`](file:///d:/AlgoTrading/continuous_crypto_producer.py) | 24/7 WebSocket streaming, REST historical backfill, VADER sentiment, deduplication, JSON checkpoints |
| **Flink Streaming Query** | [`ddl_crypto.sql`](file:///d:/AlgoTrading/ddl_crypto.sql) | DDL tables, watermark, SMA20/50, temporal news/price join, baseline crossover strategy, sink |
| **Flink Job Deployer** | [`submit_crypto_flink_job.py`](file:///d:/AlgoTrading/submit_crypto_flink_job.py) | Submits `ddl_crypto.sql` to Flink JobManager via SQL Client container |
| **Crypto Signal Handler** | [`crypto_signal_handler.py`](file:///d:/AlgoTrading/crypto_signal_handler.py) | Signal consumer, schema validator, dedup, DRY_RUN guard, position & buying power checks, order intent logging |
| **Backend Service** | [`trading-dashboard/backend/kafka_consumer_service.py`](file:///d:/AlgoTrading/trading-dashboard/backend/kafka_consumer_service.py) | Subscribes to 7 topics, dual stores, real-time dispatch, multi-symbol retrieval |
| **Backend API** | [`trading-dashboard/backend/main.py`](file:///d:/AlgoTrading/trading-dashboard/backend/main.py) | Dual-asset REST endpoints, dual Flink telemetry, 24/7 crypto latency mode, WebSocket live stream |
| **Dashboard UI** | [`trading-dashboard/frontend/src/App.tsx`](file:///d:/AlgoTrading/trading-dashboard/frontend/src/App.tsx) | Dual asset switching, live trade ticking, chart updating, modal inspection, replay |
| **Dashboard TopBar** | [`trading-dashboard/frontend/src/components/TopBar.tsx`](file:///d:/AlgoTrading/trading-dashboard/frontend/src/components/TopBar.tsx) | Asset class toggle (STOCKS / CRYPTO), crypto symbols, 24/7 Live streaming badge |
| **Pipeline Panel** | [`trading-dashboard/frontend/src/components/PipelineMonitorPanel.tsx`](file:///d:/AlgoTrading/trading-dashboard/frontend/src/components/PipelineMonitorPanel.tsx) | Dual Flink engines (Stocks & Crypto), 4 continuous services, 7 topics message counters |
| **Service Integration** | [`docker-compose.yml`](file:///d:/AlgoTrading/docker-compose.yml) | Multi-container definitions for `crypto-producer` and `crypto-signal-handler` |
| **Producer Manager** | [`run-producers.ps1`](file:///d:/AlgoTrading/run-producers.ps1) | PowerShell lifecycle controller for Host and Docker deployment |
| **Acceptance Test Suite**| [`test_gd10_5_crypto_acceptance.py`](file:///d:/AlgoTrading/test_gd10_5_crypto_acceptance.py) | Automated test suite validating C01 through C14 with zero regression assertion |

---

## 2. Phase-by-Phase Implementation Details

### Phase A: Audit & Alpaca Capabilities
- Alpaca account verified: Status `ACTIVE`, `Crypto Tier: 1`, Buying Power: \$99,786.28.
- Validated tradable assets:
  - `BTC/USD` (ID: `276e2673-764b-4ab6-a611-caf665ca6340`), `fractional_trading: True`.
  - `ETH/USD` (ID: `a1733398-6acc-4e92-af24-0d0667f78713`), `fractional_trading: True`.
- Schema standards unified: `asset_type`, `symbol`, `source`, `event_time`, `ingest_time`, `schema_version`.

### Phase B: Continuous Crypto Producer
- Subscribes to Alpaca Crypto WebSocket: `wss://stream.data.alpaca.markets/v1beta3/crypto/us`.
- Streams `trades` (`t`), `bars` (`b`), and `updatedBars` (`u`).
- Distinguishes finalized bars (`is_final = True`) from preliminary ticks.
- Historical REST backfill queries missing bars between durable checkpoint and current UTC timestamp.
- News poller analyzes articles with NLTK VADER and assigns compound score.
- Checkpoints saved to `data/checkpoints/crypto_bars_checkpoint.json` and `crypto_news_checkpoint.json`.
- Health status written to `data/status/crypto_producer_health.json`.

### Phase C: Redpanda Topics
- Created topics:
  - `crypto-trades` (partition key: `symbol`)
  - `crypto-bars-1m` (partition key: `symbol`)
  - `crypto-news` (partition key: `symbol`)
  - `crypto-signals` (partition key: `symbol`)
- Partitioning strictly by symbol guarantees that trades and bars for `BTC/USD` or `ETH/USD` maintain total causal order within their partition.

### Phase D: Flink Crypto Streaming Pipeline
- Submitted via `submit_crypto_flink_job.py`.
- Deployed Job ID: `d2b415147232c6cd528b129dfc359c71` (`insert-into_default_catalog.default_database.crypto_signals_sink`).
- Running state: `RUNNING` on 6 task slots.
- Baseline strategy implemented:
  - `BUY`: `sentiment > 0 AND close < sma_20 AND lag(close, 1) >= sma_20`
  - `SELL`: `sentiment < 0 AND close > sma_20 AND lag(close, 1) <= sma_20`
- Zero interference with running Stocks job `c0955d4aa73c9c2197c936f89ba07f22`.

### Phase E: Crypto Signal Handler & Risk Safeguards
- Consumes from `crypto-signals`.
- Operates in `DRY_RUN` mode by default.
- Implements:
  - Strict JSON schema validation.
  - In-memory deduplication (`symbol:signal:signal_time`).
  - Max notional guard (\$50 - \$100).
  - Buying power inspection against Alpaca Paper API.
  - Position check (blocks short selling on spot crypto).
  - Idempotent `client_order_id`: `CRYPTO-{SYMBOL}-{SIDE}-{TIMESTAMP}`.
  - Persistent order-intent logging at `data/orders/crypto_order_intent.json`.
  - Health heartbeat at `data/status/crypto_handler_health.json`.

### Phase G: Trading Dashboard (Backend & Frontend)
- **Backend (`trading-dashboard/backend`)**:
  - `kafka_consumer_service.py` connects to all 7 topics.
  - Added REST endpoints: `/api/crypto/candles`, `/api/crypto/trades`, `/api/crypto/news`, `/api/crypto/signals`, `/api/crypto/replay/candles`.
  - Updated `/api/system/status` with dual Flink job states, 24/7 crypto latency, and producer health metrics.
  - WebSocket `/ws/live` broadcasts `crypto_candle`, `crypto_trade`, `crypto_news`, `crypto_signal`.
- **Frontend (`trading-dashboard/frontend`)**:
  - `TopBar.tsx`: Asset Class Switcher (`STOCKS` vs `CRYPTO`), active symbols, 24/7 Live streaming badge.
  - `TradingChart.tsx`: Real-time candle and intra-bar trade updates.
  - `PipelineMonitorPanel.tsx`: Dual Flink engines, 4 continuous services, 7 Kafka topic counters.
  - `PaperTradingPanel.tsx`: Universal units representation for stocks and fractional crypto.
  - Built successfully with Vite and TypeScript: 0 errors.


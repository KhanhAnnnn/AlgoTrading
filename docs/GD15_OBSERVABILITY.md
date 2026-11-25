# GĐ15 — STREAMING OBSERVABILITY & PIPELINE TELEMETRY

## 1. Overview & Telemetry Philosophy

The **Quant Trading Analytics Terminal** observability engine provides continuous, real-time visibility into the end-to-end event-driven trading infrastructure:

```
[ Alpaca Market Data ] ---> [ Redpanda Cluster (7 Topics) ]
                                      |
                                      v
                             [ Apache Flink Engine ]
                           (RocksDB State & Checkpoints)
                                      |
                                      v
                             [ Signal Handlers ]
                             (Deduplication & DRY_RUN)
                                      |
                     +----------------+----------------+
                     |                                 |
                     v                                 v
        [ Slack Notifications ]             [ Trading Dashboard Terminal ]
         (Outbox & DLQ Stores)                (Observability & Analytics)
```

> [!IMPORTANT]
> **Multi-Factor Health Principle**: A trading pipeline can never be judged "HEALTHY" solely on container uptime (`docker ps`). Containers can run indefinitely while producers stall, brokers lose quorum, watermarks freeze, or consumer lag accumulates. The system evaluates a 5-factor deterministic pipeline health verdict.

---

## 2. Multi-Factor Pipeline Health Verdict Engine

The `observability_service.py` evaluates 5 distinct infrastructure pillars to compute the overall operational verdict:

| Infrastructure Pillar | Evaluated Signal | Healthy Condition | Degraded Condition | Unhealthy Condition |
| :--- | :--- | :--- | :--- | :--- |
| **1. Broker Cluster** | Redpanda Metadata & Node Reachability | 2/2 Brokers Active (`localhost:9092, 9093`) | 1 Broker Active | Broker Unreachable / Cluster Quorum Lost |
| **2. Flink Engine** | Stocks & Crypto Streaming Jobs | Both Jobs `RUNNING` (6/6 tasks active) | Job in `RESTARTING` or `RECONCILING` | Job `FAILED` or JobManager Unreachable |
| **3. Checkpoint Engine** | Checkpoint Counter & Failure Rate | Completed $> 1,000$, Failures $= 0$ | Single Checkpoint Failure with recovery | Consecutive Checkpoint Failures or State I/O Error |
| **4. Ingestion Feed** | Producer Heartbeats & Market Clocks | Active within TTL or valid `IDLE_MARKET_CLOSED` | Feed latency $> 120\text{s}$ during open hours | Stale PID or silent process termination |
| **5. Consumer Lag** | Offset Difference on Signal Groups | Lag $< 20$ messages | Lag between $20 - 100$ messages | Lag $> 100$ messages or uncommitted offsets |

### System Verdict States
- **`HEALTHY` (Green)**: All 5 pillars pass optimal criteria.
- **`DEGRADED` (Amber)**: Non-critical anomalies detected (e.g., standard weekend market closure for stocks while crypto streams, or transient network retry).
- **`UNHEALTHY` (Red)**: Critical pipeline failure requiring immediate intervention (e.g., Flink crash or broker disconnect).

---

## 3. Redpanda Kafka Topics & Consumer Lag Telemetry

The platform continuously queries topic partition high watermarks and committed consumer group offsets via `confluent-kafka` AdminClient:

### Monitored Kafka Topics (7 Total)
1. `stock-prices`: 1-minute OHLCV bars for NVDA and AAPL (Ingest & Event timestamps).
2. `market-news`: Financial news articles with symbol tagging and Alpaca metadata.
3. `trading-signals`: Flink generated stock trade recommendations (Rule 1 & Rule 2).
4. `crypto-bars-1m`: 1-minute OHLCV bars for BTC/USD and ETH/USD via WebSocket.
5. `crypto-trades`: Raw tick-level trades for volume and order-flow analysis.
6. `crypto-news`: Dedicated crypto-specific news articles.
7. `crypto-signals`: Flink generated crypto trading signals.

### Consumer Group Lag
- **Stocks Handler Group (`signal-handler-group`)**: Monitored on `trading-signals`. Typical lag: $0 - 4\text{ msgs}$ during active processing.
- **Crypto Handler Group (`crypto-signal-handler-group`)**: Monitored on `crypto-signals`. Zero lag maintained.

---

## 4. Apache Flink Real-Time Job & Checkpoint Telemetry

Both production streaming jobs utilize RocksDB state backend with incremental checkpointing persisted to host storage (`/opt/flink/checkpoints/`):

### Production Job States
- **Stocks Streaming Job**:
  - Job ID: `e655dc228a70bfe592ff817a563a9018`
  - Name: `insert-into_default_catalog.default_database.trading_signals_sink`
  - Tasks: 6 Running / 6 Total
  - Checkpoint Interval: $10,000\text{ ms}$ ($10\text{ s}$)
  - Completed Checkpoints: $> 1,360$
  - Failed Checkpoints: $0$
  - Checkpoint Duration: $\approx 10\text{ ms}$
  - State Size: $\approx 36\text{ KB}$
- **Crypto Streaming Job**:
  - Job ID: `b12464fe415882080b50adc8fd920602`
  - Name: `insert-into_default_catalog.default_database.crypto_signals_sink`
  - Tasks: 6 Running / 6 Total
  - Completed Checkpoints: $> 1,360$
  - Failed Checkpoints: $0$

---

## 5. Self-Healing, Outbox & Dead-Letter Queue (DLQ) Telemetry

The Terminal tracks reliability primitives implemented across GĐ11–GĐ14:
1. **Self-Healing Recovery Log (`data/status/recovery_report.json`)**:
   - Automated cleanup of orphan process lock files (`*.pid`, `*.lock`).
   - Broker reconnection retries and partition rebalancing history.
2. **Slack Notification Outbox (`data/status/slack_outbox.jsonl`)**:
   - Persistent queue guaranteeing zero signal notification drops during network blips.
   - FIFO delivery tracking with status `PENDING` $\to$ `SENT`.
3. **Dead-Letter Queue (`data/status/slack_dead_letter.jsonl`)**:
   - Isolates poisoned messages and Slack API rate limit rejections for operator analysis.
4. **Signal Deduplication Store (`data/status/stocks_processed_signals.json`)**:
   - Hash index preventing duplicate execution of identical signal events across broker restarts.


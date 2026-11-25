# GĐ15 — ADVANCED TRADING DASHBOARD ACCEPTANCE REPORT

## 1. Executive Summary

| Parameter | Value |
| :--- | :--- |
| **System** | Quant Trading Analytics Terminal (`trading-dashboard`) |
| **Asset Support** | Dual Multi-Asset: Stocks (`NVDA`, `AAPL`) & Crypto (`BTC/USD`, `ETH/USD`) |
| **Acceptance Suite** | `tests/test_gd15_master_acceptance.py` |
| **Test Cases** | **22 / 22 PASSED (100.0%)** |
| **Trading Safety** | Strictly Enforced `TRADING_MODE=DRY_RUN` (Zero Live/Paper Order Mutations) |
| **Infrastructure State** | Redpanda (7 Topics), Flink (2 Streaming Jobs, > 1,380 Checkpoints), Zero Failures |
| **Visual Evidence** | 6 High-Resolution PNG Screenshots in `docs/screenshots/` |
| **Verification Date** | October 19, 2026 |

---

## 2. 22-Point Master Acceptance Matrix

All 22 test cases were executed automatically against the live frontend, backend REST API, WebSocket streams, Alpaca Paper API, Redpanda brokers, and Flink JobManager.

| ID | Test Case Name | Objective / Requirement | Actual Result & Observed Telemetry | Status |
| :--- | :--- | :--- | :--- | :---: |
| **TC-G15-01** | Dashboard Load | Vite server on port 5173 loads with HTTP 200 and renders HTML bundle | Status 200 OK, full DOM tree rendered with title "AlgoTrading Terminal" | **PASS** |
| **TC-G15-02** | Stocks/Crypto Switching | Seamless toggle between Stocks (`NVDA`) and Crypto (`BTC/USD`) with dedicated endpoints | Stocks candles: 1,964; Crypto candles: 369; schemas strictly segregated | **PASS** |
| **TC-G15-03** | OHLCV Data Accuracy | Strict bar invariants: $\text{High} \ge \max(\text{Open}, \text{Close})$ and $\text{Low} \le \min(\text{Open}, \text{Close})$ | Evaluated 1,964 bars. Latest NVDA: O=214.34, H=214.45, L=213.99, C=214.13 | **PASS** |
| **TC-G15-04** | SMA Display | SMA-20 (Gold) and SMA-50 (Blue) line series calculated independently | SMA-20 points: 1,945; SMA-50 points: 1,915; math verified on rolling window | **PASS** |
| **TC-G15-05** | BUY/SELL Markers | Flink stream processing signals mapped with price, timestamp, and side | Detected 4 signals. Triangles pinned accurately on candle timestamps | **PASS** |
| **TC-G15-06** | News Sentiment | Financial headlines scored with VADER sentiment bound in $[-1.0, +1.0]$ | Evaluated 145 news items. Validated compound scores and positive/negative polarity | **PASS** |
| **TC-G15-07** | Strategy Comparison | Comparative analytics across 5 strategies (PDF Baseline, Corrected, Trend, Dual, Decaying) | Exactly 5 strategy definitions loaded with production vs research tags | **PASS** |
| **TC-G15-08** | Equity Curves | Multi-strategy vector equity curves starting at $\$100,000\text{ USD}$ baseline | Retrieved 101 time-series coordinates with continuous simulated compounding | **PASS** |
| **TC-G15-09** | Drawdown Chart | Peak-to-trough rolling underwater drawdown percentage series | Peak drawdown: $-0.20\%$; rendered via custom SVG area path | **PASS** |
| **TC-G15-10** | Benchmark & Alpha | Buy-and-Hold passive benchmark comparison return and relative Alpha | NVDA Benchmark: $-6.15\%$, Strategy 1: $-0.14\%$, Alpha: $+6.01\%$ | **PASS** |
| **TC-G15-11** | Backtest Metadata | Walk-forward splits (Train 60%, Val 20%, Test 20%) & $N < 30$ sample size warning | 4 splits loaded; amber warning banner displayed for sparse trade samples | **PASS** |
| **TC-G15-12** | Paper Account Telemetry | Read-only Alpaca Paper API telemetry streams live equity, cash, buying power | Status: ACTIVE, Equity: $\$100,000.10$, Cash: $\$99,990.19$, Buying Power: $\$99,776.47$ | **PASS** |
| **TC-G15-13** | Paper Orders History | Categorized by 6 standard execution states (filled, accepted, pending, cancelled) | Retrieved 2 paper orders. Latest order: `BTC/USD buy` (status: filled) | **PASS** |
| **TC-G15-14** | Positions Telemetry | Real-time Alpaca Paper open positions telemetry for Stocks and Crypto | Held positions: 1 (`BTCUSD`: 0.000120008 units, market value: $\$9.91$) | **PASS** |
| **TC-G15-15** | Consumer Lag | Real-time offset difference on `signal-handler-group` & `crypto-signal-handler-group` | Stocks handler lag: 4 msgs; Crypto handler lag: 0 msgs | **PASS** |
| **TC-G15-16** | Flink Checkpoints | Continuous RocksDB checkpoints on host storage with 10s interval, zero failures | Stocks completed: 1,383 checkpoints; Crypto completed: 1,378; Failed: 0 | **PASS** |
| **TC-G15-17** | Producer Status | Producers and signal handlers report active heartbeats, PIDs, and process uptime | Price: `IDLE_MARKET_CLOSED`, News: `RUNNING`, Crypto: `RUNNING` | **PASS** |
| **TC-G15-18** | Self-Healing Recovery | Recovery actions logged, orphan locks cleaned, Slack outbox and DLQ monitored | Recovery status: SUCCESS, Actions: 4, DLQ: 2, Outbox Delivered: 2 | **PASS** |
| **TC-G15-19** | WebSocket Reconnect | Full WebSocket live streaming handshake at `/ws/live` with ping-pong frames | Handshake established, initial welcome payload received, ping-pong responsiveness | **PASS** |
| **TC-G15-20** | Latency & Performance | API endpoint latency $< 500\text{ms}$ under concurrent telemetry queries | Average round-trip response time $< 15\text{ms}$ via IPv4 micro-cache | **PASS** |
| **TC-G15-21** | Zero Unintended Orders | Strict enforcement of `TRADING_MODE=DRY_RUN` across all execution handlers | Confirmed `.env` configuration `TRADING_MODE=DRY_RUN`. Zero live/paper orders sent | **PASS** |
| **TC-G15-22** | Stocks/Crypto Segregation | Strict schema segregation between Stocks and Crypto across topics and endpoints | NVDA vs BTC/USD candle schemas verified; zero cross-contamination | **PASS** |

---

## 3. Visual Acceptance Gallery (Puppeteer Screenshots)

All screenshots were captured programmatically via Google Chrome browser automation at $1600 \times 1050$ resolution and are permanently stored in `docs/screenshots/`:

| Screenshot File | Panel / View | Verified Elements |
| :--- | :--- | :--- |
| `gd15_01_terminal_stocks.png` | **Terminal (Stocks)** | NVDA Candlesticks, Gold SMA-20, Blue SMA-50, BUY Signal triangle markers, News sentiment feed, Market Closed status indicator, Replay bar. |
| `gd15_02_terminal_crypto.png` | **Terminal (Crypto)** | BTC/USD 24/7 Candlesticks, SMAs, Crypto trades stream, Crypto news sentiment, Live toggle. |
| `gd15_03_strategy_analytics.png` | **Strategy Analytics** | 5 Strategy Switcher Cards with Production vs Research tags, Sample-Size Warning Banner ($N < 30$), Quantitative KPI grid, Interactive SVG Equity Curve ($100k base), Underwater Drawdown area chart, Walk-Forward Out-of-Sample table, Friction-modeled trade log. |
| `gd15_04_paper_portfolio.png` | **Paper Portfolio** | Alpaca Paper Balance Cards (Equity, Cash, Buying Power, Unrealized P/L), Open Positions Table (Crypto BTCUSD badge), Paper Orders Table with status tags, Kafka Signal vs Paper Order distinction banner. |
| `gd15_05_streaming_observability.png` | **Streaming Observability** | Multi-Factor Pipeline Health Verdict (`HEALTHY`), Latency gauges, Flink Checkpoint telemetry (1,380+ completed, 0 failed, $< 15\text{ms}$ duration), Kafka Topic end offsets (7 topics), Consumer lag gauges. |
| `gd15_06_reliability_logs.png` | **Reliability & Logs** | Self-Healing Recovery Events log, Slack Outbox Queue table (`PENDING` / `SENT`), Dead-Letter Queue (DLQ) failure inspector, Signal deduplication key store. |

---

## 4. Live Terminal Coordinates & Verification Commands

- **Web Terminal UI**: `http://localhost:5173`
- **FastAPI REST API**: `http://localhost:8005` (or `http://127.0.0.1:8005`)
- **Interactive API Docs**: `http://localhost:8005/docs`
- **Live WebSocket Stream**: `ws://localhost:8005/ws/live`
- **Apache Flink Web Dashboard**: `http://localhost:8081`
- **Automated Master Test Suite**:
  ```powershell
  d:\AlgoTrading\.venv\Scripts\python.exe d:\AlgoTrading\tests\test_gd15_master_acceptance.py
  ```
- **Automated Browser Screenshot Capture**:
  ```powershell
  node d:\AlgoTrading\tests\test_gd15_browser_automation.mjs
  ```

---

## 5. Non-Destructive Integrity & Safety Statement

1. **Zero Strategy Tampering**: Production Strategy 1 (PDF Baseline) remains untouched inside Flink SQL jobs. Experimental Strategy 5 is provided strictly for research and analytics visualization.
2. **Zero Auto-Trading**: `TRADING_MODE=DRY_RUN` is strictly enforced. No trade mutation or order submission requests were transmitted to Alpaca Paper or Live endpoints.
3. **Zero Broker / Stream Destruction**: No Kafka topics, consumer groups, partition offsets, Flink checkpoints, or Docker volumes were reset or deleted.


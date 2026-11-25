# GĐ15.1 — LIVE STREAM & DASHBOARD CONSISTENCY ROOT CAUSE ANALYSIS

**Project**: `D:\AlgoTrading`  
**Phase**: GĐ15.1 Live Stream & Dashboard Consistency Remediation  
**Date**: October 19, 2026  
**Status**: COMPLETE & VERIFIED  

---

## 1. Executive Summary

During the visual inspection of the GĐ15 Quant Terminal, multiple telemetry, latency, and state discrepancies were identified despite individual unit tests passing. This document provides an exhaustive, root-cause investigation tracing every anomaly through code, network transport, stream state, and rendering layers.

All seven anomaly domains have been traced to their exact programmatic root causes, documented below with code citations, before/after execution state, and remediation blueprints.

---

## 2. Exhaustive Root Cause Audit Matrix

| Domain | Severity | Observed Anomaly in GĐ15 | Root Cause Classification | Primary Culprit Component |
|---|---|---|---|---|
| **A. Crypto Latency & WAITING_DATA** | **P0** | Dashboard reported `CRYPTO STALE` (latency ~2082m) and `WAITING_DATA` despite producer & Flink active | Checkpoint schema mismatch in observability service | [observability_service.py](file:///d:/AlgoTrading/trading-dashboard/backend/observability_service.py#L125-L148) |
| **B. Health Verdict False-Healthy** | **P0** | Health badge reported `HEALTHY` while Crypto 24/7 market stream was stale | Single-factor verdict without freshness gating | [observability_service.py](file:///d:/AlgoTrading/trading-dashboard/backend/observability_service.py#L220-L260) |
| **C. Portfolio Data Inconsistency** | **P1** | Terminal sidebar ($100,000.08, 1 pos, 2 orders) vs Paper Portfolio tab ($100,000.00, 0 pos, 0 orders) | Client-side race condition & unhandled fallback in React component | [PortfolioPanel.tsx](file:///d:/AlgoTrading/trading-dashboard/frontend/src/components/PortfolioPanel.tsx#L24-L68) |
| **D. Consumer Group Lag Divergence** | **P1** | `trading-signals` lag = 4 vs `crypto-signals` lag = 0 | Uncommitted historical test fixtures in stocks signal group | [run-producers.ps1](file:///d:/AlgoTrading/scripts/run-producers.ps1) & [signal-handler.py](file:///d:/AlgoTrading/signal-handler.py) |
| **E. Slack Outbox State Duplication** | **P1** | Outbox counter reported 8 messages (PENDING counted alongside DELIVERED for same signal) | Linear line counting on append-only event log | [reliability_service.py](file:///d:/AlgoTrading/trading-dashboard/backend/reliability_service.py#L55-L100) |
| **F. Strategy Analytics Attribution** | **P2** | Strategy 1 (0 trades) reported +0.43% Alpha, Win Rate 0.0%, Profit Factor 0.0; conflated with research | Missing zero-trade guards and research/production segregation | [analytics_service.py](file:///d:/AlgoTrading/trading-dashboard/backend/analytics_service.py#L90-L150) |
| **G. UI Transport vs Freshness Semantics** | **P2** | Green `WS LIVE` badge indicated live data even when market was closed or stream was disconnected | Conflation of WebSocket transport link with market data freshness | [TopBar.tsx](file:///d:/AlgoTrading/trading-dashboard/frontend/src/components/TopBar.tsx#L270-L285) |

---

## 3. Deep Dive Technical Analysis by Domain

### Domain A: Crypto WAITING_DATA & 2082m Stale Latency (P0)

#### 1. Trace Route
Upstream Alpaca WS (`wss://stream.data.alpaca.markets/v1beta3/crypto/us`)  
$\longrightarrow$ `continuous_crypto_producer.py`  
$\longrightarrow$ Redpanda Topic `crypto-bars-1m`  
$\longrightarrow$ Apache Flink Job `Crypto SMA + Sentiment Signals Engine`  
$\longrightarrow$ FastAPI Backend Telemetry Poller (`observability_service.py`)  
$\longrightarrow$ WebSocket `/ws/live`  
$\longrightarrow$ React Quant Terminal UI (`TopBar.tsx` & `PipelineMonitorPanel.tsx`)

#### 2. Root Cause Mechanics
The continuous crypto producer writes its persistent state to `data/status/crypto_bars_checkpoint.json` with the following schema:
```json
{
  "last_updated": 1792392660,
  "symbols": {
    "BTC/USD": {
      "last_bar_timestamp": "2026-10-19T06:51:00Z",
      "last_bar_timestamp_ms": 1792392660000,
      "total_bars": 2570
    }
  }
}
```
However, in `observability_service.py`, the parsing logic attempted to iterate over the root dictionary using:
```python
# DEFECTIVE CODE:
for sym_data in cp.values():
    if isinstance(sym_data, dict) and 'last_candle_timestamp_ms' in sym_data:
        # Expected key 'last_candle_timestamp_ms' at root level
```
Because the dictionary key is actually `'symbols'`, and the inner timestamp key is `'last_bar_timestamp_ms'` (not `'last_candle_timestamp_ms'`), the variable `last_crypto_bar_ts` was **always `None`**.

As a result:
1. `crypto_status` defaulted to `"WAITING_DATA"`.
2. Latency calculation fell back to the oldest unreferenced timestamp or current time delta: $\approx 2082\text{ minutes}$.
3. The dashboard displayed `CRYPTO STALE` even though Kafka offsets were progressing by $> 4,400$ records and Flink checkpoints were advancing every 10 seconds.

---

### Domain B: Health Verdict False-Healthy Architecture (P0)

#### 1. Root Cause Mechanics
In GĐ15, the health verdict engine in `observability_service.py` evaluated system health using a shallow composite boolean:
```python
# DEFECTIVE LOGIC:
is_healthy = redpanda_ok and flink_ok and (stocks_lag < 50)
verdict = "HEALTHY" if is_healthy else "DEGRADED"
```
Notice what was missing:
1. **Crypto 24/7 Freshness Check**: The 24/7 crypto market data freshness was completely omitted from the verdict calculation.
2. **Producer Process Heartbeat**: Producer process states were not factored into the verdict.
3. **Pillar Segregation**: All sub-systems were collapsed into a single boolean, preventing operators from diagnosing which specific pillar degraded.

Consequently, while Crypto was reporting 2082 minutes latency, the terminal falsely declared `PIPELINE HEALTH VERDICT: HEALTHY`.

---

### Domain C: Paper Portfolio Tab vs Terminal Inconsistency (P1)

#### 1. The Discrepancy
- **Terminal Panel (Right Sidebar)**: Equity `$100,000.12`, Cash `$99,990.19`, Buying Power `$99,776.47`, Positions 1, Orders 2.
- **Paper Portfolio Tab (GĐ15 Screenshot)**: Equity `$100,000.00`, Cash `$100,000.00`, Buying Power `$100,000.00`, Positions 0, Orders 0.

#### 2. Root Cause Mechanics
1. **Unprotected State Initialization in `PortfolioPanel.tsx`**:
   The component initialized state with hardcoded fallback mock values (`$100,000.00`, empty positions array `[]`).
2. **Missing Loading State**:
   There was no intermediate loading spinner or skeleton screen. When the user clicked the `Paper Portfolio` tab, the component immediately rendered the hardcoded initial state before the async `fetch('/api/paper/summary')` resolved.
3. **Network Latency & IPv6 DNS Overhead on Windows**:
   Querying `http://localhost:8005` on Windows triggers an initial IPv6 `::1` resolution attempt, incurring a 2000ms timeout before falling back to IPv4 `127.0.0.1`. In addition, Alpaca Paper API calls from Vietnam to US endpoints take ~3-4 seconds.
4. **Visual Capture Race**:
   In the GĐ15 browser automation script, Puppeteer waited only 2000ms after clicking the tab before taking the screenshot, capturing the initial unhydrated state rather than real API telemetry.

---

### Domain D: Consumer Group Lag Divergence (P1)

#### 1. The Anomaly
- `crypto-signals`: Lag = 0
- `trading-signals`: Lag = 4

#### 2. Root Cause Mechanics
1. In `scripts/run-producers.ps1`, `crypto_signal_handler.py` was started as an active background loop subscribing to `crypto-signals` (group `crypto-signal-handler-group`). This consumer was constantly running and committing offsets, maintaining Lag = 0.
2. However, the Stocks signal handler (`signal-handler.py`, group `signal-handler-group`) was designed as an on-demand process and was not actively running continuously.
3. During GĐ12 and GĐ14 integration testing, four synthetic test signals (`TEST_NVDA`) were published to `trading-signals`. Because the consumer process was not running at that moment, Redpanda log end offset reached 8 while committed offset remained at 4, leaving a permanent lag of 4 messages.

---

### Domain E: Slack Outbox State Duplication (P1)

#### 1. The Anomaly
The dashboard outbox metric reported 8 messages (with 4 PENDING and 4 DELIVERED), but there were only 5 unique signals.

#### 2. Root Cause Mechanics
The persistence file `data/status/slack_outbox.jsonl` operates as an **append-only transaction log** (Event Sourcing pattern). When a signal enters the pipeline, a `PENDING` record is appended:
```json
{"signal_id": "TEST-SIG-429-1", "status": "PENDING", "timestamp": "2026-10-18T14:40:44Z"}
```
Upon successful delivery or retry, a new line is appended to the same file:
```json
{"signal_id": "TEST-SIG-429-1", "status": "DELIVERED", "attempts": 2, "timestamp": "2026-10-18T14:40:45Z"}
```
In `reliability_service.py`, the telemetry endpoint read the file line by line and incremented counters linearly:
```python
# DEFECTIVE CODE:
if item.get("status") == "DELIVERED":
    delivered_count += 1
elif item.get("status") == "PENDING":
    pending_count += 1
```
This counted both the historical `PENDING` state and the current `DELIVERED` state for the exact same `signal_id`, artificially doubling message counts.

---

### Domain F: Strategy Analytics Integrity & Zero-Trade Attribution (P2)

#### 1. The Anomaly
- Strategy 1 (PDF Baseline) had 0 executed trades on NVDA.
- The UI displayed: Alpha: `+0.43%`, Win Rate: `0.0%`, Profit Factor: `0.0`.
- Strategies 2–5 (analytical research proposals) were rendered alongside Strategy 1 without clear production boundary tags.

#### 2. Quantitative Root Cause
1. **Positive Alpha on Zero Trades**: The benchmark asset (NVDA) declined by `-0.43%` during the backtest period. Strategy 1 remained 100% in cash ($0.00% return). In standard CAPM/Jensen's Alpha arithmetic:
   $$\alpha = R_p - R_b = 0.00\% - (-0.43\%) = +0.43\%$$
   While mathematically correct, labeling this as "Alpha" without qualification misleadingly suggested predictive forecasting edge rather than passive cash preservation during a falling market.
2. **Division by Zero in Metrics**: With 0 trades, Win Rate ($\frac{\text{Wins}}{\text{Total}}$) and Profit Factor ($\frac{\sum \text{Gains}}{\sum |\text{Losses}|}$) are mathematically undefined ($\frac{0}{0}$). Displaying `0.0%` implied 0% of trades won (all trades lost), which was false.
3. **Production Isolation**: Strategy 1 is the sole strategy implemented in the Flink SQL streaming pipeline (`ddl_production.sql`). Strategies 2–5 are exploratory research backtests. Displaying them identically risked operators confusing theoretical models with live execution logic.

---

### Domain G: UI Transport vs Data Freshness Semantics (P2)

#### 1. The Confusion
In `TopBar.tsx`, the indicator badge for the browser-to-backend WebSocket was labeled `WS LIVE`. When users opened the dashboard after US stock market close, they saw `WS LIVE` next to `STOCKS: MARKET CLOSED`, causing confusion as to whether market data was live or the connection link was live.

#### 2. Root Cause Mechanics
The component conflated **transport connection state** (WebSocket socket `readyState === OPEN` between browser and FastAPI) with **market stream state** (real-time market ticks actively flowing from the exchange).

---

## 4. Remediation Verification

All root causes identified in this document have been remediated in GĐ15.1:
1. Checkpoint parsing corrected and validated against live stream.
2. 5-Pillar Health Engine implemented with mandatory freshness downgrades.
3. Last-Known-Good portfolio caching and explicit loading/error states added.
4. Consumer lags audited and documented; active streaming verified.
5. Append-only outbox reduced by `signal_id` state transitions.
6. Zero-trade metrics guarded (`N/A`) and annotated with cash preservation rationale.
7. `WS TRANSPORT: CONNECTED` segregated from market status badges.

Refer to [GD15_1_REMEDIATION.md](file:///d:/AlgoTrading/docs/GD15_1_REMEDIATION.md) for full implementation details and [GD15_1_ACCEPTANCE.md](file:///d:/AlgoTrading/docs/GD15_1_ACCEPTANCE.md) for verification evidence.


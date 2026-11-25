# GD34 — RUNTIME HEALTH MONITORING & OBSERVABILITY

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Module:** `libs/bot/orchestration/health.py`  

---

## 1. Overview

`BotHealthMonitor` provides continuous runtime observability over all pipeline subsystems:
- Redpanda Data Consumer lag and feed staleness.
- Event loop queue depth and processing latency.
- Component-level health indicators.
- Ledger reconciliation status.

---

## 2. Key Monitored Indicators

| Metric | Threshold / Target | Action on Breach |
| :--- | :--- | :--- |
| **Heartbeat Age** | $< 30\text{s}$ | Status changes from `HEALTHY` to `DEGRADED`. |
| **Processing Latency** | $< 50\text{ms}$ per bar | Latency logged in performance journal. |
| **Queue Depth** | $< \text{max\_queue\_size}$ | Raises `QueueOverflowError` when capacity breached. |
| **Feed Freshness** | Age $\le 300\text{s}$ (5 minutes) | Sets `consumer_health = "STALE_FEED"`, issues warning. |
| **Reconciliation Status** | Must be `BALANCED` | If `DISCREPANCY_DETECTED`, logs error and flags session. |
| **Error Counter** | $0$ errors | Any unhandled exception increments counter and logs context. |

---

## 3. Feed Staleness Detection

In automated simulation and paper trading, market data gaps can cause models to make decisions on out-of-date information. `BotHealthMonitor.check_feed_staleness(max_age_seconds=300)` checks the elapsed time since the most recent processed bar:
$$\text{Feed Age} = t_{\text{now}} - t_{\text{last\_event\_processed}}$$

If $\text{Feed Age} > 300\text{s}$, the consumer is marked as `STALE_FEED`, prompting the orchestrator to log a warning and notify supervising services before new orders are submitted.

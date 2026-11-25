# GĐ36 — BACKTESTING ENGINE & HISTORICAL REPLAY ARCHITECTURE

**Project:** AlgoTrading V2.0  
**Phase:** GĐ36 — Backtesting Engine & Historical Replay Integration  
**Status:** ACCEPTED — 100% OPERATIONAL  
**Regression Status:** 393/393 Tests PASS (GĐ29–GĐ36)  
**Safety Status:** FAIL-CLOSED (`TRADING_MODE=DRY_RUN`, `PaperExecutionGate=CLOSED`, `environment=SIMULATION`)

---

## 1. Executive Summary

GĐ36 introduces a high-performance, deterministic historical backtesting engine for AlgoTrading V2.0. Rather than duplicating existing logic, GĐ36 reuses and coordinates the modular components delivered across GĐ29–GĐ35:

```
Historical Market Data (JSONL / Dataset Manifest)
       │
       ▼
Historical Dataset Manager (libs/bot/backtesting/dataset.py)
       │
       ▼
Virtual Replay Clock & Controller (libs/bot/backtesting/replay_clock.py, replay_controller.py)
       │
       ├── Warmup Phase (Strictly 0 Trades) ──► Strategy Engine (Indicators Warmup)
       │
       ▼ Tradable Phase (Event-Driven Next-Bar Matching)
┌─────────────────────────────────────────────────────────────┐
│ 1. Broker Fill Matching (SimulationBroker from GĐ33)        │
│ 2. Mark-to-Market Portfolio Valuation (PositionBook GĐ32)   │
│ 3. Strategy Signal Evaluation (StrategyExecutionEngine GĐ31)│
│ 4. Risk & Intent Generation (SignalDecisionEngine GĐ32)     │
│ 5. Broker Order Placement (SimulationBroker GĐ33)           │
│ 6. Equity Time Series & Journaling                          │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
Quantitative Metrics & Risk Calculator (libs/bot/backtesting/metrics.py)
       │
       ▼
Deterministic Fingerprint & Results (libs/bot/backtesting/results.py)
       │
       ▼
Isolated Storage (data/paper_bot/backtests/{run_id}/)
       │
       ▼
REST API & Dashboard (libs/bot/api/backtest_routes.py, BacktestPanel.tsx)
```

---

## 2. Core Architectural Principles

### 2.1 Reusable Engine Design
The backtest engine avoids writing separate simulation logic for trading. It runs the exact same:
- `StrategyExecutionEngine` and strategy instances (`MovingAverageCrossoverStrategy`, `RSIStrategy`)
- `SignalDecisionEngine` and `RiskConfig`
- `SimulationBroker`, `OrderLifecycleStateMachine`, `FillEngine`, and fee/slippage models
- `SimulationPortfolioManager` and `PositionBook`

This ensures **100% parity** between historical backtesting simulations and forward paper trading bots.

### 2.2 Strict Warmup Phase Isolation
In quantitative backtesting, indicators such as 20-period SMA, 50-period SMA, or 14-period RSI require historical data bars before they can produce meaningful values.
During the warmup phase:
- Bars are fed into the strategy engine to build indicator windows.
- **Strictly zero trading is permitted**: no signals are sent to the risk engine, no order intents are generated, and no fills are created.
- Insufficient bar history raises explicit errors when `warmup_policy="REQUIRED"`.

### 2.3 Virtual Event-Time vs Wall-Clock
The replay clock (`ReplayClock`) decouples simulation time from real-world system wall-clock time. Historical bars from 2020 or 2024 are evaluated with respect to the virtual replay clock, eliminating artificial staleness flags while preserving strict time-ordering.

### 2.4 Multi-Symbol Deterministic Tie-Breaker
When multiple symbols have bars at the same timestamp, execution order is resolved using a deterministic 3-tuple:
$$(t_{\text{event}}, \text{symbol.upper}(), \text{bar\_revision})$$
This prevents non-deterministic thread race conditions or dictionary ordering artifacts.

### 2.5 Complete Filesystem & Memory Segregation
- Backtest runs use isolated IDs: `bt_{uuid}`.
- Backtest portfolios use isolated IDs: `port_bt_{uuid}`.
- Output artifacts are saved exclusively to `data/paper_bot/backtests/{run_id}/`.
- No live Kafka consumer groups, offset commits, or Alpaca broker API calls are created.

# GĐ40 — AlgoTrading V2.0 Simulation Release Candidate Specification

## 1. Executive Summary & Release Identity

**AlgoTrading V2.0 Simulation Release Candidate 1 (`v2.0.0-rc1`)** marks the convergence and stabilization of the full algorithmic trading simulation stack engineered throughout GĐ29 through GĐ39.

| Metadata Attribute | Specification Value |
| :--- | :--- |
| **Product Version** | `v2.0.0-rc1` (Simulation Release Candidate) |
| **Git Commit Frozen** | `e4bc3d8b11266835b1b478124e4c97b9ffea4b79` |
| **Git Branch** | `main` |
| **Repository Path** | `D:\AlgoTrading` |
| **Target Milestone Date** | Saturday, 28/11/2026 |
| **Target Operating System** | Microsoft Windows 10/11 x64 / Windows Server 2022 |
| **Primary Trading Timeframe** | 1-minute (`1m`) OHLCV closed bars |
| **Execution Environment** | `SIMULATION` ONLY |
| **Trading Mode** | `DRY_RUN` (`dry_run=True`) |
| **Alpaca Paper Gate** | `CLOSED` (`is_gate_open=False`) |
| **Outbound Broker Write Calls** | Exactly 0 (No live/paper submit, replace, cancel) |
| **Regression Test Baseline** | **623 / 623 Tests Passing (100.0%)** |
| **Frontend Production Build** | Vite v6.2.6 + React 19 + TypeScript (0 errors, `dist/`) |
| **Release Candidate Verdict** | `CONDITIONALLY_READY_FOR_DEMO` |

> [!IMPORTANT]
> **Safety Boundary Notice**: GĐ40 is strictly a **Simulation Release Candidate**. It does NOT enable live trading, does NOT submit orders to Alpaca Paper accounts, and does NOT risk real capital. The final acceptance classification is `CONDITIONALLY_READY_FOR_DEMO` due to the pending 2-hour Level 2 Integration Soak inherited from GĐ39.

---

## 2. Release Candidate Bill of Materials & Inventory

The release candidate bundles all software components, library contracts, frontend dashboard assets, and test harnesses developed across GĐ29–GĐ39:

### 2.1 Backend Core Modules (`libs/bot/`)

```
libs/bot/
├── __init__.py
├── adapters.py                 # Adapters bridging domain models and V1 components
├── api/                        # FastAPI REST API endpoints & WebSocket hub (GĐ35, GĐ37, GĐ38)
├── backfill.py                 # Historical market data backfill & replay engine (GĐ30)
├── backtesting/                # Backtesting engine, runners, stores, metrics (GĐ36)
├── config.py                   # Central TradingConfig dataclass (DRY_RUN, SIMULATION)
├── consumer.py                 # Redpanda / Kafka streaming data consumer (GĐ30)
├── data_access.py              # Data access layer for live & historical bars
├── domain.py                   # Pure domain dataclasses & event schemas (GĐ29)
├── execution/                  # Fill engine, simulated broker, fee & slippage models (GĐ33)
├── experiments/                # Backtest experiment manager & comparison store (GĐ38)
├── indicators/                 # Technical indicators: SMA, EMA, RSI, MACD, ATR, Bollinger
├── intent_store.py             # Persistent order intent store with idempotency
├── interfaces.py               # Abstract Base Classes defining architectural boundaries
├── multibot/                   # Multi-Bot Supervisor, resource isolation, session store (GĐ37)
├── normalization.py            # Real-time tick & bar normalization engine (GĐ30)
├── observability.py            # Latency tracking, Prometheus metrics, structured logs
├── orchestration/              # Bot lifecycle controller, event loop, state machines (GĐ34)
├── portfolio/                  # Position book, portfolio manager, cash accounting (GĐ32)
├── portfolio_store.py          # Portfolio state persistence and snapshot store
├── quality.py                  # Real-time data quality & out-of-order filter
├── reliability/                # Queue overflow handlers, gap recovery, crash recovery (GĐ39)
├── revision.py                 # Bar revision and late-arriving event policies
├── risk/                       # Risk engine, 2% capital risk guards, drawdown limits (GĐ32)
├── signal_store.py             # Signal audit log and persistence store
├── signal_validator.py         # Signal sanity check and deduplication validator
├── storage.py                  # Low-level SQLite and JSON persistence layer
├── strategies/                 # Strategy implementations (MA Crossover, RSI, Mean Reversion)
├── strategy_comparison.py      # Multi-run comparison and correlation metrics (GĐ38)
├── strategy_config/            # Configuration schemas, versioning, SHA-256 presets (GĐ38)
├── strategy_engine.py          # Signal decision engine & strategy orchestrator (GĐ31)
└── strategy_registry.py        # Strategy discovery and dynamic registration registry
```

### 2.2 Dashboard Frontend (`trading-dashboard/frontend/`)

- **Framework**: React 19, TypeScript 5.8, Vite 6.2.6, TailwindCSS, Lucide-React.
- **Production Bundle**: `trading-dashboard/frontend/dist/` (Verified cleanly built).
- **Core Tabs**:
  1. **Bot Management**: Single-bot creation, status inspection, parameters, start/pause/resume/stop lifecycle controls.
  2. **Multi-Bot Overview**: Aggregate multi-bot dashboard, aggregate portfolio summary, system-wide resource monitoring.
  3. **Strategy Configuration**: Schema-driven strategy parameters, versioned presets, immutable JSON configuration editor.
  4. **Portfolio & Positions**: Real-time cash, equity, cost basis, unrealized P&L, position inventory.
  5. **Orders & Fills**: Complete audit trail of generated order intents, simulated orders, and simulated fills.
  6. **Backtesting Workbench**: Historical dataset selection, parameter sweeps, backtest execution, interactive equity curves.
  7. **Strategy Experiments**: Experiment manager, batch execution logs, reproducibility fingerprints.
  8. **Backtest Comparison**: Side-by-side run comparison, Sharpe ratio, Sortino ratio, max drawdown diff table.
  9. **Runtime Health & Observability**: Latency telemetry, event-loop throughput, queue depths, crash recovery state.

---

## 3. Scope Boundaries & Non-Goals

1. **NO Live Trading**: Under no circumstances does this release communicate with `https://api.alpaca.markets`.
2. **NO Alpaca Paper Order Submissions**: The `AlpacaPaperGate` is firmly CLOSED (`is_gate_open=False`). Outbound write calls (`submit_paper_order`, `replace_paper_order`, `cancel_paper_order`) will raise `PaperExecutionGateClosedError`.
3. **NO V1 Modifications**: Legacy Flink streaming pipelines, existing Kafka topics, and V1 database schemas remain unmodified and isolated.
4. **NO Virtual vs Real Capital Mixing**: All portfolio cash balances ($100k, $150k, etc.) are strictly simulated within SQLite/Memory `PositionBook` structures.

---

## 4. Verification Baseline Summary

| Verification Category | Status | Verified Evidence |
| :--- | :---: | :--- |
| **Comprehensive Regression** | **PASS** | 623 / 623 tests pass across 11 test suites in 12.365s |
| **Frontend Production Build** | **PASS** | `tsc -b && vite build` completed in 430ms with 0 errors |
| **Deterministic Roundtrip (BUY -> SELL)** | **PASS** | $0.0000 cash discrepancy, reconciled balance confirmed |
| **Multi-Bot Sandbox Isolation** | **PASS** | 3 independent bots, pause/resume isolation, 0 state crosstalk |
| **Backtest Replay & Comparison** | **PASS** | Deterministic 64-char fingerprint generated, side-by-side comparison verified |
| **Windows Startup & API Serving** | **PASS** | FastAPI endpoints respond 200 OK, startup scripts validated |
| **GĐ39 Harness Smoke (30s)** | **PASS** | 30.07s wall-clock, 3 bots, 149 events, 0 error |
| **GĐ39 Level 1 Smoke Soak (10m)** | **PASS** | 600.24s wall-clock, 3 bots, 3000 events, 0 error |
| **GĐ39 Level 2 Integration Soak (2h)** | **PENDING** | 7200s soak required before Live/Alpaca Paper Release |

---

## 5. Master Verdict

```
FINAL VERDICT: CONDITIONALLY_READY_FOR_DEMO
```

The system is verified robust, mathematically reconciled, and architecturally complete for the scheduled Saturday 28/11/2026 simulation demonstration.

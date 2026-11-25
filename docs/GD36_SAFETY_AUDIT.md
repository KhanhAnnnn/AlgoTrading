# GĐ36 — SAFETY INVARIANTS & ISOLATION AUDIT

**Target:** AlgoTrading V2.0 Simulation Sandbox  
**Audit Date:** 2026-11-24  
**Audit Result:** 100% COMPLIANT — ZERO SAFETY BREACHES

---

## 1. Safety Invariants Summary

| Safety Invariant | Required State | Actual State | Audit Method |
| :--- | :--- | :--- | :--- |
| `TRADING_MODE` | `DRY_RUN` | `DRY_RUN` | Environment & Config Assertions |
| `PaperExecutionGate.is_gate_open` | `False` | `False` | Code inspection & API fail-closed check |
| `Alpaca Broker API Writes` | Zero calls | Zero calls | Method interceptor & fail-closed barrier |
| `Environment Isolation` | `SIMULATION` | `SIMULATION` | Strict event & config environment tags |
| `Broker Routing` | `SimulationBroker` | `SimulationBroker` | Isolated in-memory execution ledger |
| `Kafka Consumer Offset Impact` | Zero mutations | Zero mutations | Datasets loaded from memory / JSONL |

---

## 2. Fail-Closed Barrier Verification

The `libs/alpaca_paper_gate.py` barrier enforces:
```python
if self.is_gate_open is not True:
    raise PaperExecutionGateClosedError(
        "CRITICAL SAFETY GUARD: Alpaca Paper Execution Gate is LOCKED (fail-closed)."
    )
```

In `tests/test_gd36_backtesting.py`:
- `TC 40` verifies that attempting to initialize `BacktestRunner` with an open gate raises `LiveTradingProhibitedError`.
- `TC 64` verifies that attempting to call `paper_gate.submit_paper_order(...)` directly fails with `PaperExecutionGateClosedError`.

---

## 3. Storage and Process Isolation

- **Directory Segregation:** All backtest data is persisted to `data/paper_bot/backtests/{run_id}/`, isolated from live paper bot sessions in `data/paper_bot/sessions/`.
- **Portfolios:** Backtest portfolios are initialized with distinct IDs (`port_bt_{uuid}`) and have zero interaction with live accounts or workbench state.
- **Offsets:** Historical replay uses the `ReplayClock` and dataset managers; natural Kafka consumer offsets remain untouched.

# GD34 — PAUSE, RESUME, AND STOP SEMANTICS

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Modules:** `libs/bot/orchestration/orchestrator.py`, `libs/bot/orchestration/stop_policy.py`  

---

## 1. Pause Semantics

When operator or automated supervisor triggers `pause()`:
1. **Lifecycle Transition:** Transitions session from `RUNNING` to `PAUSED`.
2. **Event Loop Suspension:** Sets `event_loop.is_paused = True`. Any incoming market data bars submitted via `submit_bar` are ignored and rejected.
3. **Working Order Protection:** Working and partially-filled simulation orders in `SimulationBroker` remain in `WORKING` status. They are **not** cancelled.
4. **State Persistence:** Triggers an atomic checkpoint (`save_checkpoint()`) and writes the updated session to disk.

---

## 2. Resume Semantics

When operator triggers `resume()`:
1. **Lifecycle Transition:** Transitions session from `PAUSED` back to `RUNNING`.
2. **Event Loop Reactivation:** Sets `event_loop.is_paused = False`.
3. **Seamless Resumption:** The bot immediately resumes consuming and evaluating new finalized 1-minute bars without state loss or duplicate fills.

---

## 3. Stop Policies & Graceful Shutdown

When `stop(policy)` is called, the orchestrator executes a multi-stage graceful shutdown:

$$\text{RUNNING / PAUSED} \longrightarrow \text{STOPPING} \longrightarrow \text{Apply Stop Policy} \longrightarrow \text{Reconcile} \longrightarrow \text{Final Checkpoint} \longrightarrow \text{STOPPED}$$

### Supported Stop Policies (`StopPolicy`):

1. **`CANCEL_REMAINDER` (Default, Recommended):**
   - Iterates through all open simulation orders in `WORKING` or `PARTIALLY_FILLED` status.
   - Issues a simulation cancellation (`cancel_order`) for each order with reason `"BOT_SHUTDOWN"`.
   - **Cash Reservation Release:** The `PortfolioExecutionAdapter` automatically releases reserved buying power cash, returning uncommitted funds back to `portfolio.available_cash`.
2. **`KEEP_WORKING`:**
   - Leaves active working simulation orders untouched in the broker.
   - Useful for specialized multi-session handovers or manual inspection scenarios.

---

## 4. Final Verification & Terminal State

Before the final transition to `STOPPED` occurs:
1. **Reconciliation Audit:** `simulation_broker.reconcile()` verifies that $\Delta \text{Cash} + \Delta \text{Positions} = \text{Ledger Total}$. Discrepancies are logged in health monitor.
2. **Performance Reporting:** Final session performance metrics are compiled and persisted to `data/paper_bot/performance/perf_<session_id>.json`.
3. **State Lock:** The session enters terminal `STOPPED` state, guaranteeing that no further events can be processed under this session ID.

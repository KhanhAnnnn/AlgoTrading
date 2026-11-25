# GD33 — RECOVERY & IDEMPOTENCY SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ33 — Order Management & Simulation Broker Engine  
**Modules:** `libs/bot/execution/order_store.py`, `libs/bot/execution/fill_store.py`  
**Storage Paths:** `data/paper_bot/orders/`, `data/paper_bot/fills/`  

---

## 1. Multi-Tier Idempotency Architecture

The execution pipeline enforces idempotency at every stage:

| Stage | Deduplication Key | Mechanism | Duplicate Action |
| :--- | :--- | :--- | :--- |
| **Intent Admission** | `idempotency_key` | `SimulationOrderManager._seen_idempotency_keys` | Rejected with `DUPLICATE_INTENT_IDEMPOTENCY_KEY` |
| **Intent Re-consumption**| `intent_id` | `SimulationOrderManager._orders_by_intent` | Rejected with `INTENT_ALREADY_CONSUMED` |
| **Order Fill Duplicate** | `simulated_fill_id` | `PortfolioExecutionAdapter._applied_fill_ids` | Skipped without altering portfolio cash/positions |
| **Order Transition** | `order_id` + `status` | `OrderLifecycleStateMachine` | Rejects transitions from terminal states |

---

## 2. Crash Recovery & Restart Sequence

In the event of process termination, restart recovery proceeds as follows:

1. **Index Rehydration:**
   - `OrderStore` parses `orders_log.jsonl` to re-index all previously generated order IDs and idempotency keys.
   - `FillStore` parses `fills_log.jsonl` to re-index all generated fill IDs.
2. **Order Book Recovery:**
   - Active orders (`WORKING`, `PARTIALLY_FILLED`) are reloaded from disk into memory.
3. **Portfolio Reconciliation:**
   - `ExecutionLedger.reconcile()` audits existing orders and fills against persistent portfolio snapshots, detecting and reporting any incomplete transactions without blind double-booking.

# GD34 — 1-MINUTE EVENT LOOP & PIPELINE

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Module:** `libs/bot/orchestration/event_loop.py`  

---

## 1. Single-Writer Event-Driven Pipeline

`BotEventLoop` implements a strictly sequential event-driven processor designed specifically for 1-minute market bars (`1m`). To completely eliminate race conditions and data corruption, only a single writer processes events from the bounded FIFO queue.

### Sequential Processing Order per 1m Bar:

$$\text{Incoming Bar } B_t \longrightarrow \text{[Step 1: Match Orders]} \longrightarrow \text{[Step 2: Evaluate Strategy]} \longrightarrow \text{[Step 3: Risk Check]} \longrightarrow \text{[Step 4: Place Orders]} \longrightarrow \text{[Step 5: Journal Commit]}$$

1. **Step 1 — Broker Fill Matching:**  
   Orders placed during bar $B_{t-1}$ (or earlier) are matched against bar $B_t$ (e.g., using $B_t$'s Open price for Market orders). This strictly simulates real-world execution delay.
2. **Step 2 — Strategy Evaluation:**  
   Strategy indicators are updated using closed bar $B_t$, and new analytical signals (`StrategySignal`) are emitted.
3. **Step 3 — Risk & Portfolio Evaluation:**  
   The `SignalDecisionEngine` evaluates the signal against current cash, positions, and risk boundaries, producing a `SignalDecision`.
4. **Step 4 — Order Intent Submission:**  
   If accepted, a `SimulationOrderIntent` is created and submitted to `SimulationBroker`, which registers an order in `WORKING` state for execution on future bars ($B_{t+1}$ onwards).
5. **Step 5 — Journal Commit & Telemetry:**  
   The bar key and event ID are committed to `BotEventJournal`, and processing latency is logged in `BotHealthMonitor`.

---

## 2. Anti-Lookahead Bias Guarantees

In financial algorithmic trading simulation, **look-ahead bias** occurs when an order is executed on the same bar that triggered the signal, or when future prices leak into current calculations.

GĐ34 enforces zero look-ahead bias through two mechanisms:
1. **Separation of Matching and Evaluation:** Fill matching always occurs before strategy evaluation. Signals generated on bar $B_t$ can NEVER match or fill on bar $B_t$.
2. **Source Bar Isolation:** Every `SimulatedOrder` stores `source_bar_key`. The `FillEngine` explicitly asserts:
   $$\text{order.source\_bar\_key} \ne \text{current\_bar.bar\_key}$$
   Any matching attempt on the source bar is rejected with zero fills.

---

## 3. Backpressure & Bounded Queue

1. **Queue Capacity Limit:** The internal deque is configured with `max_queue_size` (default: 1,000 events).
2. **Fail-Closed Overflow:** If market data arrives faster than the event loop can process and the queue reaches capacity, `enqueue_event` logs a critical alert and raises `QueueOverflowError`.
3. **Provisional Rejection:** Bars with `is_final=False` are rejected immediately from the queue.

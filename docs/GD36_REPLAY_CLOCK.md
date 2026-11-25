# GĐ36 — VIRTUAL REPLAY CLOCK & PROGRESSION CONTROL

**Modules:** `libs/bot/backtesting/replay_clock.py`, `libs/bot/backtesting/replay_controller.py`  
**Purpose:** Virtual event-time simulation clock and historical replay flow controllers.

---

## 1. Virtual Replay Clock (`ReplayClock`)

The virtual replay clock completely eliminates dependencies on real-world host wall-clock time during historical simulation.

### 1.1 Invariants
1. **Monotonic Non-Decreasing:** The clock can only advance forward in time:
   $$t_{k+1} \ge t_k$$
   Attempting to call `advance_to(t)` with $t < t_k$ immediately raises `ValueError`.
2. **Decoupled Staleness:** An event's age is calculated relative to the virtual replay time:
   $$\text{Age}_{\text{virtual}} = t_{\text{clock}} - t_{\text{bar}}$$
   If $\text{Age}_{\text{virtual}} \le \text{max\_staleness}$, the bar is considered fresh, regardless of how many years in the past the data originated.
3. **Deterministic Tie-Breaking:** When multiple symbols share identical timestamps, ordering is resolved via:
   $$\text{Key} = (t_{\text{event}}, \text{symbol.upper}(), \text{bar\_revision})$$

---

## 2. Replay Controller (`ReplayController`)

The `ReplayController` coordinates playback modes:

| Replay Mode | Description | Typical Use Case |
| :--- | :--- | :--- |
| `FAST_REPLAY` | Zero sleep delay between bars; maximum computational throughput | Batch backtesting, hyperparameter sweeps |
| `PACED_REPLAY` | Introduces a configurable `pace_delay_seconds` between bars | Live dashboard visual demonstrations |
| `STEP_REPLAY` | Processes exactly 1 bar per `step()` invocation | Interactive debugging, unit testing |

### 2.1 Lifecycle State Transitions

```
               ┌──────────┐
               │INITIALIZED│
               └────┬─────┘
                    │ run() / step()
                    ▼
               ┌──────────┐
         ┌────►│ RUNNING  │◄────┐
 pause() │     └────┬─────┘     │ resume()
         │          │           │
         ▼          │           │
    ┌────────┐      │      ┌────────┐
    │ PAUSED │──────┴─────►│ PAUSED │
    └────────┘             └────────┘
         │ cancel()
         ▼
    ┌──────────┐
    │CANCELLED │
    └──────────┘
         ▲
         │ (all bars processed)
    ┌──────────┐
    │COMPLETED │
    └──────────┘
```

### 2.2 Progress Tracking & Callbacks
`ReplayController` invokes optional progress hooks:
- `on_bar_callback(bar, clock)`: Dispatched as each bar is processed.
- `on_progress_callback(processed_count, total_count, current_virtual_time)`: Informs dashboards of completion percentage.

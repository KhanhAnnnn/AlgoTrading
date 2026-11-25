# GD34 — BOT LIFECYCLE & STATE MACHINE

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Module:** `libs/bot/orchestration/lifecycle.py`  

---

## 1. Lifecycle State Machine Definition

The Bot Lifecycle State Machine defines all operational phases of a paper bot session. Every state transition is validated against a deterministic transition matrix; invalid transitions raise `InvalidLifecycleStateTransitionError` and fail closed.

```
                  +--------------+
                  |   STOPPED    | (Initial dormant state)
                  +-------+------+
                          | start()
                          v
                  +--------------+
                  |   STARTING   |
                  +-------+------+
                          | services ready
                          v
          +-------------> +--------------+ <------------+
          |               |   RUNNING    |              |
          |               +-------+------+              |
          | resume()              | pause()             | resume()
          |                       v                     |
          |               +--------------+              |
          +---------------+    PAUSED    +--------------+
                          +-------+------+
                                  | stop()
                                  v
+-------------------------------+ +--------------+
|             ERROR             | |   STOPPING   |
| (Terminal failure diagnosis)  | +-------+------+
+-------------------------------+         | cleanup complete
                                          v
                                  +--------------+
                                  |   STOPPED    | (Terminal finished state)
                                  +--------------+
```

---

## 2. Transition Rules Matrix

| From State | Allowed Target States | Disallowed Target States | Triggers / Notes |
| :--- | :--- | :--- | :--- |
| **STOPPED (Initial)** | `STARTING` | `RUNNING`, `PAUSED`, `STOPPING`, `ERROR` | `start()` initializes subsystems before entering `RUNNING`. |
| **STARTING** | `RUNNING`, `STOPPING`, `ERROR` | `PAUSED`, `STOPPED` | Transitioned when subsystems, stores, and queues are wired. |
| **RUNNING** | `PAUSED`, `STOPPING`, `ERROR` | `STARTING`, `STOPPED` | Active processing state. |
| **PAUSED** | `RUNNING`, `STOPPING`, `ERROR` | `STARTING`, `STOPPED` | Suspends event processing; working orders remain intact. |
| **STOPPING** | `STOPPED`, `ERROR` | `STARTING`, `RUNNING`, `PAUSED` | Flushes state, cancels remainder orders, reconciles ledger. |
| **ERROR** | `STOPPING`, `STOPPED` | `STARTING`, `RUNNING`, `PAUSED` | Failure context preserved (`error_code`, `error_message`). |
| **STOPPED (Final)** | None (Terminal) | All states | Terminal finished state. |

---

## 3. Idempotency & Audit Invariants

1. **Idempotency:** Requesting a transition from state $S$ to state $S$ is recognized as an idempotent no-op and returns a `BotAuditEvent` without side effects or errors.
2. **Deterministic Audit:** Every state change emits a structured `BotAuditEvent` recording session ID, timestamp, prior state, new state, reason, and error context.
3. **Safety Guarantee:** State transitions never bypass safety boundaries; in case of unhandled runtime exceptions, the orchestrator transitions to `ERROR` and locks down processing.

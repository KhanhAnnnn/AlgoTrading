# GD35 — API Architecture & Integration Specification

**Stage:** GĐ35 — API & Dashboard Integration  
**Repository:** `D:\AlgoTrading`  
**Target:** AlgoTrading V2.0  
**Environment:** `SIMULATION`  
**Trading Mode:** `DRY_RUN`  
**PaperExecutionGate:** `is_gate_open = False`  

---

## 1. Executive Summary

GĐ35 establishes the unified REST and WebSocket API gateway connecting the AlgoTrading V2.0 Paper Trading Bot subsystem with client applications, specifically the React-based live trading terminal (`trading-dashboard/frontend`).

The architecture strictly decouples simulation controls from real market execution, enforces simulation sandboxing invariants, ensures complete idempotency for lifecycle commands, and exposes high-throughput, low-latency telemetry without degrading the performance of the event loop.

---

## 2. Architecture & Service Topology

```
+--------------------------------------------------------------------------------+
|                           React Terminal Dashboard                             |
|         [TopBar: Bot Selector]  [PaperBotPanel: Stats / Chart / Tables]        |
+--------------------------------------------------------------------------------+
             | REST (HTTP/1.1)                           ^ WebSocket (JSON / WSS)
             v                                           |
+--------------------------------------------------------------------------------+
|                         FastAPI Application Gateway                            |
|                     (trading-dashboard/backend/main.py)                        |
|                                                                                |
|  [/api/v2/bots] Routes            |            [/ws/v2/bots] WebSocket Hub     |
|  - POST /api/v2/bots (Create)     |            - /ws/v2/bots/{session_id}      |
|  - GET  /api/v2/bots (List)       |            - /ws/v2/bots (Global Stream)   |
|  - POST /{id}/start, pause, stop  |            - Sequence IDs & Deduplication  |
|  - GET  /{id}/portfolio, orders   |            - Replay Buffer & Resync        |
+--------------------------------------------------------------------------------+
             |                                           ^
             v                                           | Events / Snapshots
+--------------------------------------------------------------------------------+
|                          libs.bot.api Application Layer                        |
|                                                                                |
|  +---------------------------+        +-------------------------------------+  |
|  |       BotApiService       |------->|         BotWebSocketManager         |  |
|  +---------------------------+        +-------------------------------------+  |
|               |                                                                |
|               v                                                                |
|  +---------------------------+        +-------------------------------------+  |
|  |     BotCommandService     |------->|           SessionStore              |  |
|  +---------------------------+        +-------------------------------------+  |
+--------------------------------------------------------------------------------+
             |
             v
+--------------------------------------------------------------------------------+
|                       libs.bot.orchestration Core Engines                      |
|                                                                                |
|  [BotOrchestrator] <---> [BotLifecycleStateMachine] <---> [BotEventLoop]      |
|         |                                                        |             |
|         +------------------> [SimulationBroker]                  |             |
|         |                            |                           v             |
|         +--> [SimulationPortfolio]   +--> [FillEngine]    [PaperBotConsumer]   |
+--------------------------------------------------------------------------------+
```

---

## 3. REST Endpoint Specifications

All endpoints are mounted under `/api/v2/bots`:

| Method | Endpoint | Description | Status Code | Error Codes |
|---|---|---|---|---|
| `GET` | `/api/v2/bots` | List all active and persisted bot sessions | `200 OK` | `401 Unauthorized` |
| `POST` | `/api/v2/bots` | Create a new isolated bot session | `201 Created` | `400 Bad Request`, `422 Unprocessable` |
| `GET` | `/api/v2/bots/{session_id}` | Retrieve comprehensive bot status and summary | `200 OK` | `404 Not Found` |
| `POST` | `/api/v2/bots/{session_id}/start` | Start bot and activate event loop | `200 OK` | `404 Not Found`, `409 Conflict` |
| `POST` | `/api/v2/bots/{session_id}/pause` | Pause event loop (preserve working orders) | `200 OK` | `404 Not Found`, `409 Conflict` |
| `POST` | `/api/v2/bots/{session_id}/resume` | Resume event loop from paused state | `200 OK` | `404 Not Found`, `409 Conflict` |
| `POST` | `/api/v2/bots/{session_id}/stop` | Gracefully shut down bot session | `200 OK` | `404 Not Found` |
| `GET` | `/api/v2/bots/{session_id}/portfolio` | Real-time cash, equity, and positions | `200 OK` | `404 Not Found` |
| `GET` | `/api/v2/bots/{session_id}/orders` | Retrieve simulated orders (with filtering) | `200 OK` | `404 Not Found` |
| `GET` | `/api/v2/bots/{session_id}/fills` | Retrieve execution fills (with pagination) | `200 OK` | `404 Not Found` |
| `GET` | `/api/v2/bots/{session_id}/performance`| Quantitative metrics, drawdown, funnel | `200 OK` | `404 Not Found` |
| `GET` | `/api/v2/bots/{session_id}/health` | Heartbeat, queue depth, feed staleness | `200 OK` | `404 Not Found` |
| `POST` | `/api/v2/bots/{session_id}/bars` | Submit 1m bar directly into event loop | `200 OK` | `400 Bad Request`, `404 Not Found` |

---

## 4. Idempotency & Lifecycle Transition Matrix

All lifecycle control commands implement strict idempotent semantics:
- Calling `start` on a bot already in `RUNNING` returns `200 OK` without error.
- Calling `pause` on a bot already in `PAUSED` returns `200 OK` without error.
- Calling `resume` on a bot already in `RUNNING` returns `200 OK` without error.
- Calling `stop` on a bot already in `STOPPED` returns `200 OK` without error.
- Invalid state transitions (e.g. attempting to `pause` a `STOPPED` bot) reject with `409 Conflict`.
- State machines strictly enforce valid transitions:
  $$\text{STOPPED} \xrightarrow{\text{start}} \text{STARTING} \rightarrow \text{RUNNING}$$
  $$\text{RUNNING} \xrightarrow{\text{pause}} \text{PAUSED} \xrightarrow{\text{resume}} \text{RUNNING}$$
  $$\text{RUNNING} / \text{PAUSED} \xrightarrow{\text{stop}} \text{STOPPING} \rightarrow \text{STOPPED}$$

---

## 5. Safety Invariants & Simulation Isolation

1. **Trading Mode Guarantee**: Every API response embeds `"trading_mode": "DRY_RUN"`.
2. **Environment Tagging**: Every resource embeds `"environment": "SIMULATION"`.
3. **Execution Gate Enforcement**: `PaperExecutionGate.is_gate_open` is immutably `False`.
4. **Zero Broker API Surface**: No endpoints exist for Alpaca live broker order submissions, replacements, or cancellations.

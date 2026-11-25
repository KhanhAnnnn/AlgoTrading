# GD34 — BOT ORCHESTRATION ARCHITECTURE

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Paper Trading Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Environment:** `SIMULATION`  
**Trading Mode:** `DRY_RUN`  
**Gate Status:** CLOSED (`is_gate_open = False`)  

---

## 1. Architectural Overview

GĐ34 delivers the centralized master coordinator (`BotOrchestrator`) for AlgoTrading V2.0. It integrates and harmonizes all previously accepted components from GĐ30 through GĐ33 into an event-driven, look-ahead-free paper trading system.

```
       +---------------------------------------------------------+
       |                  Redpanda 1m Market Bars                |
       |                (GĐ30: PaperBotConsumer)                 |
       +----------------------------+----------------------------+
                                    | 1m MarketDataEvent
                                    v
       +---------------------------------------------------------+
       |                  BotEventLoop (GĐ34)                    |
       |  - Bounded FIFO Queue (Backpressure protection)         |
       |  - Event Deduplication Journal (BotEventJournal)        |
       +----------------------------+----------------------------+
                                    | Sequential Dispatch
         [Step 1: Match Prior Orders] [Step 2: Strategy Evaluation]
                                    |                     |
                                    v                     v
       +----------------------------+--+   +--------------+--------------+
       |    SimulationBroker (GĐ33)    |   | StrategyExecutionEngine(GĐ31|
       |  - Match active orders on bar |   |  - Calculate indicators     |
       |  - Generate SimulatedFill     |   |  - Generate StrategySignal  |
       +----------------------------+--+   +--------------+--------------+
                                    |                     |
                                    |                     v
                                    |      +--------------+--------------+
                                    |      | SignalDecisionEngine (GĐ32) |
                                    |      |  - Portfolio limits check   |
                                    |      |  - Position sizing          |
                                    |      |  - Emit SimulationOrderIntent
                                    |      +--------------+--------------+
                                    |                     |
                                    +<--------------------+
                                    | Submit Intent
                                    v
       +---------------------------------------------------------+
       |     SimulationBroker & Portfolio Adapter (GĐ32/GĐ33)    |
       |  - Reserve cash for BUY intents                         |
       |  - Place order into WORKING state for FUTURE bars       |
       |  - Maintain balanced execution ledger                   |
       +---------------------------------------------------------+
```

---

## 2. Integrated Subsystems

1. **Data Layer Integration (GĐ30):**
   - Consumes normalized 1-minute OHLCV bars (`MarketDataEvent`).
   - Consumer group pinned to `paper-bot-v2-group`.
   - Quality checks: finality (`is_final=True`), revision integrity, and provenance tracking.

2. **Python Strategy Engine Integration (GĐ31):**
   - Event-driven bar evaluation via `StrategyExecutionEngine`.
   - Strategy contracts strictly decoupled from order routing or portfolio access.
   - Emits standardized `StrategySignal` (`BUY`, `SELL`, `HOLD`).

3. **Portfolio & Risk Management Integration (GĐ32):**
   - Managed via `SimulationPortfolioManager` and `SignalDecisionEngine`.
   - Continuous verification of maximum position notional, drawdown limit, and exposure ceilings.
   - Converts actionable signals to `SimulationOrderIntent`.

4. **Order Management & Simulation Broker Integration (GĐ33):**
   - Managed via `SimulationBroker` and `SimulationOrderManager`.
   - High-fidelity matching engine supporting market, limit, stop, and trailing orders.
   - Slippage models, fee models, volume participation caps, and execution ledger.

5. **Lifecycle, Checkpoint & Recovery Engine (GĐ34):**
   - Enforces deterministic state transitions (`STARTING` $\rightarrow$ `RUNNING` $\longleftrightarrow$ `PAUSED` $\rightarrow$ `STOPPING` $\rightarrow$ `STOPPED`).
   - Periodic and state-driven checkpoints with SHA-256 integrity checksums.
   - Atomic session store and crash recovery with configuration hash validation.
   - Real-time health monitoring and comprehensive performance reporting.

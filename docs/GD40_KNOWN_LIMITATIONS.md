# GĐ40 — Known Technical Limitations & Operational Scope

## 1. Scope & Release Candidate Context

AlgoTrading V2.0 Simulation Release Candidate 1 (`v2.0.0-rc1`) is engineered and validated specifically for institutional research, multi-strategy simulation, and deterministic backtesting.

This document transparently records the known engineering boundaries, intentional non-goals, and technical limitations of the current release.

---

## 2. Technical Limitations & Operational Boundaries

### 2.1 Level 2 Integration Soak Pending
- **Current State**: The system has completed and passed the 30.07-second Harness Smoke and the 600.24-second (10-minute) Level 1 Smoke Soak with 3,000 events and 0 errors.
- **Limitation**: The 2-hour (7,200-second) Level 2 continuous integration soak remains pending.
- **Operational Impact**: The system is strictly rated `CONDITIONALLY_READY_FOR_DEMO`. A full 2-hour wall-clock soak must be performed before the system can be considered for Alpaca Paper order execution or production release.

### 2.2 Timeframe Optimization & Order Book Granularity
- **Current State**: The architecture is optimized around 1-minute (`1m`) OHLCV closed bars.
- **Limitation**: Sub-minute tick-level execution, Level 2 / Level 3 market depth (DOM), and microscopic queue priority within exchange matching engines are not simulated.
- **Operational Impact**: Fills are executed at the Open price of the subsequent 1-minute bar plus or minus modeled slippage and fee adjustments.

### 2.3 Simulated Fill Models vs Live Market Impact
- **Current State**: The execution simulator employs `FixedBpsSlippageModel` (default: 5 bps) and `ConfigurableFeeModel` (default: \$1.50 flat commission + volume bps).
- **Limitation**: The simulator does not model adverse market impact (e.g., an oversized institutional order walking the order book and moving the market price against itself).
- **Operational Impact**: Highly accurate for retail and small-to-mid quant order sizes; large notional orders should use appropriate percentage-of-volume constraints in strategy configurations.

### 2.4 Alpaca Paper Execution Gate is Closed
- **Current State**: `PaperExecutionGate.is_gate_open` is permanently locked to `False`.
- **Limitation**: Outbound network requests to Alpaca's paper trading API (`submit_paper_order`, `replace_paper_order`, `cancel_paper_order`) are disabled and raise `PaperExecutionGateClosedError`.
- **Operational Impact**: All trades, positions, and cash balances remain strictly virtual inside local SQLite databases and memory models. Real-world brokerage synchronization is a future milestone.

### 2.5 Single-Node Process Architecture
- **Current State**: The `MultiBotSupervisor` orchestrates concurrent bots within a single Python process using non-blocking asynchronous event loops and worker threads.
- **Limitation**: Distributed multi-node clustering (e.g., Kubernetes pod fan-out, Celery/Ray distributed backtesting) is not implemented in V2.0.
- **Operational Impact**: The system easily supports dozens of concurrent simulation bots on modern multi-core workstations, but is bounded by the CPU and RAM of the host machine.

### 2.6 Windows Process Management
- **Current State**: Startup is handled via PowerShell scripts (`run-dashboard.ps1`) or manual Uvicorn/Vite CLI invocations.
- **Limitation**: Native Windows Services (via NSSM or Windows Service Control Manager) are not installed by default.
- **Operational Impact**: If the terminal window running Uvicorn is closed, the backend process terminates. Operators should run background terminals or use screen/tmux equivalents if long-running execution is required.

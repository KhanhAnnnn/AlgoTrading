# GD35 — Frontend Dashboard Integration Specification

**Stage:** GĐ35 — API & Dashboard Integration  
**Repository:** `D:\AlgoTrading`  
**Frontend Path:** `trading-dashboard/frontend`  
**Primary Framework:** React 18, TypeScript, Tailwind CSS, Lucide Icons  

---

## 1. Component Architecture

The V2 Paper Trading Bot Dashboard is encapsulated in `PaperBotPanel.tsx` and integrated seamlessly into the existing AlgoTrading terminal interface via `App.tsx` and `TopBar.tsx`.

```
App.tsx
 ├── TopBar.tsx (Navigation & Tab Switcher: Terminal | Analytics | Portfolio | V2 Paper Bot | ...)
 └── PaperBotPanel.tsx (activeTab === 'paper_bot')
      ├── Bot Header Bar (Bot selector dropdown, Status Pill, Start/Pause/Stop controls, New Bot button)
      ├── Metric Overview Cards (Equity, Cash, Unrealized PnL, Win Rate, Latency, Queue Depth)
      ├── Tab Views:
      │    ├── Overview (Performance funnel, Realized/Unrealized PnL, Drawdown)
      │    ├── Portfolio (Cash balances, Active Positions table, Realized PnL)
      │    ├── Orders & Fills (Working/Filled orders table, Simulated execution fills)
      │    ├── Strategy & Risk (Indicator configuration, Risk limits, Hashing)
      │    └── Health & Logs (Subsystem health, Latency metrics, Real-time event log)
      └── Create Bot Modal (Configurable Bot ID, Strategy, Initial Virtual Cash, Risk Parameters)
```

---

## 2. Integrated Components & Features

### A. Navigation & Tab Switcher (`TopBar.tsx`)
- Added `'paper_bot'` tab with `Bot` icon from `lucide-react`.
- Smooth state transition between V1 Terminal, Portfolio, Workbench, and V2 Paper Trading Bot.

### B. Bot Control & State Machine (`PaperBotPanel.tsx`)
- **Start Bot**: Dispatches `POST /api/v2/bots/{session_id}/start`.
- **Pause Bot**: Dispatches `POST /api/v2/bots/{session_id}/pause`.
- **Resume Bot**: Dispatches `POST /api/v2/bots/{session_id}/resume`.
- **Stop Bot**: Dispatches `POST /api/v2/bots/{session_id}/stop` with policy `CANCEL_REMAINDER`.
- Immediate optimistic UI update confirmed by WebSocket lifecycle stream.

### C. Live Real-Time Telemetry via WebSocket
- Connects automatically to `ws://127.0.0.1:8005/ws/v2/bots/{session_id}`.
- Listens for `SNAPSHOT`, `BOT_LIFECYCLE_EVENT`, `STRATEGY_SIGNAL_EVENT`, `RISK_DECISION_EVENT`, `FILL_EVENT`, and `PORTFOLIO_UPDATE`.
- Automatically tracks `seq_id` and implements 10-second PING/PONG heartbeats.
- Visual connection status indicator (Connected / Disconnected).

### D. Safe Interactive Creation Modal
- Form with validation for bot ID, strategy ID (`MA_CROSS_1M`, `RSI_1M`, `V1_FLINK_ADAPTER`), initial capital, and risk parameters.
- Rejects non-simulation parameters.

---

## 3. UI Invariants & Guardrails

1. **Explicit Visual Badging**: The panel prominently displays a `SIMULATION / DRY_RUN` badge in yellow/amber at the top right of the viewport.
2. **Read-Only Safety**: The panel contains zero interfaces or inputs to configure live broker credentials or execute live orders.
3. **Decoupled State**: The panel operates independently of V1 trading components.

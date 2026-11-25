# GD34 — SESSION PERFORMANCE REPORTING

**Project:** AlgoTrading V2.0  
**Phase:** GĐ34 — Bot Core Orchestration & Lifecycle Controller  
**Status:** ACCEPTED  
**Module:** `libs/bot/orchestration/performance.py`  

---

## 1. Overview & Storage

`BotPerformanceReporter` compiles reproducible, audit-grade quantitative metrics for simulation bot sessions. Reports are generated upon request, upon session pause, and during graceful shutdown.

### Storage Directory:
`data/paper_bot/performance/perf_<session_id>.json`

---

## 2. Metric Categories & Formulas

### Capital & Equity Metrics:
- **Initial Equity:** \$E_0\$ (Initial capital allocated to session).
- **Current Equity:** \$E_t = \text{Cash} + \sum (\text{Qty}_i \times \text{Price}_i)\$.
- **Cash & Available Cash:** Detailed cash balance separating total cash from reserved cash.
- **Gross & Net P&L:**
  $$\text{Realized PnL} = \sum (\text{Proceeds} - \text{Cost Basis})$$
  $$\text{Unrealized PnL} = \sum (\text{Market Value}_i - \text{Cost Basis}_i)$$
  $$\text{Total Return (\%)} = \frac{E_t - E_0}{E_0} \times 100\%$$

### Execution Quality & Friction:
- **Total Fees Incurred:** Sum of all simulated transaction fees across fills.
- **Estimated Slippage:** Quantified cost difference between decision reference price and execution fill price.
- **Turnover:** Total dollar volume traded.

### Signal Conversion Funnel:
- **Signals Received:** Total analytical signals emitted by strategy engine.
- **Signals Accepted:** Signals that passed all risk limits and portfolio boundaries.
- **Signals Rejected:** Signals rejected with categorized reason codes.
- **Acceptance Rate (\%):**
  $$\text{Acceptance Rate} = \frac{\text{Signals Accepted}}{\text{Signals Received}} \times 100\%$$

### Order Fulfillment Metrics:
- **Total Orders Created:** Sum of simulated orders created from accepted intents.
- **Filled Orders / Partial Fills / Cancelled Orders / Expired Orders.**
- **Fill Rate (\%):** Percentage of submitted orders that achieved fill status.

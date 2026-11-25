# GD33 — PORTFOLIO RECONCILIATION & ACCOUNTING INTEGRATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ33 — Order Management & Simulation Broker Engine  
**Modules:** `libs/bot/execution/portfolio_adapter.py`, `libs/bot/execution/ledger.py`  

---

## 1. Portfolio Application Mechanics

Each `SimulatedFill` is applied to `SimulationPortfolioManager` via `PortfolioExecutionAdapter` using strict Decimal math:

### A. BUY Fill:
$$\text{Cost} = (Q_{\text{fill}} \times P_{\text{fill}}) + \text{Fee}$$
- **Reservation Release:** Releases cash reservation corresponding to the filled portion:
  $$\text{ReleasedReservation} = Q_{\text{fill}} \times P_{\text{ref}}$$
- **Cash Deduction:** $\text{Portfolio.Cash} = \text{Portfolio.Cash} - \text{Cost}$
- **Position Update:** Updates `PositionBook` (quantity, cost basis, weighted average price).
- **Ledger Event:** Records `SIMULATED_FILL_BUY`.

### B. SELL Fill:
$$\text{Proceeds} = (Q_{\text{fill}} \times P_{\text{fill}}) - \text{Fee}$$
- **Cash Addition:** $\text{Portfolio.Cash} = \text{Portfolio.Cash} + \text{Proceeds}$
- **Position Update & Realized P&L:**
  $$\text{RealizedPnL}_{\Delta} = (P_{\text{fill}} - P_{\text{entry\_avg}}) \times Q_{\text{fill}} - \text{Fee}$$
  $$\text{Portfolio.RealizedPnL} = \text{Portfolio.RealizedPnL} + \text{RealizedPnL}_{\Delta}$$
- **Ledger Event:** Records `SIMULATED_FILL_SELL`.

### C. Order Cancellation / Expiration:
When an unfilled or partially filled order is cancelled or expires, the remaining reserved cash is released immediately:
$$\text{ReleasedRemaining} = Q_{\text{remaining}} \times P_{\text{ref}}$$

---

## 2. Three-Way Mathematical Reconciliation

The `ExecutionLedger.reconcile()` method validates mathematical consistency across three planes:

1. **Order vs Cumulative Fills:**
   $$\sum \text{FillQuantity}_{\text{order\_id}} == \text{Order.filled\_quantity}$$
2. **Net Fills vs Portfolio Position Book:**
   $$\sum Q_{\text{BUY}} - \sum Q_{\text{SELL}} == \text{Position.quantity}$$
3. **Cash Flow Conservation:**
   $$\text{InitialCash} - \sum (\text{BUY Notional} + \text{BUY Fees}) + \sum (\text{SELL Notional} - \text{SELL Fees}) == \text{Portfolio.Cash}$$

If all equations hold within rounding tolerances, the reconciliation returns `status="BALANCED"`.

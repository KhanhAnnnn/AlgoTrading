# GD32 — DRAWDOWN MONITORING & RISK LOCKOUT GUARDS

**Project:** AlgoTrading V2.0  
**Phase:** GĐ32 — Portfolio & Risk Management Engine  
**Module:** `libs/bot/risk/drawdown.py`  

---

## 1. Mathematical Definitions

Drawdown tracks the continuous decline in portfolio equity from its historical high-water mark (peak equity) during an active simulation session.

### Formulations:
1. **High-Water Mark (Peak Equity):**
   $$\text{PeakEquity}_t = \max(\text{PeakEquity}_{t-1}, \text{Equity}_t)$$

2. **Absolute Drawdown Amount:**
   $$\text{DrawdownAmount}_t = \max(0, \text{PeakEquity}_t - \text{Equity}_t)$$

3. **Percentage Drawdown:**
   $$\text{DrawdownPct}_t = \frac{\text{DrawdownAmount}_t}{\text{PeakEquity}_t}$$

---

## 2. Lockout State Machine & Invariants

When $\text{DrawdownPct}_t \ge \text{max\_drawdown\_pct}$ (default $10.0\%$):

1. **State Trip:**
   - `DrawdownMonitor.is_locked` transitions to `True`.
   - `SimulationPortfolioManager.set_state("RISK_LOCKED")`.
2. **Event Emission:**
   - Emits an immutable `RiskEvent` (severity: `LOCKOUT`, type: `DRAWDOWN_LIMIT_BREACHED`).
3. **Execution Freeze:**
   - In `RISK_LOCKED` state, all incoming BUY and opening SELL signals are strictly rejected with reason code `PORTFOLIO_RISK_LOCKED` or `DRAWDOWN_LIMIT_BREACHED`.
4. **Controlled Recovery:**
   - Resetting lockout requires an explicit operator call (`reset_lock()`), preventing automated premature re-entry.
   - Historical drawdown events and telemetry remain immutable on disk.

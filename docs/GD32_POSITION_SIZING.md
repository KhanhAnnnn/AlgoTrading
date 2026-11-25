# GD32 — POSITION SIZING ENGINE & 2% RISK SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ32 — Portfolio & Risk Management Engine  
**Module:** `libs/bot/risk/sizing.py`  
**Reference Document:** *Topic 4 - Paper Trading Bot.pdf* (Anil Gaddam)  

---

## 1. Overview & Research Status

The `PositionSizingEngine` determines the proposed asset quantity and notional value for incoming strategy signals.

> [!NOTE]
> All parameters (such as the 2% risk threshold) are explicitly modeled as **operator-configurable simulation research parameters**, NOT financial recommendations or guaranteed optimal thresholds.

---

## 2. The 2% Risk Sizing Rule

The baseline model implements Anil Gaddam's risk rule adapted with strict Decimal boundaries and cash caps:

### Mathematical Steps:
1. **Risk Budget Allocation:**
   $$\text{RiskBudget} = \text{PortfolioEquity} \times \text{risk\_per\_trade\_pct}$$
   *Example:* With $\$100,000$ equity and $2\%$ risk, $\text{RiskBudget} = \$2,000.00$.

2. **Stop Distance Evaluation:**
   $$\text{StopDistance} = |P_{\text{ref}} - P_{\text{stop}}|$$
   - **Zero Stop Distance Guard:** If $\text{StopDistance} == 0$, the calculation halts immediately, rejecting the signal with reason code `ZERO_STOP_DISTANCE` to prevent infinite sizing.
   - **Missing Stop Price Policy:** If no stop price is provided, sizing defaults to unhedged allocation capped by single-symbol concentration limits.

3. **Theoretical Quantity Calculation:**
   $$Q_{\text{raw}} = \frac{\text{RiskBudget}}{\text{StopDistance}}$$

4. **Cash & Buying Power Cap:**
   $$Q_{\text{cash\_max}} = \frac{\text{AvailableSimulatedCash}}{P_{\text{ref}}}$$
   $$Q_{\text{capped}} = \min(Q_{\text{raw}}, Q_{\text{cash\_max}})$$

5. **Position Limits Cap:**
   $$Q_{\text{notional\_max}} = \frac{\text{max\_position\_notional}}{P_{\text{ref}}}$$
   $$Q_{\text{final}} = \min(Q_{\text{capped}}, Q_{\text{notional\_max}}, \text{max\_position\_qty})$$

6. **Conservative Quantization:**
   $$Q_{\text{quantized}} = \text{quantize\_qty}(Q_{\text{final}}, \text{decimals})$$
   $$\text{ProposedNotional} = \text{quantize\_currency}(Q_{\text{quantized}} \times P_{\text{ref}})$$

---

## 3. Boundary & Guardrail Invariants

1. **Fractional Asset Preservation:** Fractional quantities (e.g., $0.25$ BTC) are never rounded up or down to integers.
2. **No Minimum-One Behavior:** If the sizing rule yields $0.05$ shares, it remains $0.05$ shares. The engine never artificially forces a minimum quantity of $1.0$.
3. **Non-Negative Guarantee:** Proposed quantity and notional must be strictly positive ($> 0$).
4. **Mutual Exclusion:** When submitting order intents, proposed quantity and proposed notional are aligned without contradictory overrides.
5. **Freshness Verification:** Prices older than 300 seconds are rejected (`STALE_REFERENCE_PRICE`).

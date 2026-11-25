# GD32 — PORTFOLIO ACCOUNTING & DECIMAL SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ32 — Portfolio & Risk Management Engine  
**Module:** `libs/bot/portfolio/accounting.py`  
**Precision Standard:** Python Decimal Fixed-Point Arithmetic  

---

## 1. Accounting Principles & Invariants

All calculations in the V2 Simulation Portfolio are strictly performed using Python `Decimal` arithmetic. Floating-point arithmetic is prohibited in calculation cores to eliminate binary representation bias and rounding errors.

### Precision Standards:
- **Currency (USD):** Quantized to 2 decimal places using `ROUND_HALF_UP` (`0.01` USD).
- **Asset Quantities:** Quantized to asset-specific decimals (Crypto: 4 to 8 decimals; Stocks: 2 to 4 decimals) using conservative `ROUND_DOWN` to avoid purchasing power over-allocation.
- **Fail-Closed Validation:** Conversion helper `to_decimal(v)` strictly rejects `NaN`, `+Inf`, `-Inf`, and `None`.

---

## 2. Core Mathematical Formulations

### A. Position Market Value
$$\text{MarketValue} = \text{Quantity} \times \text{ValuationPrice}$$

### B. Position Cost Basis
$$\text{CostBasis} = \text{Quantity} \times \text{AvgEntryPrice}$$

### C. Unrealized P&L
$$\text{UnrealizedPnL} = \text{MarketValue} - \text{CostBasis}$$

### D. Portfolio Equity
$$\text{Equity} = \text{Cash} + \sum_{i=1}^{M} \text{MarketValue}_i$$

### E. Available vs Reserved Cash
$$\text{AvailableCash} = \max(0, \text{Cash} - \text{ReservedCash})$$

### F. Weighted Average Cost on Position Increase
When expanding an existing long position by $\Delta Q$ shares at fill price $P_{\text{fill}}$:
$$\text{NewAvgPrice} = \frac{(Q_{\text{curr}} \times P_{\text{curr\_avg}}) + (\Delta Q \times P_{\text{fill}})}{Q_{\text{curr}} + \Delta Q}$$

### G. Realized P&L on Position Trimming / Closing
When closing $Q_{\text{closed}}$ shares at exit price $P_{\text{exit}}$:
- **Long Position:**
  $$\text{RealizedPnL} = (P_{\text{exit}} - P_{\text{avg}}) \times Q_{\text{closed}} - \text{Fee}$$
- **Short Position:**
  $$\text{RealizedPnL} = (P_{\text{avg}} - P_{\text{exit}}) \times Q_{\text{closed}} - \text{Fee}$$

---

## 3. Edge Case Handling

1. **Zero Quantity Positions:** When a position is fully liquidated ($Q = 0$), `market_value`, `cost_basis`, and `unrealized_pnl` are set to `0.0`. The position is retained in history or cleaned up without division by zero.
2. **Invalid Mark Prices:** If a market valuation price is non-positive ($\le 0$), `NaN`, or older than `max_price_age_seconds` (300s), `update_valuation()` returns `False` and leaves position valuation uncorrupted.
3. **Partial Fills / Staged Execution:** Accounted for via `record_fill()` with exact fee deduction.

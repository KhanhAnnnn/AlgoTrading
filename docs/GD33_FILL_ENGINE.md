# GD33 — 1-MINUTE BAR FILL ENGINE & ORDER TYPE SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ33 — Order Management & Simulation Broker Engine  
**Module:** `libs/bot/execution/fill_engine.py`  
**Execution Resolution:** Finalized 1-Minute Bars (`1m`, `is_final=True`)  

---

## 1. Anti-Lookahead Bias Guarantees

In backtesting and streaming simulation, executing an order on the same bar that triggered the signal creates look-ahead bias (assuming knowledge of the bar's future before it completes).

The GĐ33 Fill Engine enforces strict temporal separation:
1. **Source Bar Exclusion:** An order with `source_bar_key` is strictly prohibited from executing against that bar:
   $$\text{order.source\_bar\_key} \ne \text{execution\_bar.bar\_key}$$
2. **Next-Bar Execution:** Market orders execute on the Open of the subsequent eligible 1m bar:
   $$P_{\text{base}} = \text{execution\_bar.open}$$
3. **Bar Finality Requirement:** Only bars marked with `is_final = True` are admitted to the matching engine.

---

## 2. Order Type Execution Policies

### A. MARKET Order
- **Execution Price:** Base price is `execution_bar.open`, adjusted by adverse slippage.
- **Participation Cap:** Fill quantity is capped by allowable volume participation in the bar.

### B. LIMIT Order
- **BUY Condition:** Eligible if $\text{execution\_bar.low} \le P_{\text{limit}}$.
  - If $\text{execution\_bar.open} \le P_{\text{limit}}$ (favorable gap down): executes at $\min(P_{\text{limit}}, \text{open} + \text{slippage})$.
  - If $\text{execution\_bar.open} > P_{\text{limit}}$: executes at $P_{\text{limit}}$.
  - **Invariant:** $P_{\text{fill}} \le P_{\text{limit}}$ (never fill worse than limit).
- **SELL Condition:** Eligible if $\text{execution\_bar.high} \ge P_{\text{limit}}$.
  - **Invariant:** $P_{\text{fill}} \ge P_{\text{limit}}$ (never fill worse than limit).

### C. STOP Order
- **BUY Condition:** Triggers when $\text{execution\_bar.high} \ge P_{\text{stop}}$.
  - If gap up ($\text{open} \ge P_{\text{stop}}$): executes at $\text{open} + \text{slippage}$.
  - Otherwise: executes at $P_{\text{stop}} + \text{slippage}$.
- **SELL Condition:** Triggers when $\text{execution\_bar.low} \le P_{\text{stop}}$.
  - If gap down ($\text{open} \le P_{\text{stop}}$): executes at $\text{open} - \text{slippage}$.
  - Otherwise: executes at $P_{\text{stop}} - \text{slippage}$.

### D. STOP_LIMIT Order
- Two distinct phases:
  1. **Trigger Phase:** Once $\text{high} \ge P_{\text{stop}}$ (BUY) or $\text{low} \le P_{\text{stop}}$ (SELL), the order transitions to triggered state (`stop_triggered = True`).
  2. **Limit Phase:** Evaluates standard limit condition ($P_{\text{fill}} \le P_{\text{limit}}$ for BUY).
- **Intrabar Ambiguity:** Handled conservatively without assuming favorable intrabar price sequencing.

### E. TRAILING_STOP Order
- **SELL (Long Exit):**
  - Tracks peak price: $\text{TrailingRef}_t = \max(\text{TrailingRef}_{t-1}, \text{bar.high})$.
  - Stop trigger: $P_{\text{trigger}} = \text{TrailingRef}_t - \text{trailing\_offset}$.
  - Triggers when $\text{bar.low} \le P_{\text{trigger}}$.
- **BUY (Short Exit):**
  - Tracks trough price: $\text{TrailingRef}_t = \min(\text{TrailingRef}_{t-1}, \text{bar.low})$.
  - Stop trigger: $P_{\text{trigger}} = \text{TrailingRef}_t + \text{trailing\_offset}$.
  - Triggers when $\text{bar.high} \ge P_{\text{trigger}}$.

---

## 3. Volume Constraints & Partial Fills

1. **Max Participation Rate:** Default $10.0\%$ (`max_participation_rate = 0.10`).
   $$\text{AllowableBarVolume} = \text{bar.volume} \times \text{max\_participation\_rate}$$
2. **Zero Volume Guard:** If $\text{bar.volume} == 0$, the bar generates zero fills ($Q_{\text{fill}} = 0$).
3. **Competing Order Volume Sharing:** Multiple orders for the same symbol in a single bar share the allowable volume limit using deterministic FIFO sequencing.

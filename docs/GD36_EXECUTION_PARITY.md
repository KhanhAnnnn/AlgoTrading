# GĐ36 — EXECUTION INTEGRATION & BROKER PARITY

**Modules:** `libs/bot/execution/simulation_broker.py`, `libs/bot/backtesting/runner.py`  
**Parity Target:** GĐ33 Order Management & Simulation Broker Engine

---

## 1. Overview

A critical requirement of AlgoTrading V2.0 is that a strategy evaluated in a backtest must produce the identical fill, fee, slippage, and portfolio balances as if it were running live in forward paper trading.

GĐ36 achieves **zero-divergence parity** by utilizing the exact `SimulationBroker` and `SimulationPortfolioManager` created in GĐ32 and GĐ33.

---

## 2. The 5-Step Next-Bar Matching Cycle

For each bar $t$ in the historical dataset, the backtesting loop executes in the exact chronological sequence:

```
Incoming 1m Bar (t)
       │
       ▼
[Step 1] Broker Match & Fill (Orders submitted at t-1 or earlier)
       • Market orders fill at Bar(t).Open
       • Limit orders fill if Bar(t).Low <= LimitPrice (BUY) or High >= LimitPrice (SELL)
       • Stop orders trigger if Bar(t).High >= StopPrice (BUY) or Low <= StopPrice (SELL)
       • Volume participation cap enforces FillQty <= 0.10 * Bar(t).Volume
       │
       ▼
[Step 2] Mark-to-Market Valuation Update
       • PositionBook.update_valuation(symbol, Bar(t).Close)
       • Unrealized PnL updated across all open positions
       │
       ▼
[Step 3] Strategy Signal Evaluation
       • StrategyExecutionEngine.process_bar(Bar(t))
       • Emits StrategySignal(BUY / SELL / HOLD)
       │
       ▼
[Step 4] Risk & Portfolio Check
       • SignalDecisionEngine.evaluate(signal, reference_price=Bar(t).Close)
       • Position sizing and cash availability verified
       • Creates SimulationOrderIntent if ACCEPTED
       │
       ▼
[Step 5] Broker Intent Submission
       • SimulationBroker.submit_intent(intent)
       • Converts intent to SimulatedOrder in WORKING state
       • Order will be evaluated against Bar(t+1) in the NEXT iteration
```

---

## 3. Modeling Costs

### 3.1 Slippage Models
- **Zero Slippage:** `ZeroSlippageModel` executes strictly at base price.
- **Fixed BPS Slippage:** `FixedBpsSlippageModel(bps=5.0)`:
  $$\text{Price}_{\text{fill}} = \text{Price}_{\text{base}} \times \left(1 \pm \frac{\text{bps}}{10,000}\right)$$
- **Impact Slippage:** `ConfigurableImpactSlippageModel` scales slippage based on the participation rate:
  $$\text{Impact} = \text{Spread}_{\text{base}} + \gamma \cdot \left(\frac{\text{OrderQty}}{\text{BarVolume}}\right)^2$$

### 3.2 Fee Models
- **Configurable Equity Commission:**
  $$\text{Commission}_{\text{stocks}} = \max(\text{MinCommission}, \text{Qty} \times \text{PerShareFee})$$
  Default: $\$0.005/\text{share}$, minimum $\$1.00$.
- **Crypto Exchange Fees:**
  $$\text{Commission}_{\text{crypto}} = \text{Notional} \times \frac{\text{BPS}}{10,000}$$
  Default: 10 BPS ($0.10\%$).

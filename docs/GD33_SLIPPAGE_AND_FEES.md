# GD33 — SLIPPAGE & FEE MODELS SPECIFICATION

**Project:** AlgoTrading V2.0  
**Phase:** GĐ33 — Order Management & Simulation Broker Engine  
**Modules:** `libs/bot/execution/slippage.py`, `libs/bot/execution/fees.py`  

---

## 1. Slippage Models

Slippage represents execution friction between the observed reference/open price and actual filled price.

> [!NOTE]
> All slippage and fee configurations in GĐ33 are explicitly **research simulation models**, NOT real market guarantees or financial advice.

### Supported Models:

1. **`ZeroSlippageModel` (Baseline):**
   $$P_{\text{exec}} = P_{\text{base}}, \quad \text{Slippage} = \$0.00$$

2. **`FixedBpsSlippageModel`:**
   $$\text{SlippageAmount} = P_{\text{base}} \times \left(\frac{\text{BPS}}{10000}\right)$$
   - **BUY (Adverse Up):** $P_{\text{fill}} = P_{\text{base}} + \text{SlippageAmount}$
   - **SELL (Adverse Down):** $P_{\text{fill}} = \max(0.0001, P_{\text{base}} - \text{SlippageAmount})$

3. **`ConfigurableImpactSlippageModel`:**
   $$\text{EffectiveBps} = \text{BaseBps} + \left(\text{ImpactCoef} \times \frac{Q_{\text{order}}}{V_{\text{bar}}} \times 100\right)$$
   - Captures order size relative to available bar volume.

---

## 2. Commission & Fee Models

### Supported Schedules:

1. **`ZeroFeeModel` (Baseline):**
   $$\text{Fee} = \$0.00$$

2. **`ConfigurableFeeModel`:**
   - **Stocks (`STOCKS`):**
     $$\text{RawFee} = Q \times \text{stocks\_per\_share} \quad (\text{default: } \$0.005/\text{share})$$
     $$\text{Fee} = \max(\text{min\_commission}, \text{RawFee}) \quad (\text{min: } \$1.00)$$
   - **Crypto (`CRYPTO`):**
     $$\text{Fee} = (Q \times P_{\text{fill}}) \times \left(\frac{\text{crypto\_bps}}{10000}\right) \quad (\text{default: } 10\text{ BPS = } 0.10\%)$$
   - All fees are calculated with Python `Decimal` and quantized to 2 decimal places (`0.01` USD) with `ROUND_HALF_UP`.

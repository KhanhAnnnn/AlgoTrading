# GĐ36 — QUANTITATIVE PERFORMANCE & RISK ANALYTICS

**Module:** `libs/bot/backtesting/metrics.py`  
**Purpose:** Quantitative performance statistics, risk ratios, annualization, and research disclaimers.

---

## 1. Overview

The `BacktestMetricsCalculator` computes comprehensive financial, operational, and risk statistics from backtest executions. It avoids look-ahead distortion and phantom metric inflation on small datasets.

---

## 2. Mathematical Formulations

### 2.1 Capital & Returns
- **Net PnL:**
  $$\text{Net PnL} = E_{\text{final}} - E_{\text{initial}}$$
- **Net Return Percentage:**
  $$\text{Return}_{\%} = \frac{E_{\text{final}} - E_{\text{initial}}}{E_{\text{initial}}} \times 100\%$$
- **Gross PnL:**
  $$\text{Gross PnL} = \text{Realized PnL} + \text{Unrealized PnL} + \text{Total Fees}$$

### 2.2 Drawdown Curve
For each point $t$ along the equity series $E_t$:
- **Peak Equity:**
  $$P_t = \max_{0 \le i \le t} E_i$$
- **Drawdown ($):**
  $$D_t^{\$} = P_t - E_t$$
- **Drawdown (%):**
  $$D_t^{\%} = \frac{P_t - E_t}{P_t} \times 100\%$$
- **Max Drawdown:**
  $$\text{MDD}^{\$} = \max_t D_t^{\$}, \quad \text{MDD}^{\%} = \max_t D_t^{\%}$$

### 2.3 Risk-Adjusted Ratios & Annualization
For bar-by-bar percentage returns $R_t = \frac{E_t - E_{t-1}}{E_{t-1}}$:
- **Sampling Frequency:** Declared explicitly as `1m_bars`.
- **Annualization Factor ($K$):**
  - **Equities (STOCKS):** 252 trading days/year $\times$ 390 minutes/day = 98,280 bars/year:
    $$K_{\text{stocks}} = \sqrt{252 \times 390} \approx 313.496$$
  - **Crypto (CRYPTO):** 365 days/year $\times$ 1,440 minutes/day = 525,600 bars/year:
    $$K_{\text{crypto}} = \sqrt{365 \times 1,440} \approx 724.983$$
- **Sharpe Ratio:**
  $$\text{Sharpe} = \frac{\overline{R}}{\sigma_R} \times K$$
- **Sortino Ratio (Downside Deviation):**
  $$\sigma_{\text{down}} = \sqrt{\frac{1}{N_-} \sum_{R_t < 0} R_t^2}, \quad \text{Sortino} = \frac{\overline{R}}{\sigma_{\text{down}}} \times K$$

### 2.4 Trade Statistics
- **Total Trades:** Count of completed round-trip executions (fills // 2).
- **Win Rate:** Percentage of profitable round trips.
- **Profit Factor:**
  $$\text{PF} = \frac{\sum \text{Gains}}{\sum \text{Losses}}$$
- **Time In Market (%):** Proportion of bars during which an active position was held:
  $$\text{TIM} = \frac{\text{Bars with Position}}{\text{Total Tradable Bars}} \times 100\%$$

---

## 3. Regulatory & Research Disclaimer

Every calculated metric dictionary and output JSON artifact includes the mandatory disclaimer:
> *"Simulation metrics are calculated from historical backtesting data for research purposes only. Past simulation performance does not guarantee future financial returns."*

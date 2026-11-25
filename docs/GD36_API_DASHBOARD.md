# GĐ36 — BACKTESTING REST API & DASHBOARD INTEGRATION

**Endpoints Prefix:** `/api/v2/backtests`  
**Frontend Component:** `trading-dashboard/frontend/src/components/BacktestPanel.tsx`  
**Authentication:** Header `X-API-KEY: simulation_token_v2`

---

## 1. REST Endpoints Specification

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v2/backtests` | Creates and executes a backtest run | `201 Created` |
| `GET` | `/api/v2/backtests` | Lists all completed backtest runs | `200 OK` |
| `GET` | `/api/v2/backtests/{run_id}` | Retrieves metadata and summary metrics | `200 OK` / `404` |
| `GET` | `/api/v2/backtests/{run_id}/results`| Returns full quantitative results & fingerprint | `200 OK` / `404` |
| `GET` | `/api/v2/backtests/{run_id}/trades` | Returns simulated fills and trades list | `200 OK` / `404` |
| `GET` | `/api/v2/backtests/{run_id}/equity` | Returns sequential equity time series curve | `200 OK` / `404` |
| `POST` | `/api/v2/backtests/{run_id}/cancel` | Cancels active run or confirms completion | `200 OK` / `404` |
| `DELETE`| `/api/v2/backtests/{run_id}` | Removes run artifacts from disk storage | `200 OK` / `404` |

---

## 2. Request & Response Payload Examples

### 2.1 Launch Backtest (`POST /api/v2/backtests`)

```json
{
  "strategy_id": "MA_CROSS_1M",
  "symbols": ["NVDA"],
  "initial_simulated_cash": 100000.0,
  "warmup_bars_count": 50,
  "fee_model": "DEFAULT",
  "slippage_model": "DEFAULT",
  "volume_participation_rate": 0.10,
  "market_session_policy": "STRICT_HOURS",
  "seed": 42
}
```

Response (`201 Created`):
```json
{
  "status": "COMPLETED",
  "run_id": "bt_9481465c6eb8",
  "strategy_id": "MA_CROSS_1M",
  "symbols": ["NVDA"],
  "metrics": {
    "initial_equity": 100000.0,
    "final_equity": 102450.0,
    "net_pnl": 2450.0,
    "net_return_pct": 2.45,
    "sharpe_ratio": 1.84,
    "max_drawdown_pct": 0.85,
    "total_trades": 8,
    "win_rate_pct": 62.5,
    "deterministic_fingerprint": "6db28a0bb78553e7bd9255235003f39a..."
  },
  "deterministic_fingerprint": "6db28a0bb78553e7bd9255235003f39a...",
  "environment": "SIMULATION"
}
```

---

## 3. Dashboard UI Integration (`BacktestPanel.tsx`)

Mounted on tab `V2 Backtest` (`activeTab === 'backtesting'`):
1. **Interactive Config Form:**
   - Dropdown selection of strategy (`MA_CROSS_1M`, `RSI_1M`)
   - Asset selection (Stocks: `NVDA`, `AAPL`; Crypto: `BTC/USD`)
   - Virtual initial capital and warmup bar threshold
   - Fee and slippage model toggles
2. **Completed Runs Selector:**
   - Real-time list of historical runs with Net Return % color-coded badges
3. **Quantitative Breakdown Panel:**
   - Cards: Final Equity, Net PnL, Sharpe / Sortino Ratios, Max Drawdown %, Win Rate %
   - Deterministic SHA-256 fingerprint badge for auditability
   - Tabs:
     - `Quantitative Breakdown`: Realized PnL, Turnover, Slippage, Sampling details
     - `Trades & Fills`: Table of simulated executions with timestamps, price, fee, and slippage
     - `Equity Time Series`: Tabular and visual equity curve points
   - Safety Status: `TRADING_MODE=DRY_RUN`, `EXECUTION GATE=CLOSED (SAFE)`

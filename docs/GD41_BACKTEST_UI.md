# GĐ41 — BACKTEST DASHBOARD UI SPECIFICATION

## 1. User Interface Overview
The V2 Backtest Panel has been upgraded from requiring manual CSV uploads or synthetic fixtures to providing a complete one-click quantitative research interface.

---

## 2. Interactive Form Controls

| Control | Options / Type | Description |
|---|---|---|
| **Market Data Source** | `Alpaca Historical API`, `Verified Local Cache`, `Synthetic Fixture` | Determines where 1m bars originate. |
| **Asset Class** | `US Equities (Stocks)`, `Crypto 24/7 (Alpaca)` | Auto-detected when selecting symbol. |
| **Symbol** | `NVDA`, `AAPL`, `TSLA`, `BTC/USD`, `ETH/USD`, Custom | Target ticker for simulation. |
| **Stock Feed** | `IEX` (Free Tier), `SIP` (Full Market) | Applicable to Equities. |
| **Timeframe** | `1m (1-Minute OHLCV)` | Standard high-resolution quantitative bar timeframe. |
| **Date Range** | Datetime-local inputs + 3 Presets (`2 Hours`, `Full Day`, `Crypto 24h`) | User specifies historical UTC window. |
| **Force Refresh** | Checkbox | Bypasses local cache to query fresh data from Alpaca. |
| **Strategy Preset** | `MA_CROSS_1M`, `RSI_1M` | Quantitative algorithmic trading strategy. |
| **Simulated Capital** | Numeric input (Default: `$100,000`) | Initial virtual equity in USD. |
| **Warmup Bars** | Numeric input (Default: `20`) | Bars evaluated to warm up indicators before trading starts. |
| **Fee & Slippage Models** | `Default (5 bps)`, `Zero`, `Volume Impact` | Execution cost modeling. |

---

## 3. Real-Time Stage Transition Tracker
When the user clicks **"Fetch from Alpaca & Backtest"**, the UI dynamically displays the active phase with an animated progress banner:

1. `FETCHING`: Communicating with Alpaca Market Data API to retrieve 1-minute bars.
2. `VALIDATING`: Checking high $\ge$ low, high $\ge$ open, positive prices, volume, and session trading hours.
3. `CACHING`: Calculating canonical SHA-256 checksum and saving `manifest.json` and `bars.jsonl` to disk.
4. `BACKTESTING`: Simulating order matching on next eligible bar with strict anti-lookahead.
5. `COMPLETED`: Updating KPI cards, equity curve, trades list, and deterministic fingerprint.
6. `FAILED`: Displaying actionable error message (e.g. market closed, rate limit, authentication).

---

## 4. Provenance & Audit Badges
- **Real Market Data**: Emerald badge displaying `ALPACA REAL HISTORICAL DATA`, Feed tag (`IEX` / `CRYPTO`), and total bar count.
- **SHA-256 Checksum**: Full 64-character hash displayed with one-click copy.
- **Export CSV**: One-click download button fetching `GET /api/v2/historical-data/datasets/{id}/csv`.

---

## 5. Interactive TradingView Trade Chart & Bidirectional Explorer (`BacktestTradeChart.tsx`)
- **Chart Library**: `lightweight-charts` v5.2.1 (`Apache-2.0` license) with native 2-pane synchronization (`Pane 0`: Candlesticks, Volume, MA Fast/Slow; `Pane 1`: RSI 14 on 0–100 scale with OB/OS reference lines).
- **Exact Execution vs Signal Separation**:
  - **Execution Markers (`SimulatedFill`)**: Green `arrowUp` (`BUY`) and Red `arrowDown` (`SELL`) anchored at exact execution bar time & `fill_price`. Zero fills inside warmup bars. Multi-fill / partial-fill bars preserve every fill record.
  - **Signal Markers (`StrategySignal`)**: Toggleable `circle` markers (`SIG BUY` / `SIG SELL`) showing exact analytical trigger bar prior to next-bar execution.
- **Inspection Tooltip & Bidirectional Trade Explorer**:
  - Hovering or clicking any marker displays `Order ID`, `Fill ID`, `Side`, `Timestamp (UTC)`, `Quantity`, `Execution Price`, `Fee`, `Slippage`, `Strategy Reason`, and linked Closed Trade P&L.
  - Trade Explorer Table provides 3 views (`Execution Fills`, `Closed Trades Entry ↔ Exit`, `Portfolio Ledger`) and filters (`BUY/SELL`, `WIN/LOSS`, `Symbol`, `Strategy`, text search). Clicking any row zooms & highlights the exact bar/range on the chart.

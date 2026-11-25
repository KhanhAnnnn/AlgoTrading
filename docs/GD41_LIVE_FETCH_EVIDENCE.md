# GĐ41 — LIVE FETCH EVIDENCE

## 1. Verification with Live Alpaca API Credentials
Live historical fetches were executed against Alpaca Market Data API endpoints using verified paper account credentials.

### 1.1 US Equities: NVDA (NVIDIA Corp)
- **Symbol**: `NVDA`
- **Asset Class**: `STOCKS`
- **Feed**: `IEX` (Free tier endpoint)
- **Timeframe**: `1m`
- **Requested Window**: `2024-11-20T14:30:00Z` to `2024-11-20T16:30:00Z` (US Regular Trading Hours)
- **Bars Retrieved**: **121 bars**
- **First Bar**: `2024-11-20T14:30:00+00:00` (Open: \$147.36, Close: \$146.40, Volume: 54,642)
- **Last Bar**: `2024-11-20T16:30:00+00:00` (Open: \$144.53, Close: \$144.43, Volume: 14,357)
- **Dataset Checksum (SHA-256)**: `cd0448f447a731206f35b4ce70a31eb2460b37f48d0879685a08fc17f8cb79aa`
- **Completeness**: `COMPLETE` (Zero corrupt or negative bars, session hours verified)

### 1.2 Crypto 24/7: BTC/USD (Bitcoin)
- **Symbol**: `BTC/USD`
- **Asset Class**: `CRYPTO`
- **Feed**: `CRYPTO` (Alpaca Crypto Historical API)
- **Timeframe**: `1m`
- **Requested Window**: `2024-11-20T14:30:00Z` to `2024-11-20T16:30:00Z`
- **Bars Retrieved**: **115 bars**
- **First Bar**: `2024-11-20T14:30:00+00:00` (Open: \$94,576.40, Close: \$94,625.50)
- **Last Bar**: `2024-11-20T16:30:00+00:00` (Open: \$93,520.10, Close: \$93,548.28)
- **Dataset Checksum (SHA-256)**: `593aefe7b37f846d0a793a388b030df1a07dfbfca5174092b3a9e6bf08d5aa4d`
- **Completeness**: `COMPLETE`

---

## 2. One-Click Backtest Execution Evidence

### 2.1 NVDA Backtest Run
- **Run ID**: `bt_alpaca_25d5dd60c05c`
- **Strategy**: `MA_CROSS_1M` (v1.0.0)
- **Initial Cash**: \$100,000.00
- **Final Equity**: \$99,998.76
- **Total Trades**: 1 round-trip trade
- **Total Orders**: 2 (BUY 13.8 units @ \$144.97, SELL 13.8 units @ \$145.17)
- **Realized PnL**: +\$0.76 gross, -\$1.24 net after \$2.00 commission & \$0.14 slippage
- **Deterministic Fingerprint**: `c20560e4903a9977684f774e307889efc6b7e68b2e68c9914699f4f63fe3742f`

### 2.2 BTC/USD Backtest Run
- **Run ID**: `bt_alpaca_4889cfa7c5a9`
- **Strategy**: `MA_CROSS_1M` (v1.0.0)
- **Initial Cash**: \$100,000.00
- **Final Equity**: \$99,985.40
- **Total Trades**: 5 round-trip trades
- **Total Fills**: 10 fills
- **Deterministic Fingerprint**: `647ddf67b9124577962366f482c4ea9c51948fbe52899e3a2b9d305153174fcc`

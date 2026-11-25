# GĐ10.5 — Crypto Pipeline Operations & Runbook

## 1. Quick Start Commands

### 1.1 Managing Producers (Stocks & Crypto)
Use [`run-producers.ps1`](file:///d:/AlgoTrading/run-producers.ps1) to manage all background ingestion daemons and signal handlers:

```powershell
# Check status of all producers and handlers
powershell -ExecutionPolicy Bypass -File .\run-producers.ps1 -Action status

# Start continuous producers on Host
powershell -ExecutionPolicy Bypass -File .\run-producers.ps1 -Action start

# Start continuous producers via Docker Compose
powershell -ExecutionPolicy Bypass -File .\run-producers.ps1 -Action start -Docker

# Stop all producers and handlers
powershell -ExecutionPolicy Bypass -File .\run-producers.ps1 -Action stop

# Restart all producers
powershell -ExecutionPolicy Bypass -File .\run-producers.ps1 -Action restart
```

### 1.2 Starting Dashboard Backend & Frontend
```powershell
# Terminal 1: FastAPI Backend
cd D:\AlgoTrading\trading-dashboard\backend
d:\AlgoTrading\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8005

# Terminal 2: React Frontend Dev Server
cd D:\AlgoTrading\trading-dashboard\frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Dashboard is accessible at: `http://localhost:5173`
Backend API documentation at: `http://localhost:8005/docs`

---

## 2. Flink Jobs Management

### 2.1 Viewing Running Jobs
Access Flink JobManager Web Dashboard at: `http://localhost:8081`

To check via REST API:
```bash
curl http://localhost:8081/jobs/overview
```

### 2.2 Re-deploying Crypto Flink Job
If you modify `ddl_crypto.sql`:
```bash
d:\AlgoTrading\.venv\Scripts\python.exe submit_crypto_flink_job.py
```

### 2.3 Canceling a Flink Job
```bash
curl -X PATCH http://localhost:8081/jobs/<JOB_ID>?mode=cancel
```

---

## 3. Running Acceptance Tests

Execute the automated acceptance test suite to verify end-to-end pipeline health:

```powershell
d:\AlgoTrading\.venv\Scripts\python.exe -u test_gd10_5_crypto_acceptance.py
```

All test outcomes, timestamps, and metric evidence are saved to:
`D:\AlgoTrading\data\status\gd10_5_acceptance_report.json`

---

## 4. Paper Trading Safeguards & Execution Policy

> [!CAUTION]
> **Live Trading is strictly disabled in code.**
> All orders are guarded by `TRADING_MODE=DRY_RUN` and target `https://paper-api.alpaca.markets`.
> Zero orders are submitted to Alpaca Paper without explicit user approval of symbol, side, notional, and order count.

### 4.1 Order Intent Inspection
All detected signals, order calculations, and simulated executions are appended to:
`D:\AlgoTrading\data\orders\crypto_order_intent.json`

### 4.2 Paper Trading Execution Workflow (When Approved)
When the user explicitly authorizes a paper trade test:
1. Specify:
   - Target Symbol: `BTC/USD` or `ETH/USD`
   - Side: `BUY` or `SELL`
   - Notional Amount: e.g. \$50.00
   - Maximum Orders: e.g. 1
2. Set environment variable: `TRADING_MODE=PAPER_TRADING`
3. Execute approved test order.
4. Verify Alpaca order status transitions from `accepted` / `new` to `filled`.
5. Check portfolio equity and position updates on the dashboard.
6. Return `TRADING_MODE` back to `DRY_RUN`.

---

## 5. Troubleshooting & Log Locations

| Component | Log File Location | Checkpoint / State Location |
| :--- | :--- | :--- |
| **Crypto Producer** | `data/logs/crypto_producer.log` | `data/checkpoints/crypto_bars_checkpoint.json` |
| **Crypto News Poller** | `data/logs/crypto_producer.log` | `data/checkpoints/crypto_news_checkpoint.json` |
| **Crypto Signal Handler** | `logs/crypto_signal_handler.log` | `data/orders/crypto_order_intent.json` |
| **Producer Health Status** | `data/status/crypto_producer_health.json` | N/A |
| **Handler Health Status** | `data/status/crypto_handler_health.json` | N/A |
| **Acceptance Report** | `data/status/gd10_5_acceptance_report.json` | N/A |


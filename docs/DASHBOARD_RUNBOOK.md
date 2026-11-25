# Runbook: Live Trading Visualization Dashboard (Windows)

## 1. Prerequisites

Before launching the dashboard, ensure the underlying pipeline components are healthy:

1. **Docker Desktop**: Running in the current user session.
   - Verify: `docker ps`
   - Active containers required:
     - `redpanda-1` (`localhost:9092`)
     - `redpanda-2` (`localhost:9093`)
     - `redpanda-console` (`localhost:8080`)
     - `jobmanager` (`localhost:8081`)
     - `taskmanager`
2. **Python Environment**: Python 3.10+ (Current: Python 3.14 virtual environment at `D:\AlgoTrading\.venv`).
3. **Node.js**: Node 18+ (Current: Node v24.15.0).

---

## 2. Quick Start (Automated PowerShell Script)

A single PowerShell script starts both the backend and frontend servers:

```powershell
# Open PowerShell in repository root:
cd D:\AlgoTrading

# Execute launcher:
.\run-dashboard.ps1
```

Once launched:
- **Web Dashboard**: Open `http://localhost:5173` in any modern web browser.
- **Backend API**: Accessible at `http://localhost:8005/docs`.
- **WebSocket Feed**: `ws://localhost:8005/ws/live`.

---

## 3. Manual Step-by-Step Launch

If running individual components manually in separate PowerShell terminal windows:

### Terminal 1: Launch FastAPI Backend
```powershell
cd D:\AlgoTrading
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run Uvicorn backend on port 8005
python -m uvicorn main:app --host 0.0.0.0 --port 8005 --app-dir D:\AlgoTrading\trading-dashboard\backend
```

### Terminal 2: Launch React Frontend
```powershell
cd D:\AlgoTrading\trading-dashboard\frontend

# Start Vite dev server on port 5173
npm run dev -- --host 0.0.0.0 --port 5173
```

---

## 4. Running the Automated Test Suite (T01 - T16)

Execute all 16 integration and validation tests:

```powershell
cd D:\AlgoTrading
.\.venv\Scripts\pytest.exe D:\AlgoTrading\trading-dashboard\tests\test_t01_t16.py -v
```

Expected output:
```
16 passed in ~45s
```

---

## 5. System Health & Inspection Endpoints

| Service | Address | Purpose |
| :--- | :--- | :--- |
| **Trading Terminal UI** | `http://localhost:5173` | React TradingView Dashboard |
| **Backend REST API** | `http://localhost:8005/docs` | Swagger UI for testing API endpoints |
| **System Status Endpoint** | `http://localhost:8005/api/system/status` | JSON health of Kafka, Flink, and Latency |
| **Redpanda Web Console** | `http://localhost:8080` | Topic browser and message partition inspector |
| **Apache Flink Dashboard** | `http://localhost:8081` | JobManager UI, task slots, and SQL job metrics |

---

## 6. Operational Troubleshooting

### Issue 1: Port 8005 or 5173 in Use
- Check active listening ports:
  ```powershell
  Get-NetTCPConnection -LocalPort 8005, 5173 -ErrorAction SilentlyContinue
  ```
- To terminate a stale process by PID:
  ```powershell
  Stop-Process -Id <PID> -Force
  ```

### Issue 2: Redpanda Cluster Reconnection Failure
- Confirm broker containers are Up:
  ```powershell
  docker ps --filter "name=redpanda"
  ```
- If containers were stopped, start them safely without pruning:
  ```powershell
  docker compose -f D:\AlgoTrading\docker-compose.yml start
  ```

### Issue 3: Flink Streaming Job Restart
- Check active Flink jobs:
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8081/jobs"
  ```
- If the streaming SQL job is not RUNNING, submit `ddl_production.sql` via Flink SQL Client:
  ```powershell
  Get-Content ddl_production.sql -Raw | docker exec -i jobmanager ./bin/sql-client.sh
  ```

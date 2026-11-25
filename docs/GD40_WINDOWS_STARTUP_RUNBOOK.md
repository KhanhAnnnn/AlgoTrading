# GĐ40 — AlgoTrading V2.0 Windows Operational Startup Runbook

## 1. Scope & System Prerequisites

This runbook provides complete operational guidance for booting, supervising, and shutting down AlgoTrading V2.0 Simulation Release Candidate on Microsoft Windows environments (Windows 10/11 or Windows Server 2022).

### Prerequisites Checklist

| Component | Minimum Version | Verification Command | Expected Output |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11.x x64 | `python --version` | `Python 3.11.*` or `3.12.*` |
| **Node.js** | 20.x or 22.x LTS | `node --version` | `v20.*` or `v22.*` |
| **npm** | 10.x+ | `npm --version` | `10.*` |
| **PowerShell** | 5.1 or 7+ | `$PSVersionTable.PSVersion` | Major: 5, 7, etc. |
| **Docker Desktop** (Optional) | 4.x+ | `docker --version` | Used if running local Redpanda container |

---

## 2. Port Allocation & Pre-Flight Checks

Before starting services, ensure the required network ports are unallocated on localhost:

- **Port `8005`**: FastAPI V2 Backend REST API & WebSocket Server
- **Port `5173`**: React Vite Development / Preview Dashboard
- **Port `9092`**: Redpanda / Kafka Event Broker (if running live streaming)

To check port availability in PowerShell:
```powershell
Get-NetTCPConnection -LocalPort 8005, 5173, 9092 -ErrorAction SilentlyContinue | Format-Table LocalAddress, LocalPort, State, OwningProcess
```

If any port is held by an orphaned process:
```powershell
Stop-Process -Id <OwningProcessId> -Force
```

---

## 3. Step-by-Step Startup Procedure

### Step 3.1: Start the Message Broker (Redpanda)
*If running with full live streaming broker:*
```powershell
cd D:\AlgoTrading
docker compose up -d redpanda
```
*Note: In simulation mode or historical backtesting mode, the internal `ReplayManager` or `HistoricalReplayController` can operate without external Redpanda.*

---

### Step 3.2: Start the FastAPI V2 Backend

Open a dedicated PowerShell terminal (Console 1):

```powershell
cd D:\AlgoTrading
# Activate virtual environment if configured
# .\venv\Scripts\Activate.ps1

# Start FastAPI server on port 8005
python -m uvicorn libs.bot.api.main:app --host 127.0.0.1 --port 8005 --reload
```

**Verification of Backend Health**:
Open a secondary terminal and execute:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8005/api/v2/bots/overview" -Method GET
```
Expected response: JSON payload containing bot list and aggregate summary statistics.

---

### Step 3.3: Start the React Dashboard

Open a dedicated PowerShell terminal (Console 2):

```powershell
cd D:\AlgoTrading\trading-dashboard\frontend

# Option A: Start Vite development server (recommended for interactive demo)
npm run dev -- --port 5173

# Option B: Serve pre-built production bundle
npm run preview -- --port 5173
```

Open a web browser and navigate to:
```
http://localhost:5173
```

---

### Step 3.4: Automated Single-Script Startup (`run-dashboard.ps1`)

Alternatively, launch both backend and frontend via the unified repository script:
```powershell
cd D:\AlgoTrading
.\run-dashboard.ps1
```

---

## 4. Operational Lifecycle & Runtime Behaviors

### 4.1 Manual vs Auto-Start Behavior
- **Manual Start**: In this Release Candidate, services are launched via command-line or PowerShell scripts. Auto-start on Windows boot is NOT configured by default to ensure operators deliberately initialize simulation sessions.
- **Bot Lifecycle**: Bots registered in the SQLite session database (`data/sessions.db`) are loaded into memory in `STOPPED` state upon backend startup. Bots will NOT automatically execute trades until an operator issues an explicit `START` command via the Dashboard or REST API.

### 4.2 Browser Close Behavior
- If an operator closes the web browser tab or entire browser window:
  - **Zero Impact on Trading Engine**: The FastAPI backend and active Bot Orchestrator instances run as headless background Python processes.
  - Bots continue processing 1-minute market bars, evaluating signals, updating portfolio positions, and recording fills into SQLite uninterrupted.
  - Re-opening `http://localhost:5173` immediately reconnects the WebSocket and re-syncs current bot states and order histories.

### 4.3 Machine Restart & Crash Recovery
- If the Windows host is rebooted, powered off, or the Python process terminates unexpectedly:
  - **Durable Checkpoints**: State is preserved across SQLite tables (`sessions`, `positions`, `orders`, `fills`, `intent_store`).
  - **Recovery Sequence**: Upon restarting the backend (`libs.bot.api.main:app`), the `MultiBotSupervisor` initializes, inspects the SQLite database, reconstructs portfolio cash and open positions, and sets bot statuses to `STOPPED` with a `RECOVERED` flag.
  - Operators can inspect the portfolio reconciliation balance and safely issue `RESUME` or `START`.

---

## 5. Graceful Shutdown Procedure

To cleanly terminate all running services without leaving zombie processes or uncommitted database transactions:

1. **In Dashboard**: Navigate to **Multi-Bot Overview** and click **Stop All Bots** (or send `POST /api/v2/bots/{bot_id}/stop`).
2. **Stop Frontend**: In Console 2 (Vite), press `Ctrl + C` and type `Y`.
3. **Stop Backend**: In Console 1 (Uvicorn), press `Ctrl + C`. The event loop will flush active SQLite writes and shut down cleanly.
4. **Stop Redpanda (if running)**:
   ```powershell
   docker compose down
   ```

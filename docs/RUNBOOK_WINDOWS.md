# Windows PowerShell Runbook — Real-Time Algorithmic Trading

This runbook outlines operational procedures for managing, executing, and monitoring the Algorithmic Trading system on Windows 10/11 using PowerShell and Docker Desktop.

---

## 1. Prerequisites Checklist

Ensure the following tools are operational on Windows:
- **Docker Desktop**: Running with Linux containers (WSL2 backend).
- **PowerShell**: Version 5.1+ or PowerShell 7+.
- **Python**: 3.10+ (Verified on Python 3.14.4).
- **Ports Available**:
  - `8080`: Redpanda Console
  - `8081`: Apache Flink Dashboard
  - `9092`: Redpanda Node 1 host listener
  - `9093`: Redpanda Node 2 host listener

---

## 2. Infrastructure Operations (Docker Compose)

### 2.1 Start All Infrastructure Services
Open PowerShell and navigate to the project directory:
```powershell
cd D:\AlgoTrading
docker compose up -d redpanda-1 redpanda-2 redpanda-console jobmanager taskmanager
```

### 2.2 Verify Container Health
```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
Expected output:
- `redpanda-1`: Up (Ports 9092, 29092, 8082, 28082)
- `redpanda-2`: Up (Ports 9093, 29093, 8083, 28083)
- `redpanda-console`: Up (Port 8080)
- `jobmanager`: Up (Port 8081)
- `taskmanager`: Up (20 task slots available)

### 2.3 Stop Infrastructure Safely
> [!CAUTION]
> Never run `docker system prune` or `docker volume prune`. Stop containers using Docker Compose only.
```powershell
docker compose down
```

---

## 3. Kafka Topics Management

### 3.1 Verify Topics
```powershell
docker exec redpanda-1 rpk topic list --brokers redpanda-1:29092
```
Expected topics:
- `market-news`
- `stock-prices`
- `trading-signals`

### 3.2 Create Topics Manually (If Missing)
```powershell
docker exec redpanda-1 rpk topic create market-news stock-prices trading-signals --brokers redpanda-1:29092
```

---

## 4. Flink Streaming Job Deployment

### 4.1 Deploying the Production Streaming Pipeline
To submit the streaming pipeline to the running Flink cluster:
```powershell
cd D:\AlgoTrading
docker run --rm `
  --network algotrading_algotradingenvju `
  -v "D:\AlgoTrading\ddl_production.sql:/tmp/ddl_production.sql" `
  -e "FLINK_PROPERTIES=jobmanager.rpc.address: jobmanager`nrest.address: jobmanager" `
  --entrypoint /opt/flink/bin/sql-client.sh `
  algotrading-sql-client `
  embedded -l /opt/sql-client/lib --file /tmp/ddl_production.sql
```

### 4.2 Check Job Status via REST API
```powershell
Invoke-RestMethod -Uri "http://localhost:8081/jobs" -Method Get | ConvertTo-Json
```

---

## 5. Running Data Producers & Signal Handler

Activate the virtual environment or run directly with `.venv\Scripts\python.exe`:

### 5.1 Set Environment Variables (Current Session)
```powershell
$env:ALPACA_KEY_ID="your_alpaca_key_id"
$env:ALPACA_SECRET_KEY="your_alpaca_secret_key"
$env:ALPACA_TRADE_BASE_URL="https://paper-api.alpaca.markets"
$env:REDPANDA_BROKERS="localhost:9092,localhost:9093"
$env:TRADING_MODE="DRY_RUN"  # Use DRY_RUN until paper trading is confirmed
```

### 5.2 Launch News Producer
```powershell
D:\AlgoTrading\.venv\Scripts\python.exe D:\AlgoTrading\news-producer.py
```

### 5.3 Launch Price Producer
```powershell
D:\AlgoTrading\.venv\Scripts\python.exe D:\AlgoTrading\prices-producer.py
```

### 5.4 Launch Signal Handler
In a dedicated PowerShell terminal:
```powershell
# Set DRY_RUN mode for safety
$env:TRADING_MODE="DRY_RUN"
D:\AlgoTrading\.venv\Scripts\python.exe D:\AlgoTrading\signal-handler.py
```

To switch to Paper Trading (after verification):
```powershell
$env:TRADING_MODE="PAPER_TRADING"
D:\AlgoTrading\.venv\Scripts\python.exe D:\AlgoTrading\signal-handler.py
```

---

## 6. System Monitoring URLs

| Component | URL | Description |
|---|---|---|
| **Redpanda Console** | [http://localhost:8080](http://localhost:8080) | Topic inspect, consumer groups, message payloads |
| **Flink Dashboard** | [http://localhost:8081](http://localhost:8081) | Active streaming jobs, task slots, watermarks, metrics |
| **Alpaca Paper Portal** | [https://app.alpaca.markets](https://app.alpaca.markets) | Paper trading account balance, positions, orders |

---

## 7. Troubleshooting Common Errors

### 7.1 Port In Use Error
If port `8080` or `8081` is already occupied by another application:
```powershell
netstat -ano | findstr "8080"
```
In `docker-compose.yml`, modify host mapping (e.g., `"18080:8080"` for Redpanda Console or `"18081:8081"` for Flink).

### 7.2 Broker Connection Refused
If producers report `NoBrokersAvailable`:
1. Check `docker ps` to ensure `redpanda-1` and `redpanda-2` are running.
2. Confirm host listeners are mapped to `9092` and `9093`.
3. Verify test connection using:
   ```powershell
   D:\AlgoTrading\.venv\Scripts\python.exe -c "from kafka import KafkaAdminClient; client = KafkaAdminClient(bootstrap_servers='localhost:9092,localhost:9093'); print(client.list_topics()); client.close()"
   ```

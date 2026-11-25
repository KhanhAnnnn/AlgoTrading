# ==============================================================================
# scripts/status_all.ps1 — Complete Platform Health & Observability Dashboard
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RootPath = "D:\AlgoTrading"
$PythonExe = "$RootPath\.venv\Scripts\python.exe"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  ALGOTRADING PLATFORM HEALTH & TELEMETRY OBSERVABILITY          " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Docker Containers
Write-Host "`n--- [1] DOCKER INFRASTRUCTURE CONTAINERS ---" -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 2. Kafka Topics & Offsets
Write-Host "`n--- [2] REDPANDA TOPICS & MESSAGE COUNTS ---" -ForegroundColor Yellow
& $PythonExe -c "
import json
from kafka import KafkaConsumer, TopicPartition
try:
    c = KafkaConsumer(bootstrap_servers=['localhost:9092', 'localhost:9093'], request_timeout_ms=3000)
    for t in sorted(list(c.topics())):
        if 'test' in t: continue
        parts = c.partitions_for_topic(t) or []
        for p in sorted(parts):
            tp = TopicPartition(t, p)
            beg = c.beginning_offsets([tp])[tp]
            end = c.end_offsets([tp])[tp]
            print(f'  • {t:<20} [p={p}]: offset={end:<6} (messages={end-beg})')
    c.close()
except Exception as e:
    print('  [!] Error querying Kafka:', e)
"

# 3. Flink Streaming Jobs & Checkpoints
Write-Host "`n--- [3] APACHE FLINK STREAMING JOBS & CHECKPOINTS ---" -ForegroundColor Yellow
$flinkScript = @"
import urllib.request, json
try:
    ov = json.loads(urllib.request.urlopen('http://localhost:8081/jobs/overview', timeout=5).read())
    jobs = ov.get('jobs', [])
    print(f'  Active Flink Jobs ({len(jobs)}):')
    for j in jobs:
        jid = j['jid']
        name = j['name'].split('.')[-1]
        state = j['state']
        tasks = f\"{j['tasks']['running']}/{j['tasks']['total']}\"
        chk = json.loads(urllib.request.urlopen(f'http://localhost:8081/jobs/{jid}/checkpoints', timeout=5).read())
        completed_chk = chk.get('counts', {}).get('completed', 0)
        latest_chk = chk.get('latest', {}).get('completed', {})
        chk_id = latest_chk.get('id', 'N/A')
        print(f'  • [{state}] {name:<26} (jid={jid[:8]}...): Tasks={tasks}, Completed Checkpoints={completed_chk} (Latest: chk-{chk_id})')
except Exception as e:
    print('  [!] Flink WebUI not reachable:', e)
"@
& $PythonExe -c $flinkScript

# 4. Producers & Handlers Health
Write-Host "`n--- [4] PRODUCER & SIGNAL HANDLER STATE ---" -ForegroundColor Yellow
& $PythonExe -c "
import os, json
status_dir = r'$RootPath\data\status'
files = {
    'Price Producer': 'price_producer_health.json',
    'News Producer': 'news_producer_health.json',
    'Crypto Producer': 'crypto_producer_health.json',
    'Crypto Handler': 'crypto_handler_health.json'
}
for label, fname in files.items():
    p = os.path.join(status_dir, fname)
    if os.path.exists(p):
        try:
            with open(p, 'r') as f:
                d = json.load(f)
            status = d.get('status', 'OK')
            up = d.get('uptime_sec', 0)
            hb = d.get('last_heartbeat', 'N/A')
            print(f'  • {label:<18}: status={status}, uptime={up}s, last_heartbeat={hb}')
        except Exception as e:
            print(f'  • {label:<18}: Error reading health ({e})')
    else:
        print(f'  • {label:<18}: Health file not found')
"

# 5. FastAPI Backend & Telemetry
Write-Host "`n--- [5] FASTAPI BACKEND TELEMETRY (PORT 8005) ---" -ForegroundColor Yellow
try {
    $sys = Invoke-RestMethod -Uri "http://localhost:8005/api/system/status" -TimeoutSec 10
    Write-Host "  • Backend Status:      UP (Data Mode: $($sys.data_mode))" -ForegroundColor Green
    Write-Host "  • Latency Label:       $($sys.latency_label)" -ForegroundColor White
    Write-Host "  • Redpanda Connected:  $($sys.kafka.redpanda_connected)" -ForegroundColor White
    Write-Host "  • Flink Connected:     $($sys.flink.connected)" -ForegroundColor White
} catch {
    Write-Host "  [!] Backend port 8005 not responding: $_" -ForegroundColor Red
}

Write-Host "`n==================================================================" -ForegroundColor Cyan

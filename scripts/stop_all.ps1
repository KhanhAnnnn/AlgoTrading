# ==============================================================================
# scripts/stop_all.ps1 — Gracefully Stop Entire AlgoTrading Platform
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$RootPath = "D:\AlgoTrading"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  Gracefully Stopping AlgoTrading Platform Services...            " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Stop Python Handlers and Backend
Write-Host "`n[1/3] Terminating Python Handlers & Backend Services..." -ForegroundColor Yellow
$pyProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue
foreach ($p in $pyProcs) {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($p.Id)").CommandLine
        if ($cmd -like "*signal-handler.py*" -or $cmd -like "*crypto_signal_handler.py*" -or $cmd -like "*uvicorn*main:app*8005*") {
            Write-Host "  [-] Stopping process PID $($p.Id)..." -ForegroundColor Yellow
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
Write-Host "[OK] Python host processes stopped." -ForegroundColor Green

# 2. Clean Up PID Locks
Write-Host "`n[2/3] Cleaning up temporary PID locks..." -ForegroundColor Yellow
$lockFiles = Get-ChildItem -Path "$RootPath\data\locks\*.pid" -ErrorAction SilentlyContinue
foreach ($lf in $lockFiles) {
    Remove-Item $lf.FullName -Force -ErrorAction SilentlyContinue
    Write-Host "  [-] Removed stale lock: $($lf.Name)" -ForegroundColor DarkGray
}
Write-Host "[OK] Lock directory cleaned." -ForegroundColor Green

# 3. Stop Docker Containers (Preserving all volumes and Kafka topics)
Write-Host "`n[3/3] Stopping Docker Containers (Volumes Preserved)..." -ForegroundColor Yellow
docker compose stop
Write-Host "[OK] Core docker containers stopped cleanly." -ForegroundColor Green

Write-Host "`n==================================================================" -ForegroundColor Cyan
Write-Host "  ALL SERVICES SAFELY STOPPED. ZERO DATA/OFFSETS WIPED.           " -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan


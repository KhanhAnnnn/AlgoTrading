# scripts/stop_prod_web.ps1
# Controlled Shutdown Script for AlgoTrading v1.0.0 Production Web Server
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $RepoRoot "logs\prod_web_server.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "[INFO] No PID file found at $PidFile. Checking port 3000..." -ForegroundColor Yellow
    $Conn = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
    if ($Conn) {
        $Pids = $Conn | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($p in $Pids) {
            Write-Host "Stopping process $p on port 3000..." -ForegroundColor Cyan
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[OK] Stopped processes on port 3000." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Production Web Server is not running." -ForegroundColor Cyan
    }
    exit 0
}

$ServerPid = Get-Content $PidFile -ErrorAction SilentlyContinue
if ($ServerPid) {
    $Proc = Get-Process -Id $ServerPid -ErrorAction SilentlyContinue
    if ($Proc) {
        Write-Host "Gracefully stopping Production Web Server (PID $ServerPid)..." -ForegroundColor Cyan
        Stop-Process -Id $ServerPid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Production Web Server stopped." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Process $ServerPid was not running." -ForegroundColor Yellow
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}


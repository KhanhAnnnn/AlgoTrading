# scripts/start_prod_web.ps1
# Controlled Startup Script for AlgoTrading v1.0.0 Production Web Server
param(
    [int]$Port = 3000,
    [string]$HostAddress = "0.0.0.0"
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ServerScript = Join-Path $RepoRoot "scripts\prod_web_server.mjs"
$LogFile = Join-Path $RepoRoot "logs\prod_web_server.log"
$PidFile = Join-Path $RepoRoot "logs\prod_web_server.pid"

# Ensure logs dir exists
$LogsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

# Check if already listening on port
$Existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "[INFO] Port $Port is already in use by PID $($Existing[0].OwningProcess)." -ForegroundColor Yellow
    exit 0
}

Write-Host "Starting Production Web Server on port $Port..." -ForegroundColor Cyan

$Proc = Start-Process -FilePath "node" -ArgumentList "$ServerScript --port $Port --host $HostAddress" -WorkingDirectory $RepoRoot -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -WindowStyle Hidden -PassThru

if ($Proc) {
    $Proc.Id | Out-File -FilePath $PidFile -Encoding ascii
    Write-Host "[OK] Production Web Server started with PID $($Proc.Id)" -ForegroundColor Green
    Write-Host "     Serving at: http://localhost:$Port" -ForegroundColor Green
    Write-Host "     Health check: http://localhost:$Port/healthz" -ForegroundColor Green
} else {
    Write-Error "Failed to start Production Web Server"
    exit 1
}

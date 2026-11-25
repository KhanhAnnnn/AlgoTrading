# ==============================================================================
# Script: run-producers.ps1
# Description: Service manager for Continuous Stocks & Crypto Producers + Signal Handler
# Supports local .venv execution or Docker Compose execution
# ==============================================================================

param (
    [ValidateSet("start", "stop", "status", "restart")]
    [string]$Action = "status",
    [switch]$Docker
)

$RootPath = "D:\AlgoTrading"
$PythonExe = "$RootPath\.venv\Scripts\python.exe"
$DataDir = "$RootPath\data"
$LockDir = "$DataDir\locks"
$StatusDir = "$DataDir\status"

function Get-ProducerStatus {
    Write-Host "=== Continuous Producers & Handlers Status ===" -ForegroundColor Cyan
    
    # 1. Price Producer (Stocks)
    $pricePidFile = "$LockDir\price_producer.pid"
    $priceHealthFile = "$StatusDir\price_producer_health.json"
    $priceRunning = $false
    
    if (Test-Path $pricePidFile) {
        $pPid = Get-Content $pricePidFile -ErrorAction SilentlyContinue
        if ($pPid -and (Get-Process -Id $pPid -ErrorAction SilentlyContinue)) {
            $priceRunning = $true
            Write-Host "  Stocks Price Producer (Host): RUNNING (PID $pPid)" -ForegroundColor Green
        }
    }
    if (-not $priceRunning) {
        $dockerPrice = docker ps --filter "name=price-producer" --format "{{.Status}}" 2>$null
        if ($dockerPrice) {
            Write-Host "  Stocks Price Producer (Docker): $dockerPrice" -ForegroundColor Green
            $priceRunning = $true
        }
    }
    if (-not $priceRunning) {
        Write-Host "  Stocks Price Producer: STOPPED" -ForegroundColor Yellow
    }
    if (Test-Path $priceHealthFile) {
        $health = Get-Content $priceHealthFile | ConvertFrom-Json
        Write-Host "    State: $($health.status) | Uptime: $($health.uptime_sec)s | Heartbeat: $($health.last_heartbeat)" -ForegroundColor Gray
    }

    # 2. News Producer (Stocks)
    $newsPidFile = "$LockDir\news_producer.pid"
    $newsHealthFile = "$StatusDir\news_producer_health.json"
    $newsRunning = $false
    
    if (Test-Path $newsPidFile) {
        $nPid = Get-Content $newsPidFile -ErrorAction SilentlyContinue
        if ($nPid -and (Get-Process -Id $nPid -ErrorAction SilentlyContinue)) {
            $newsRunning = $true
            Write-Host "  Stocks News Producer (Host):  RUNNING (PID $nPid)" -ForegroundColor Green
        }
    }
    if (-not $newsRunning) {
        $dockerNews = docker ps --filter "name=news-producer" --format "{{.Status}}" 2>$null
        if ($dockerNews) {
            Write-Host "  Stocks News Producer (Docker): $dockerNews" -ForegroundColor Green
            $newsRunning = $true
        }
    }
    if (-not $newsRunning) {
        Write-Host "  Stocks News Producer:  STOPPED" -ForegroundColor Yellow
    }
    if (Test-Path $newsHealthFile) {
        $nHealth = Get-Content $newsHealthFile | ConvertFrom-Json
        Write-Host "    State: $($nHealth.status) | Uptime: $($nHealth.uptime_sec)s | Heartbeat: $($nHealth.last_heartbeat)" -ForegroundColor Gray
    }

    # 3. Crypto Producer (24/7 WebSocket + REST)
    $cryptoPidFile = "$LockDir\crypto_producer.pid"
    $cryptoHealthFile = "$StatusDir\crypto_producer_health.json"
    $cryptoRunning = $false
    
    if (Test-Path $cryptoPidFile) {
        $cPid = Get-Content $cryptoPidFile -ErrorAction SilentlyContinue
        if ($cPid -and (Get-Process -Id $cPid -ErrorAction SilentlyContinue)) {
            $cryptoRunning = $true
            Write-Host "  Crypto Producer (Host):       RUNNING (PID $cPid)" -ForegroundColor Green
        }
    }
    if (-not $cryptoRunning) {
        $dockerCrypto = docker ps --filter "name=crypto-producer" --format "{{.Status}}" 2>$null
        if ($dockerCrypto) {
            Write-Host "  Crypto Producer (Docker):      $dockerCrypto" -ForegroundColor Green
            $cryptoRunning = $true
        }
    }
    if (-not $cryptoRunning) {
        Write-Host "  Crypto Producer:       STOPPED" -ForegroundColor Yellow
    }
    if (Test-Path $cryptoHealthFile) {
        $cHealth = Get-Content $cryptoHealthFile | ConvertFrom-Json
        Write-Host "    State: $($cHealth.status) | Uptime: $($cHealth.uptime_sec)s | Heartbeat: $($cHealth.last_heartbeat)" -ForegroundColor Gray
    }

    # 4. Crypto Signal Handler (DRY_RUN Guard)
    $handlerPidFile = "$LockDir\crypto_signal_handler.pid"
    $handlerHealthFile = "$StatusDir\crypto_handler_health.json"
    $handlerRunning = $false
    
    if (Test-Path $handlerPidFile) {
        $hPid = Get-Content $handlerPidFile -ErrorAction SilentlyContinue
        if ($hPid -and (Get-Process -Id $hPid -ErrorAction SilentlyContinue)) {
            $handlerRunning = $true
            Write-Host "  Crypto Signal Handler (Host): RUNNING (PID $hPid)" -ForegroundColor Green
        }
    }
    if (-not $handlerRunning) {
        $dockerHandler = docker ps --filter "name=crypto-signal-handler" --format "{{.Status}}" 2>$null
        if ($dockerHandler) {
            Write-Host "  Crypto Signal Handler (Docker): $dockerHandler" -ForegroundColor Green
            $handlerRunning = $true
        }
    }
    if (-not $handlerRunning) {
        Write-Host "  Crypto Signal Handler: STOPPED" -ForegroundColor Yellow
    }
    if (Test-Path $handlerHealthFile) {
        $hHealth = Get-Content $handlerHealthFile | ConvertFrom-Json
        Write-Host "    State: $($hHealth.status) | Mode: $($hHealth.trading_mode) | Heartbeat: $($hHealth.last_heartbeat)" -ForegroundColor Gray
    }
}

function Start-Producers {
    if ($Docker) {
        Write-Host "[*] Starting producers via Docker Compose..." -ForegroundColor Cyan
        docker compose up -d price-producer news-producer crypto-producer crypto-signal-handler
        Start-Sleep -Seconds 3
        Get-ProducerStatus
        return
    }

    Write-Host "[*] Starting Continuous Producers on Host..." -ForegroundColor Cyan
    
    # 1. Price Producer (Stocks)
    $pricePidFile = "$LockDir\price_producer.pid"
    if (Test-Path $pricePidFile) {
        $pPid = Get-Content $pricePidFile -ErrorAction SilentlyContinue
        if ($pPid -and (Get-Process -Id $pPid -ErrorAction SilentlyContinue)) {
            Write-Host "  Stocks Price Producer already running (PID $pPid)." -ForegroundColor Yellow
        } else {
            Remove-Item $pricePidFile -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path $pricePidFile)) {
        Start-Process -FilePath $PythonExe -ArgumentList "continuous_price_producer.py" -WorkingDirectory $RootPath -WindowStyle Hidden
        Write-Host "  [OK] Launched Stocks Price Producer." -ForegroundColor Green
    }

    # 2. News Producer (Stocks)
    $newsPidFile = "$LockDir\news_producer.pid"
    if (Test-Path $newsPidFile) {
        $nPid = Get-Content $newsPidFile -ErrorAction SilentlyContinue
        if ($nPid -and (Get-Process -Id $nPid -ErrorAction SilentlyContinue)) {
            Write-Host "  Stocks News Producer already running (PID $nPid)." -ForegroundColor Yellow
        } else {
            Remove-Item $newsPidFile -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path $newsPidFile)) {
        Start-Process -FilePath $PythonExe -ArgumentList "continuous_news_producer.py" -WorkingDirectory $RootPath -WindowStyle Hidden
        Write-Host "  [OK] Launched Stocks News Producer." -ForegroundColor Green
    }

    # 3. Crypto Producer (24/7)
    $cryptoPidFile = "$LockDir\crypto_producer.pid"
    if (Test-Path $cryptoPidFile) {
        $cPid = Get-Content $cryptoPidFile -ErrorAction SilentlyContinue
        if ($cPid -and (Get-Process -Id $cPid -ErrorAction SilentlyContinue)) {
            Write-Host "  Crypto Producer already running (PID $cPid)." -ForegroundColor Yellow
        } else {
            Remove-Item $cryptoPidFile -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path $cryptoPidFile)) {
        Start-Process -FilePath $PythonExe -ArgumentList "continuous_crypto_producer.py" -WorkingDirectory $RootPath -WindowStyle Hidden
        Write-Host "  [OK] Launched Crypto Producer." -ForegroundColor Green
    }

    # 4. Crypto Signal Handler (DRY_RUN)
    $handlerPidFile = "$LockDir\crypto_signal_handler.pid"
    if (Test-Path $handlerPidFile) {
        $hPid = Get-Content $handlerPidFile -ErrorAction SilentlyContinue
        if ($hPid -and (Get-Process -Id $hPid -ErrorAction SilentlyContinue)) {
            Write-Host "  Crypto Signal Handler already running (PID $hPid)." -ForegroundColor Yellow
        } else {
            Remove-Item $handlerPidFile -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path $handlerPidFile)) {
        Start-Process -FilePath $PythonExe -ArgumentList "crypto_signal_handler.py" -WorkingDirectory $RootPath -WindowStyle Hidden
        Write-Host "  [OK] Launched Crypto Signal Handler (DRY_RUN)." -ForegroundColor Green
    }
    
    Start-Sleep -Seconds 3
    Get-ProducerStatus
}

function Stop-Producers {
    Write-Host "[*] Stopping Continuous Producers..." -ForegroundColor Cyan
    
    # Stop Docker containers if running
    docker compose stop price-producer news-producer crypto-producer crypto-signal-handler 2>$null
    
    # Stop Host processes
    $pricePidFile = "$LockDir\price_producer.pid"
    if (Test-Path $pricePidFile) {
        $pPid = Get-Content $pricePidFile -ErrorAction SilentlyContinue
        if ($pPid) {
            Stop-Process -Id $pPid -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped Stocks Price Producer (PID $pPid)." -ForegroundColor Green
        }
        Remove-Item $pricePidFile -Force -ErrorAction SilentlyContinue
    }
    
    $newsPidFile = "$LockDir\news_producer.pid"
    if (Test-Path $newsPidFile) {
        $nPid = Get-Content $newsPidFile -ErrorAction SilentlyContinue
        if ($nPid) {
            Stop-Process -Id $nPid -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped Stocks News Producer (PID $nPid)." -ForegroundColor Green
        }
        Remove-Item $newsPidFile -Force -ErrorAction SilentlyContinue
    }

    $cryptoPidFile = "$LockDir\crypto_producer.pid"
    if (Test-Path $cryptoPidFile) {
        $cPid = Get-Content $cryptoPidFile -ErrorAction SilentlyContinue
        if ($cPid) {
            Stop-Process -Id $cPid -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped Crypto Producer (PID $cPid)." -ForegroundColor Green
        }
        Remove-Item $cryptoPidFile -Force -ErrorAction SilentlyContinue
    }

    $handlerPidFile = "$LockDir\crypto_signal_handler.pid"
    if (Test-Path $handlerPidFile) {
        $hPid = Get-Content $handlerPidFile -ErrorAction SilentlyContinue
        if ($hPid) {
            Stop-Process -Id $hPid -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped Crypto Signal Handler (PID $hPid)." -ForegroundColor Green
        }
        Remove-Item $handlerPidFile -Force -ErrorAction SilentlyContinue
    }
    
    Write-Host "[OK] All producers stopped." -ForegroundColor Green
}

switch ($Action) {
    "start"   { Start-Producers }
    "stop"    { Stop-Producers }
    "restart" { Stop-Producers; Start-Sleep -Seconds 2; Start-Producers }
    "status"  { Get-ProducerStatus }
}

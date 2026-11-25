# scripts/backup_system.ps1
# Standardized Backup Script for AlgoTrading v1.0.0 Maintenance
param(
    [string]$BackupDir = "data/backups"
)

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
$TargetFolder = Join-Path $BackupDir "backup_$Timestamp"

Write-Host "Creating backup directory at: $TargetFolder" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $TargetFolder | Out-Null

# 1. Backup Mock Broker State
$MockStatePath = "data/mock_broker/mock_broker_state.json"
if (Test-Path $MockStatePath) {
    Copy-Item $MockStatePath -Destination $TargetFolder
    Write-Host "  [OK] Mock Broker state backed up." -ForegroundColor Green
} else {
    Write-Host "  [WARN] Mock Broker state file not found." -ForegroundColor Yellow
}

# 2. Backup Status Manifests
$StatusDir = "data/status"
if (Test-Path $StatusDir) {
    $StatusTarget = Join-Path $TargetFolder "status"
    New-Item -ItemType Directory -Force -Path $StatusTarget | Out-Null
    Copy-Item "$StatusDir/*.json" -Destination $StatusTarget
    Write-Host "  [OK] Status manifests backed up." -ForegroundColor Green
}

# 3. Create Backup Manifest
$Manifest = @{
    backup_timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    version = "v1.0.0"
    target_folder = $TargetFolder
    trading_mode = "DRY_RUN"
}
$ManifestPath = Join-Path $TargetFolder "backup_manifest.json"
$Manifest | ConvertTo-Json -Depth 4 | Out-File -FilePath $ManifestPath -Encoding utf8
Write-Host "  [OK] Backup manifest generated at $ManifestPath" -ForegroundColor Green
Write-Host "Backup completed successfully." -ForegroundColor Cyan


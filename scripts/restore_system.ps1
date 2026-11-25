# scripts/restore_system.ps1
# Standardized Restore/Recovery Script for AlgoTrading v1.0.0
param(
    [string]$SourceBackupFolder,
    [string]$DestinationDir = "data/mock_broker",
    [switch]$DryRunTest = $false
)

if (-not $SourceBackupFolder) {
    # Find latest backup in data/backups
    $Backups = Get-ChildItem "data/backups" -Directory | Sort-Object Name -Descending
    if ($Backups.Count -gt 0) {
        $SourceBackupFolder = $Backups[0].FullName
    } else {
        Write-Error "No backups found in data/backups"
        exit 1
    }
}

Write-Host "Restoring from backup: $SourceBackupFolder" -ForegroundColor Cyan

$MockBackupFile = Join-Path $SourceBackupFolder "mock_broker_state.json"
if (Test-Path $MockBackupFile) {
    if ($DryRunTest) {
        Write-Host "  [DRY_RUN TEST] Would restore $MockBackupFile to $DestinationDir" -ForegroundColor Yellow
    } else {
        New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
        Copy-Item $MockBackupFile -Destination $DestinationDir -Force
        Write-Host "  [OK] Mock Broker state restored to $DestinationDir" -ForegroundColor Green
    }
} else {
    Write-Host "  [WARN] mock_broker_state.json not found in backup." -ForegroundColor Yellow
}

Write-Host "Recovery operation completed." -ForegroundColor Cyan


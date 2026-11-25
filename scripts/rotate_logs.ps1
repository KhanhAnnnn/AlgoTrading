# scripts/rotate_logs.ps1
# Standardized Log Rotation Script for AlgoTrading v1.0.0
param(
    [string]$LogsDir = "logs",
    [int]$MaxSizeMB = 10
)

$ArchiveDir = Join-Path $LogsDir "archive"
if (-not (Test-Path $ArchiveDir)) {
    New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
}

$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmssZ")
Get-ChildItem -Path $LogsDir -Filter "*.log" | ForEach-Object {
    $SizeMB = $_.Length / 1MB
    if ($SizeMB -ge $MaxSizeMB) {
        $ArchiveName = "$($_.BaseName)_$Timestamp.log"
        $ArchivePath = Join-Path $ArchiveDir $ArchiveName
        Move-Item -Path $_.FullName -Destination $ArchivePath -Force
        New-Item -Path $_.FullName -ItemType File -Force | Out-Null
        Write-Host "Rotated $($_.Name) ($([math]::Round($SizeMB,2)) MB) -> $ArchiveName" -ForegroundColor Yellow
    } else {
        Write-Host "Log $($_.Name) is $([math]::Round($SizeMB,2)) MB (< $MaxSizeMB MB, no rotation needed)." -ForegroundColor Gray
    }
}
Write-Host "Log rotation check completed." -ForegroundColor Green


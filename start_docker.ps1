# start_docker.ps1
Write-Host "Checking Docker status..."
try {
    $out = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Docker is already running!"
        exit 0
    }
} catch {}

Write-Host "Starting Docker Desktop..."
Start-Process "C:\Users\Dell\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 3
    $proc = Get-Process -Name "*docker*" -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Docker processes found ($($proc.Count)). Testing docker info..."
        $info = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker Desktop is READY!"
            $ready = $true
            break
        }
    } else {
        Write-Host "Waiting for Docker Desktop processes..."
    }
}

if (-not $ready) {
    Write-Host "Docker did not become ready in time."
    docker info 2>&1
}

# Rebuild everything (base image built first, then all others use it)
# docker-compose build
# Push to Docker Hub (includes base + collector)
# .\push_to_hub.ps1 -Username imedbenmadi

param(
    [Parameter(Mandatory=$true)]
    [string]$Username
)

Write-Host "Logging into Docker Hub..." -ForegroundColor Green
docker login

Write-Host ""
Write-Host "Pushing images to Docker Hub..." -ForegroundColor Green
Write-Host ""

$images = @(
    "ost-2-base",
    "ost-2-kafka-producer",
    "ost-2-timescaledb-collector",
    "ost-2-federated-aggregator",
    "ost-2-device-viewer",
    "ost-2-database-init",
    "ost-2-monitoring-dashboard",
    "ost-2-grafana-init",
    "ost-2-spark-master",
    "ost-2-spark-worker-1",
    "ost-2-flink-jobmanager",
    "ost-2-flink-taskmanager"
)

$success = 0
$fail = 0

foreach ($img in $images) {
    Write-Host ">>> $img" -ForegroundColor Cyan
    
    $fullTag = $Username + "/" + $img + ":v1.0"
    $localTag = $img + ":latest"
    
    docker tag $localTag $fullTag
    docker push $fullTag
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    OK - Pushed to Docker Hub" -ForegroundColor Green
        $success++
    } else {
        Write-Host "    ERROR - Failed" -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Summary: $success pushed, $fail failed" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next: Replace imedbenmadi with $Username in docker-compose.yml" -ForegroundColor Cyan

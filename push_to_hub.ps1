# Build and push Docker images to Docker Hub
# Step 1: Build all images from Dockerfiles (base image built first, then all others inherit from it)
# Step 2: Login to Docker Hub
# Step 3: Push all 12 images to Docker Hub
# 
# Usage: .\push_to_hub.ps1 -Username imedbenmadi

param(
    [Parameter(Mandatory=$true)]
    [string]$Username
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Building Docker Images..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# List of Dockerfiles to build with their corresponding image names
$dockerfiles = @(
    @{name="ost-2-base"; dockerfile="docker/Dockerfile.base"},
    @{name="ost-2-kafka-producer"; dockerfile="docker/Dockerfile.producer"},
    @{name="ost-2-timescaledb-collector"; dockerfile="docker/Dockerfile.timescaledb-collector"},
    @{name="ost-2-federated-aggregator"; dockerfile="docker/Dockerfile.aggregator"},
    @{name="ost-2-device-viewer"; dockerfile="docker/Dockerfile.device-viewer"},
    @{name="ost-2-database-init"; dockerfile="docker/Dockerfile.database-init"},
    @{name="ost-2-monitoring-dashboard"; dockerfile="docker/Dockerfile.monitoring-dashboard"},
    @{name="ost-2-grafana-init"; dockerfile="docker/Dockerfile.grafana-init"},
    @{name="ost-2-spark-master"; dockerfile="docker/Dockerfile.spark"},
    @{name="ost-2-spark-worker-1"; dockerfile="docker/Dockerfile.spark"},
    @{name="ost-2-flink-jobmanager"; dockerfile="docker/Dockerfile.flink"},
    @{name="ost-2-flink-taskmanager"; dockerfile="docker/Dockerfile.flink"}
)

$buildSuccess = 0
$buildFail = 0

foreach ($img in $dockerfiles) {
    Write-Host "Building: $($img.name) from $($img.dockerfile)" -ForegroundColor Yellow
    
    $imageName = "$($img.name):latest"
    
    docker build -f $img.dockerfile -t $imageName .
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK - Built $($img.name)" -ForegroundColor Green
        $buildSuccess++
    } else {
        Write-Host "  ERROR - Build failed for $($img.name)" -ForegroundColor Red
        $buildFail++
    }
}

Write-Host ""
if ($buildFail -gt 0) {
    Write-Host "ERROR - $buildFail build(s) failed!" -ForegroundColor Red
    exit 1
}

Write-Host "All images built successfully" -ForegroundColor Green
Write-Host ""

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Logging into Docker Hub..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
docker login

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Pushing images to Docker Hub..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
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

if ($success -eq 12) {
    Write-Host "SUCCESS! All 12 images pushed to Docker Hub" -ForegroundColor Green
    Write-Host ""
    Write-Host "Images available at:" -ForegroundColor Cyan
    $images | ForEach-Object {
        Write-Host "  - docker.io/$Username/$_`:v1.0" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Green
    Write-Host "  1. Merge test_DockerHub branch to main" -ForegroundColor Yellow
    Write-Host "  2. Team members can now use: docker-compose up -d" -ForegroundColor Yellow
    Write-Host "  3. First-time setup: ~2 minutes (pull images)" -ForegroundColor Yellow
} else {
    Write-Host "ERROR - Some images failed to push. Check errors above." -ForegroundColor Red
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Logging into Docker Hub..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
docker login

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Pushing images to Docker Hub..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
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

if ($success -eq 12) {
    Write-Host "SUCCESS! All 12 images pushed to Docker Hub" -ForegroundColor Green
    Write-Host ""
    Write-Host "Images available at:" -ForegroundColor Cyan
    $images | ForEach-Object {
        Write-Host "  - docker.io/$Username/$_`:v1.0" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Green
    Write-Host "  1. Merge test_DockerHub branch to main" -ForegroundColor Yellow
    Write-Host "  2. Team members can now use: docker-compose up -d" -ForegroundColor Yellow
    Write-Host "  3. First-time setup: ~2 minutes (pull images)" -ForegroundColor Yellow
} else {
    Write-Host "ERROR - Some images failed to push. Check errors above." -ForegroundColor Red
    exit 1
}


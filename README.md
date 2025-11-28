# Federated Learning Platform for Edge IoT Data

## Deployment Architecture

The FLEAD platform employs a fully containerized Docker approach, utilizing a single-broker Kafka configuration to simulate realistic IoT streams while keeping resource usage low. All components (Kafka, Flink, Spark, TimescaleDB, and Grafana) run in isolated Docker containers, eliminating the complexities of local environment setup and ensuring cross-platform compatibility.

### Single-Broker Kafka Configuration

The system uses a single Kafka broker for development and lightweight local deployments. All 2400 IoT devices stream to the broker `kafka-broker-1` and data is partitioned inside that single broker as needed. This setup reduces complexity and resource usage.

### Docker-Only Approach

All components run in Docker containers with no local Python dependencies required. The Kafka producer script (`02_kafka_producer.py`) automatically:

1. Discovers and loads all 2400 device CSV files from data/processed/
2. Maps devices to brokers using device_id modulo 4
3. Connects to all 4 bootstrap servers simultaneously
4. Streams messages randomly across all devices at a configurable rate
5. Routes each message to its assigned broker partition

This approach eliminates NumPy compilation issues on Windows and ensures identical deployment across Windows, macOS, and Linux.

## Project Architecture

![FLEAD architecture](/project_architecture.png)

## Device Viewer

![Device Viewer](/Device%20Viewer.PNG)

## Pipeline Monitor

![Pipline Moniter](/Moniter.PNG)

**Key Features:**

-   Real-time streaming data processing with a single-broker Apache Kafka
-   Distributed model training on 2400 IoT devices using Apache Flink
-   Federated model aggregation using FedAvg algorithm
-   Time-series analytics with TimescaleDB and Apache Spark
-   Interactive visualization dashboards with Grafana 11.0.0
-   Complete Docker containerization (no local dependencies required)
-   Cross-platform deployment (Windows, macOS, Linux)
-   Automatic service orchestration and health checking

**Core Technologies:**

-   Apache Kafka 7.6.1 - Single-broker message streaming (KRaft mode)
-   Apache Flink 1.18 - Real-time processing
-   Apache Spark 3.5.0 - Batch analytics
-   TimescaleDB (PostgreSQL 16) - Time-series database
-   Grafana 11.0.0 - Visualization
-   Docker - Complete containerization (no local setup required)

## Dataset

This platform uses the Edge-IIoTset dataset, which contains network traffic and IoT device telemetry data.

-   **Source**: [Edge-IIoTset on Kaggle](https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset)
-   **Preprocessing Notebook**: [Data Preprocessing](https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac)
-   **Features**: 60+ network traffic features, including TCP, MQTT, DNS, and HTTP metrics
-   **Devices**: 2407 preprocessed device CSV files

## Docker Deployment Guide

### Prerequisites

-   Docker Desktop (Windows, macOS, or Linux)
-   No local Python installation required
-   Recommended: 8GB+ RAM, 10GB+ disk space
    -   Kaggle API Token (optional): If you want Docker to automatically download the Edge-IIoTSet dataset
            and generate processed chunks, place your Kaggle API token file `kaggle.json` inside the
            repository `kaggle/` folder: `./kaggle/kaggle.json`. The Docker compose mounts this directory into
            containers at `/root/.kaggle` so the `data-preprocessor` service (or Jupyter notebook) can access it.
    -   Security note: `kaggle.json` contains sensitive API credentials. Do NOT commit your `kaggle.json` to the repository.
            The project `.gitignore` already includes `kaggle/kaggle.json` and will prevent accidental commits.

### Why Docker-Only Architecture

This project uses complete containerization to avoid common deployment issues:

**Problem**: NumPy compilation on Windows requires C compiler (not installed by default)
**Solution**: All dependencies pre-installed in Docker images

**Problem**: Different Python versions/packages on each machine lead to incompatibilities
**Solution**: Identical environments in containers across all machines

**Problem**: Hard to manage 17 interconnected services with proper ordering
**Solution**: Docker Compose orchestrates services with automatic dependency management

**Problem**: Difficulty scaling to production environments
**Solution**: Docker images are production-ready and deployable to any platform

### System Components

18 total Docker containers (including optional dev and preprocessing services):

**Kafka Cluster (1 container)**

-   kafka-broker-1 (Port 9092)

**Infrastructure (2 containers)**

-   timescaledb (PostgreSQL 16 with TimescaleDB extension)
-   grafana (Data visualization)
 -   data-preprocessor (optional) — Downloads Edge-IIoTSet from Kaggle and creates processed chunks
    (service runs automatically if `data/processed/chunks` are missing)

**Stream Processing (4 containers)**

-   flink-jobmanager
-   flink-taskmanager
-   spark-master
-   spark-worker-1

**Batch Processing (2 containers)**

-   kafka-ui (Kafka management interface)
-   kafka-producer (Streams 2400 devices across brokers)
 -   jupyter-dev (Optional dev environment - mounts `./kaggle` and supports notebook exploration)

**Initialization (3 containers - run once)**

-   database-init (Creates schema)
-   grafana-init (Configures dashboards)
-   federated-aggregator (Aggregates models)

### Docker Container Images

**Custom Images (built during startup)**

-   `ost-2-kafka-producer:latest` - Multi-broker producer
-   `ost-2-flink-jobmanager:latest` - Flink coordinator
-   `ost-2-flink-taskmanager:latest` - Flink worker
-   `ost-2-spark-master:latest` - Spark coordinator
-   `ost-2-spark-worker-1:latest` - Spark executor
-   `ost-2-aggregator:latest` - Federated aggregation
 -   `ost-2-data-preprocessor:latest` - Kaggle downloader & preprocessing

**Pre-built Images (from Docker Hub)**

-   `confluentinc/cp-kafka:7.6.1` (4 instances)
-   `timescale/timescaledb-ha:pg16`
-   `grafana/grafana:11.0.0`
-   `provectuslabs/kafka-ui:latest`

### Networking

All containers connected via Docker bridge network `flead_network`:

**Internal DNS Resolution** (within containers)

-   kafka-broker-1:9092
-   timescaledb:5432 (Database)
-   flink-jobmanager:6123 (Flink RPC)
-   spark-master:7077 (Spark cluster)

**External Access** (from host machine)

-   Kafka: localhost:9092
-   TimescaleDB: localhost:5432
-   Grafana: localhost:3001
-   Kafka UI: localhost:8081
-   Flink UI: localhost:8161
-   Spark UI: localhost:8086

### Volume Mounting

**Data Volumes** (persistent storage)

-   kafka_broker_1_data, kafka_broker_2_data, kafka_broker_3_data, kafka_broker_4_data
-   timescaledb_data

**Code Volumes** (host machine)

-   ./scripts (mounted as /opt/flink/scripts in Flink)
-   ./data/processed (CSV files, read-only mount)
-   ./models (federated learning models, persistent)
 -   ./kaggle (Kaggle credentials - mounted to `/root/.kaggle` in containers; place `kaggle.json` here)

### Health Checks

Each container has automated health checks:

```
Kafka brokers: Check cluster membership (healthy after 30 seconds)
TimescaleDB: pg_isready command
Grafana: HTTP health endpoint
Flink: Web UI accessibility check
Spark: Web UI accessibility check
```

Docker Compose waits for health checks before starting dependent services.

## Dataset

This platform uses the Edge-IIoTset dataset, which contains network traffic and IoT device telemetry data.

-   **Source**: [Edge-IIoTset on Kaggle](https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset)
-   **Preprocessing Notebook**: [Data Preprocessing](https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac)
-   **Features**: 60+ network traffic features, including TCP, MQTT, DNS, and HTTP metrics
-   **Devices**: 2407 preprocessed device CSV files

## Run the Project

```batch
START.bat
```

This script:

1. Verifies Docker is installed and running
2. Stops any existing containers
3. Builds all 6 custom Docker images (if needed)
4. (Optional) Starts the `data-preprocessor` and `jupyter-dev` containers when present
    - `data-preprocessor` downloads the Edge-IIoTSet from Kaggle (requires `./kaggle/kaggle.json`) and generates `data/processed/chunks/`.
    - `jupyter-dev` provides an interactive notebook environment and mounts `./kaggle` for convenience
5. Starts 17 total Docker containers (1 Kafka broker + supporting services)
6. Waits 60 seconds for services to become healthy
7. Launches pipeline orchestrator to open all dashboards automatically

Alternative (cross-platform, host): `python scripts/pipeline_orchestrator.py`

Tip: The Windows `START.bat` script accepts `--fast` and `--no-wait` flags which are passed to `pipeline_orchestrator.py`.
Examples:

```powershell
START.bat --fast
START.bat --no-wait
```

If you need to run a full reset of the stack with backups and a fresh rebuild, you can use `scripts/cleanup_and_build.ps1` (PowerShell) or the manual commands documented below.

Tip: The orchestrator now supports `--fast` and `--no-wait` flags to reduce or skip the health checks during startup. Example:

```bash
# Run orchestrator with shortened waits (good for a powerful laptop)
python scripts/pipeline_orchestrator.py --fast

# Run orchestrator without any container health checks (start immediately)
python scripts/pipeline_orchestrator.py --no-wait
```

Notes:
- Spark driver (host) uses `SPARK_MASTER` with default `spark://localhost:7077` (set in `pipeline_orchestrator.py` and `05_spark_analytics.py`).
- In-cluster submit option: `docker compose exec spark-master /opt/spark/bin/spark-submit --master spark://spark-master:7077 /opt/spark/scripts/05_spark_analytics.py`.
- Spark analytics logs: `logs/spark_analytics.log`; orchestrator log: `logs/pipeline_orchestrator.log`.
- `spark-analytics` service reuses the aggregator image; `dashboard_metrics_updater.py` is baked into `docker/Dockerfile.aggregator`.

No local Python installation or dependency installation required. All dependencies are pre-installed in Docker container images.

## Stop the Project

```batch
STOP.bat
```

This script gracefully stops all Docker containers and preserves data volumes for next restart.

## System Architecture

```
CSV Files (2400 devices) → Kafka Single-Broker (kafka-broker-1)
    └─ Broker 1: devices_0-2399
        ↓ (edge-iiot-stream topic)
Flink (Local Training) → Local Model Updates
    ↓ (local-model-updates topic)
Federated Server (FedAvg) → Global Model
    ↓ (global-model-updates topic)
Spark Analytics → TimescaleDB → Grafana
```

### Kafka Configuration

-   **Mode**: KRaft (no Zookeeper required)
-   **Cluster ID**: 4L6g3nQlTjGEKK1RVAx_vQ
-   **Replication Factor**: 1 (single-broker; no inter-broker replication)
-   **Partitions**: 4 (one per broker)
-   **Bootstrap Servers**: kafka-broker-1:9092

### Service Dependencies

All services depend on the Kafka broker being healthy before starting:

-   Flink JobManager/TaskManager → kafka-broker-1
-   Spark Master/Worker → kafka-broker-1
-   Kafka Producer → kafka-broker-1
-   Federated Aggregator → kafka-broker-1

This ensures all consumers can access all partitions and prevents message loss.

## Access Points

| Service       | URL                   | Purpose               |
| ------------- | --------------------- | --------------------- |
| Device Viewer | http://localhost:8082 | Browse devices        |
| Kafka UI      | http://localhost:8081 | Monitor streams       |
| Grafana       | http://localhost:3001 | View dashboards       |
| Flink UI      | http://localhost:8161 | Job monitoring        |
| Monitoring    | http://localhost:5001 | Live system dashboard |

**Database:** localhost:5432 (user: flead, password: password)

### Grafana (Professional Dashboards)

-   **URL**: http://localhost:3001
-   **Login**: admin / admin
-   **Features**:
    -   Historical trends
    -   8 pre-configured panels
    -   Model accuracy graphs
    -   Device performance rankings
    -   Real-time data refresh (30 seconds)
    -   Data source: TimescaleDB (direct SQL queries)

### Monitoring Dashboard

-   **URL**: http://localhost:5001
-   **Features**:
    -   Service logos (Kafka, Flink, TimescaleDB, Grafana)
    -   Real-time pipeline flow visualization
    -   Color-coded health indicators
    -   Recent activity feed
    -   Updates every 2 seconds

### Docker Services Status

```bash
docker-compose ps
```

Expected output: All 17 containers should show "Up" or "Healthy" status:

-   1 Kafka broker (kafka-broker-1) - Healthy
-   1 TimescaleDB - Healthy
-   1 Grafana - Healthy
-   2 Flink nodes (JobManager, TaskManager) - Healthy
-   2 Spark nodes (Master, Worker) - Up
-   3 Init services (database-init, grafana-init, kafka-ui) - Up or Exited
-   2 Streaming services (kafka-producer, federated-aggregator) - Up

## Pipeline Explanation

### Data Distribution Strategy

The Kafka producer distributes 2400 IoT devices onto a single broker using device_id mapping:

```python
broker_index = (device_id_number // 600) % 4
```

Result: Each broker receives exactly 600 devices with independent data streams:

-   Broker 1: device_0 → device_599
-   Broker 2: device_600 → device_1199
-   Broker 3: device_1200 → device_1799
-   Broker 4: device_1800 → device_2399

All Kafka consumers (Flink, Spark, Aggregator) connect to the single broker via the bootstrap server, ensuring access to the complete dataset. This single-broker setup has no inter-broker replication (replication factor = 1).

### Component Pipeline

--   **Kafka Producer**: Streams 10 messages/second from randomly selected devices to the single broker.
-   **Local Training (Flink)**: Each device trains using Z-score anomaly detection on data from its assigned broker.
-   **Federated Aggregation**: Aggregates local models using FedAvg algorithm after receiving 20 device updates.
-   **Spark Analytics**: Processes data from all brokers and stores results in TimescaleDB. Grafana displays real-time dashboards with a 30-second refresh.

### 1. Data Streaming (Single-Broker)

Kafka producer streams 10 messages/second from randomly selected devices across 4 independent brokers. Each device is permanently assigned to one broker based on device_id, ensuring consistent routing and proper load distribution.

**Message Flow:**

--   Producer connects to the single broker bootstrap server
-   Producer randomly selects a device from all 2400 devices
-   Message routes to correct broker partition based on device assignment
-   Consumers (Flink, Spark) read from all brokers simultaneously

### 2. Local Training (Flink)

Each device trains using Z-score anomaly detection on its broker-specific data stream:

-   Maintains rolling window of 100 data points per device
-   Calculates mean (μ) and standard deviation (σ)
-   Detects anomaly if |Z-score| > 2.5
-   Trains local model every 50 rows OR 60 seconds per device

**Training trigger:** Every 50 rows OR every 60 seconds per device

**Z-score formula:**

```
Z = |X - μ| / σ
```

### 3. Federated Aggregation

Aggregates local models from all brokers using FedAvg algorithm after receiving 20 device updates.

**Formula:**

```
Global Accuracy = Σ(Local Accuracy × Samples) / Σ(Samples)
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
```

### 4. Analytics & Visualization (Single-Broker)

Spark reads data from the single Kafka broker and stores results in TimescaleDB. Grafana displays real-time dashboards with 30-second refresh, sourcing data from TimescaleDB via direct SQL queries.

**Processing Pipeline:**

--   Spark connects to the single broker bootstrap server
-   Reads complete dataset from all brokers (with replication redundancy)
-   Evaluates models on diverse data across all partitions
-   Stores results in TimescaleDB hypertables (time-series optimized)
-   Grafana queries TimescaleDB for visualization

| Component          | Processing Time   |
| ------------------ | ----------------- |
| Kafka streaming    | 5 messages/sec    |
| Flink processing   | <10ms per event   |
| Model training     | 50 rows or 60 sec |
| Global aggregation | Every 20 updates  |
| End-to-end latency | 5-15 seconds      |

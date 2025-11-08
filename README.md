# Federated Learning Platform for Edge IoT Data

## Deployment Architecture

The FLEAD platform utilizes a fully containerized Docker approach with a 4-broker Kafka cluster to simulate realistic distributed IoT environments. All components (Kafka, Flink, Spark, TimescaleDB, Grafana) run in isolated Docker containers, eliminating local environment setup complexities and ensuring cross-platform compatibility.

### Multi-Broker Kafka Architecture

The system implements a 4-broker Kafka cluster distributing 2400 IoT devices across independent brokers:

-   **Broker 1** (Port 29092/9092): Devices 0-599 (600 devices)
-   **Broker 2** (Port 29093/9093): Devices 600-1199 (600 devices)
-   **Broker 3** (Port 29094/9094): Devices 1200-1799 (600 devices)
-   **Broker 4** (Port 29095/9095): Devices 1800-2399 (600 devices)

This distribution provides fault tolerance (replication factor 3), load balancing, and realistic representation of enterprise-scale IoT deployments with independent data streams per broker.

### Docker-Only Approach

All components run in Docker containers with no local Python dependencies required. The Kafka producer script (`02_kafka_producer_multi_broker.py`) automatically:

1. Discovers and loads all 2400 device CSV files from data/processed/
2. Maps devices to brokers using device_id modulo 4
3. Connects to all 4 bootstrap servers simultaneously
4. Streams messages randomly across all devices at configurable rate
5. Routes each message to its assigned broker partition

This approach eliminates NumPy compilation issues on Windows and ensures identical deployment across Windows, macOS, and Linux.

## Project Architecture

![FLEAD architecture](/project_architecture.png)

## Device Viewer

![Device Viewer](/Device%20Viewer.PNG)

## Pipline Moniter

![Pipline Moniter](/Moniter.PNG)

**Key Features:**

-   Real-time streaming data processing with 4-broker Apache Kafka cluster
-   Distributed model training on 2400 IoT devices using Apache Flink
-   Federated model aggregation using FedAvg algorithm
-   Time-series analytics with TimescaleDB and Apache Spark
-   Interactive visualization dashboards with Grafana 11.0.0
-   Complete Docker containerization (no local dependencies required)
-   Cross-platform deployment (Windows, macOS, Linux)
-   Automatic service orchestration and health checking

**Core Technologies:**

-   Apache Kafka 7.6.1 - Multi-broker message streaming (KRaft mode)
-   Apache Flink 1.18 - Real-time processing
-   Apache Spark 3.5.0 - Batch analytics
-   TimescaleDB (PostgreSQL 16) - Time-series database
-   Grafana 11.0.0 - Visualization
-   Docker - Complete containerization (no local setup required)

## Dataset

This platform uses the Edge-IIoTset dataset, which contains network traffic and IoT device telemetry data.

-   **Source**: [Edge-IIoTset on Kaggle](https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset)
-   **Preprocessing Notebook**: [Data Preprocessing](https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac)
-   **Features**: 60+ network traffic features including TCP, MQTT, DNS, and HTTP metrics
-   **Devices**: 2407 preprocessed device CSV files

## Docker Deployment Guide

### Prerequisites

-   Docker Desktop (Windows, macOS, or Linux)
-   No local Python installation required
-   Recommended: 8GB+ RAM, 10GB+ disk space

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

17 total Docker containers:

**Kafka Cluster (4 containers)**

-   kafka-broker-1 (Port 9092, 29092)
-   kafka-broker-2 (Port 9093, 29093)
-   kafka-broker-3 (Port 9094, 29094)
-   kafka-broker-4 (Port 9095, 29095)

**Infrastructure (2 containers)**

-   timescaledb (PostgreSQL 16 with TimescaleDB extension)
-   grafana (Data visualization)

**Stream Processing (4 containers)**

-   flink-jobmanager
-   flink-taskmanager
-   spark-master
-   spark-worker-1

**Batch Processing (2 containers)**

-   kafka-ui (Kafka management interface)
-   kafka-producer (Streams 2400 devices across brokers)

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

**Pre-built Images (from Docker Hub)**

-   `confluentinc/cp-kafka:7.6.1` (4 instances)
-   `timescale/timescaledb-ha:pg16`
-   `grafana/grafana:11.0.0`
-   `provectuslabs/kafka-ui:latest`

### Networking

All containers connected via Docker bridge network `flead_network`:

**Internal DNS Resolution** (within containers)

-   kafka-broker-1:29092 (Kafka internal listener)
-   kafka-broker-2:29093
-   kafka-broker-3:29094
-   kafka-broker-4:29095
-   timescaledb:5432 (Database)
-   flink-jobmanager:6123 (Flink RPC)
-   spark-master:7077 (Spark cluster)

**External Access** (from host machine)

-   Kafka: localhost:9092, localhost:9093, localhost:9094, localhost:9095
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
-   **Features**: 60+ network traffic features including TCP, MQTT, DNS, and HTTP metrics
-   **Devices**: 2407 preprocessed device CSV files

## Run the Project

```batch
START.bat
```

This script:

1. Verifies Docker is installed and running
2. Stops any existing containers
3. Builds all 6 custom Docker images (if needed)
4. Starts 17 total Docker containers (4 Kafka brokers + supporting services)
5. Waits 60 seconds for services to become healthy
6. Launches pipeline orchestrator to open all dashboards automatically

No local Python installation or dependency installation required. All dependencies are pre-installed in Docker container images.

## Stop the Project

```batch
STOP.bat
```

This script gracefully stops all Docker containers and preserves data volumes for next restart.

## System Architecture

```
CSV Files (2400 devices) → Kafka Multi-Broker Cluster (4 brokers)
    ├─ Broker 1: devices_0-599
    ├─ Broker 2: devices_600-1199
    ├─ Broker 3: devices_1200-1799
    └─ Broker 4: devices_1800-2399
        ↓ (edge-iiot-stream topic, replicated across 3 brokers)
Flink (Local Training) → Local Model Updates
    ↓ (local-model-updates topic)
Federated Server (FedAvg) → Global Model
    ↓ (global-model-updates topic)
Spark Analytics → TimescaleDB → Grafana
```

### Kafka Configuration

-   **Mode**: KRaft (no Zookeeper required)
-   **Cluster ID**: 4L6g3nQlTjGEKK1RVAx_vQ
-   **Replication Factor**: 3 (fault tolerance)
-   **Partitions**: 4 (one per broker)
-   **Bootstrap Servers**: kafka-broker-1:29092,kafka-broker-2:29093,kafka-broker-3:29094,kafka-broker-4:29095

### Service Dependencies

All services depend on all 4 Kafka brokers being healthy before starting:

-   Flink JobManager/TaskManager → All 4 brokers
-   Spark Master/Worker → All 4 brokers
-   Kafka Producer → All 4 brokers
-   Federated Aggregator → All 4 brokers

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

-   4 Kafka brokers (kafka-broker-1 through kafka-broker-4) - Healthy
-   1 TimescaleDB - Healthy
-   1 Grafana - Healthy
-   2 Flink nodes (JobManager, TaskManager) - Healthy
-   2 Spark nodes (Master, Worker) - Up
-   3 Init services (database-init, grafana-init, kafka-ui) - Up or Exited
-   2 Streaming services (kafka-producer, federated-aggregator) - Up

## Pipeline Explanation

### Data Distribution Strategy

The Kafka producer distributes 2400 IoT devices across 4 brokers using device_id modulo calculation:

```python
broker_index = (device_id_number // 600) % 4
```

Result: Each broker receives exactly 600 devices with independent data streams:

-   Broker 1: device_0 → device_599
-   Broker 2: device_600 → device_1199
-   Broker 3: device_1200 → device_1799
-   Broker 4: device_1800 → device_2399

All Kafka consumers (Flink, Spark, Aggregator) connect to all 4 brokers via bootstrap servers, ensuring access to complete dataset regardless of broker failures (with replication factor 3).

### Component Pipeline

-   **Kafka Producer**: Streams 10 messages/second from randomly selected devices across all 4 brokers.
-   **Local Training (Flink)**: Each device trains using Z-score anomaly detection on data from its assigned broker.
-   **Federated Aggregation**: Aggregates local models using FedAvg algorithm after receiving 20 device updates.
-   **Spark Analytics**: Processes data from all brokers and stores results in TimescaleDB. Grafana displays real-time dashboards with 30-second refresh.

### 1. Data Streaming (Multi-Broker)

Kafka producer streams 10 messages/second from randomly selected devices across 4 independent brokers. Each device is permanently assigned to one broker based on device_id, ensuring consistent routing and proper load distribution.

**Message Flow:**

-   Producer connects to all 4 broker bootstrap servers
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

### 4. Analytics & Visualization (Multi-Broker)

Spark reads data from all 4 Kafka brokers and stores results in TimescaleDB. Grafana displays real-time dashboards with 30-second refresh, sourcing data from TimescaleDB via direct SQL queries.

**Processing Pipeline:**

-   Spark connects to all 4 broker bootstrap servers
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

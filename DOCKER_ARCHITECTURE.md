# Docker Architecture Overview

## System Architecture

The FLEAD platform uses a containerized microservices architecture with 6 custom Docker images and 5 pre-built images, orchestrated via Docker Compose. All services run in isolated containers on a shared bridge network (`flead_network`) with automatic service discovery via Docker DNS.

## Directory Structure

```
docker/
├── Dockerfile.aggregator          # Federated model aggregation service
├── Dockerfile.database-init       # Database schema initialization
├── Dockerfile.flink              # Apache Flink stream processing
├── Dockerfile.grafana-init       # Grafana dashboard configuration
├── Dockerfile.producer           # Kafka message producer (IoT data)
└── Dockerfile.spark              # Apache Spark batch analytics

docker-compose.yml                # Service orchestration and networking
```

## Deployment Approach

### Traditional Local Approach (Deprecated)

-   Python installed locally on user machine
-   NumPy compilation requires C compiler (fails on Windows)
-   Environment configuration scattered across local system
-   Dependency conflicts and version mismatches
-   Manual service startup and dependency ordering

### New Docker Approach (Current)

-   All dependencies pre-installed in container images
-   No local Python compilation needed
-   Isolated environments prevent conflicts
-   Automatic dependency ordering via service_healthy conditions
-   Single command startup: `docker-compose up -d`
-   Cross-platform compatibility (Windows/Mac/Linux)

## Custom Docker Images

### 1. Dockerfile.producer

**Purpose:** Streams IoT sensor data from CSV files to Kafka topics

**Base Image:** `python:3.10-slim`

**Key Components:**

-   Kafka Python client library
-   CSV data loader
-   Message formatting and batching
-   Rate limiting (8-10 msgs/sec configurable)

**Runtime:**

-   Mounts: `./data/processed:/app/data/processed` (2,400+ CSV files)
-   Environment: `KAFKA_BOOTSTRAP_SERVERS=kafka:29092`, `DATA_PATH=/app/data/processed`
-   Depends on: Kafka healthy, database-init completed
-   Streams to: `edge-iiot-stream` Kafka topic
-   Health Check: Validates connection to `kafka:29092`

**Data Flow:**

```
CSV Files → Kafka Producer → edge-iiot-stream Topic → Kafka Broker
```

### 2. Dockerfile.aggregator

**Purpose:** Aggregates distributed model updates using Federated Averaging (FedAvg)

**Base Image:** `python:3.10-slim`

**Key Components:**

-   Kafka Python client (consumer/producer)
-   PostgreSQL connection library (psycopg2)
-   NumPy, scikit-learn for model aggregation
-   FedAvg algorithm implementation

**Runtime:**

-   Mounts: `./models:/app/models` (persistent model storage)
-   Environment: Kafka bootstrap servers, database credentials
-   Depends on: Kafka healthy, TimescaleDB healthy, database-init completed
-   Consumes from: `local-model-updates` Kafka topic
-   Produces to: `global-model-updates` Kafka topic
-   Health Check: Validates Kafka and database connectivity

**Data Flow:**

```
local-model-updates Topic → Aggregator → FedAvg → global-model-updates Topic
                                      ↓
                              Models/ directory (persistent)
```

### 3. Dockerfile.flink

**Purpose:** Real-time stream processing for anomaly detection and local model training

**Base Image:** `flink:1.18-scala_2.12-java11`

**Key Components:**

-   Apache Flink 1.18 (stream processing engine)
-   PyFlink Python API
-   Kafka source/sink connectors
-   TensorFlow for local model training

**Runtime:**

-   Two services: `flink-jobmanager` (scheduler) and `flink-taskmanager` (execution)
-   JobManager: Listens on port 6123 (RPC), 8161 (Web UI)
-   TaskManager: Executes parallel tasks (4 task slots, 2GB memory)
-   Consumes from: `edge-iiot-stream` Kafka topic
-   Produces to: `anomalies` and `local-model-updates` topics
-   Health Check: HTTP GET to Flink Web UI (http://localhost:8161/)

**Data Processing Pipeline:**

```
edge-iiot-stream Topic → Flink → Anomaly Detection → anomalies Topic
                             ↓
                        Local Training → local-model-updates Topic
```

### 4. Dockerfile.spark

**Purpose:** Batch analytics for historical trend analysis and model evaluation

**Base Image:** `bitnami/spark:3.5.0`

**Key Components:**

-   Apache Spark 3.5.0 (distributed computing)
-   Spark SQL for querying TimescaleDB
-   Spark MLlib for model evaluation
-   PostgreSQL JDBC driver for database connectivity

**Runtime:**

-   Two services: `spark-master` (coordinator) and `spark-worker-1` (executor)
-   Master: Listens on port 7077 (cluster), 8086 (Web UI)
-   Worker: Executes tasks (2 cores, 1GB memory)
-   Depends on: Kafka healthy, TimescaleDB healthy
-   Health Check: HTTP GET to Spark Web UI (http://localhost:8086/)

**Data Processing Pipeline:**

```
TimescaleDB → Spark SQL → Historical Analysis & Aggregation → Results to DB
```

### 5. Dockerfile.database-init

**Purpose:** One-time database schema initialization and setup

**Base Image:** `python:3.10-slim`

**Key Components:**

-   PostgreSQL client tools
-   Python database drivers
-   SQL schema creation scripts

**Execution:**

-   Runs once on startup: `restart: "no"`
-   Environment: Database connection credentials
-   Depends on: TimescaleDB healthy
-   Executes: `scripts/00_init_database.py`
-   Creates: TimescaleDB hypertables, indexes, and time-series schema

**Output:**

```
TimescaleDB ← Schema Creation ← database-init Service
```

### 6. Dockerfile.grafana-init

**Purpose:** Automated Grafana dashboard provisioning and data source configuration

**Base Image:** `python:3.10-slim`

**Key Components:**

-   Grafana API client
-   Dashboard JSON templates
-   Data source provisioning

**Execution:**

-   Runs once on startup: `restart: "no"`
-   Depends on: Grafana healthy, database-init completed
-   Executes: `scripts/01_init_grafana.py`
-   Configures: TimescaleDB as data source
-   Provisions: Pre-built dashboards for monitoring

**Output:**

```
Grafana ← Dashboard & Data Source Configuration ← grafana-init Service
```

## Pre-built Images

### Kafka (confluentinc/cp-kafka:7.6.1)

-   KRaft mode (no Zookeeper required)
-   Single broker configuration
-   Dual listeners: Internal (29092) and External (9092)
-   Ports: 9092 (external), 29092 (internal)
-   Persistent volume: `kafka_data`

### TimescaleDB (timescale/timescaledb-ha:pg16)

-   PostgreSQL 16 with TimescaleDB extension
-   Time-series optimized data structures
-   Port: 5432
-   Credentials: `flead/password`
-   Database: `flead`
-   Persistent volume: `timescaledb_data`
-   Health Check: `pg_isready` command

### Grafana (grafana/grafana:11.0.0)

-   Web-based data visualization platform
-   Credentials: `admin/admin`
-   Port: 3001
-   Provisioning: Configured by grafana-init service
-   Data source: TimescaleDB

### Kafka UI (provectuslabs/kafka-ui:latest)

-   Web UI for Kafka cluster management
-   Topic monitoring and message inspection
-   Port: 8081
-   Depends on: Kafka healthy

## Networking

### Bridge Network: flead_network

All containers connected via Docker bridge network with built-in DNS resolution.

**Internal Service Discovery:**

-   `kafka:29092` - Kafka bootstrap server (internal)
-   `timescaledb:5432` - Database connection
-   `flink-jobmanager:6123` - Flink RPC
-   `spark-master:7077` - Spark cluster
-   `grafana:3000` - Grafana internal port

**External Port Mappings:**

-   Kafka: `localhost:9092` (producer/consumer from host)
-   TimescaleDB: `localhost:5432` (psql client from host)
-   Grafana: `localhost:3001` (http://localhost:3001)
-   Kafka UI: `localhost:8081` (http://localhost:8081)
-   Flink UI: `localhost:8161` (http://localhost:8161)
-   Spark UI: `localhost:8086` (http://localhost:8086)

## Startup Orchestration

### Service Dependencies (Execution Order)

```
1. kafka → (healthy)
2. timescaledb → (healthy)
3. kafka-ui → (kafka healthy)
4. grafana → (timescaledb healthy)
5. database-init → (timescaledb healthy)
6. grafana-init → (grafana healthy AND database-init completed)
7. flink-jobmanager → (kafka healthy)
8. flink-taskmanager → (flink-jobmanager healthy AND kafka healthy)
9. spark-master → (kafka healthy AND timescaledb healthy)
10. spark-worker-1 → (spark-master healthy)
11. kafka-producer → (kafka healthy AND database-init completed)
12. federated-aggregator → (kafka healthy AND timescaledb healthy AND database-init completed)
```

### Health Check Strategy

-   **service_healthy:** Waits for container health check to pass
-   **service_completed_successfully:** Waits for one-time init service to complete and exit

### Startup Command

```bash
docker-compose up -d
```

-   Creates network: `ost-2_flead_network`
-   Builds custom images (if not cached)
-   Starts services in dependency order
-   Total startup time: ~45-60 seconds

## Data Persistence

### Volumes

-   `kafka_data` - Kafka message log persistence
-   `timescaledb_data` - PostgreSQL data persistence
-   `flink_jobmanager_data` - Flink metadata
-   `flink_taskmanager_data` - Task execution state
-   `spark_master_data` - Spark cluster state
-   `spark_worker_data` - Worker execution state
-   `./models` - Federated learning models (host mount)
-   `./data/processed` - CSV data files (host mount, read-only)

## Resource Allocation

| Service           | CPU     | Memory | Purpose           |
| ----------------- | ------- | ------ | ----------------- |
| Flink JobManager  | -       | 1GB    | Scheduling        |
| Flink TaskManager | -       | 2GB    | Stream processing |
| Spark Master      | -       | -      | Coordination      |
| Spark Worker      | 2 cores | 1GB    | Batch processing  |
| Kafka             | -       | -      | Message broker    |
| TimescaleDB       | -       | -      | Database          |
| Grafana           | -       | -      | UI                |

## Monitoring & Logs

### Container Logs

```bash
docker-compose logs -f <service-name>
```

### Key Log Locations (Inside Containers)

-   Kafka Producer: `/logs/kafka_producer.log`
-   Aggregator: `/logs/federated_aggregation.log`
-   Flink: `/opt/flink/log`
-   Spark: `/opt/spark/work`

### Web Dashboards

-   Grafana: http://localhost:3001 (data visualization)
-   Kafka UI: http://localhost:8081 (message monitoring)
-   Flink UI: http://localhost:8161 (job monitoring)
-   Spark UI: http://localhost:8086 (task monitoring)

## Deployment Characteristics

-   **Zero Local Setup:** No local Python dependencies required
-   **Cross-Platform:** Identical behavior on Windows, macOS, Linux
-   **Reproducible:** Same images guarantee consistent behavior
-   **Scalable:** Easy to add more workers or change resource limits
-   **Isolated:** Services cannot interfere with host system
-   **Version Control:** All configurations in version control (docker-compose.yml)
-   **Self-Healing:** Restart policies ensure service recovery

## Stopping Services

```bash
docker-compose down          # Stop all services (keeps volumes)
docker-compose down -v       # Stop all services and remove volumes
```

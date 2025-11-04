# Federated Learning Platform for Edge IoT Data


**Key Features:**

-   Real-time streaming data processing with Apache Kafka
-   Distributed model training using Apache Flink
-   Federated model aggregation (FedAvg algorithm)
-   Time-series analytics with TimescaleDB and apache spark
-   Interactive visualization dashboards with Grafana
-   Support for 2000+ edge devices with statistical anomaly detection

![FLEAD architecture](/Architecture%20Diagrams/diagram4.jpg)

## Dataset

This platform uses the Edge-IIoTset dataset, which contains network traffic and IoT device telemetry data.

-   **Source**: [Edge-IIoTset on Kaggle](https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset)
-   **Preprocessing Notebook**: [Data Preprocessing](https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac)
-   **Features**: 60+ network traffic features including TCP, MQTT, DNS, and HTTP metrics
-   **Devices**: 2407 preprocessed device CSV files

## Prerequisites

Before running the platform, ensure you have the following installed:

-   **Docker Desktop** (version 20.10+)
-   **Docker Compose** (version 2.0+)
-   **Python** (version 3.8+)
-   **Git**

**Hardware Requirements:**

-   Minimum 8GB RAM (16GB recommended)
-   10GB available disk space
-   Multi-core processor (4+ cores recommended)

## Technology Stack

| Component         | Technology               | Purpose                          |
| ----------------- | ------------------------ | -------------------------------- |
| Stream Processing | Apache Flink 1.18        | Real-time local model training   |
| Message Broker    | Apache Kafka             | Data streaming and model updates |
| Batch Analytics   | Apache Spark             | Historical analysis              |
| Database          | TimescaleDB (PostgreSQL) | Time-series data storage         |
| Visualization     | Grafana 9.x              | Dashboard and monitoring         |
| Orchestration     | Docker Compose           | Service management               |

## Quick Start

### Running the Platform

### Running the Platform

Start all services using the startup script:

```batch
START.bat
```

This script will:

1. Initialize Docker containers for all services
2. Create necessary Kafka topics
3. Start the data streaming pipeline
4. Launch the Device Viewer Website at http://localhost:8082

To stop all services:

```batch
STOP.bat
```

### Service Endpoints

Once the platform is running, access the following interfaces:

| Service           | URL                   | Port | Description                            |
| ----------------- | --------------------- | ---- | -------------------------------------- |
| Device Viewer     | http://localhost:8082 | 8082 | Web interface for device visualization |
| Kafka UI          | http://localhost:8081 | 8081 | Kafka topics and message monitoring    |
| Grafana Dashboard | http://localhost:3001 | 3001 | Analytics and metrics visualization    |
| TimescaleDB       | localhost:5432        | 5432 | Database connection endpoint           |

### Database Configuration

**TimescaleDB Connection Details:**

```
Host: localhost
Port: 5432
Database: flead
Username: flead
Password: password
```

Use these credentials to connect external database clients or analytics tools.

## System Architecture

### Pipeline Execution Order

The platform executes the following pipeline stages sequentially:

```
1. Dataset Download
   └─> Downloads Edge-IIoTset dataset to data/raw/

2. Data Preprocessing
   └─> Cleans and normalizes data to data/processed/

3. Device Viewer
   └─> Launches web interface at http://localhost:8082

4. Data Streaming
   └─> Kafka streams data from randomly selected devices

5. Local Training (Flink)
   └─> Trains statistical models per device, stores in models/local/

6. Federated Aggregation
   └─> Aggregates local models into global model in models/global/

7. Analytics Pipeline
   └─> Batch and stream analytics, stores results in TimescaleDB

8. Visualization
   └─> Grafana dashboards display metrics and trends
```

### Component Architecture

**Data Flow:**

```
Edge Devices (CSV) → Kafka Producer → Kafka Topics → Flink (Local Training)
    ↓
Local Model Updates → Federated Aggregator → Global Model Updates
    ↓
TimescaleDB ← Spark Analytics ← Global/Local Models
    ↓
Grafana Dashboards
```

## Machine Learning Algorithms

### Local Training (Apache Flink)

Each device trains an independent statistical model for anomaly detection:

-   **Algorithm**: Z-score anomaly detection
-   **Model**: Rolling statistics (mean, standard deviation)
-   **Training Trigger**: Every 50 data points OR every 60 seconds (whichever occurs first)
-   **Output**: Local model statistics sent to Federated Server via Kafka

**Anomaly Detection Formula:**

```
Z-score = (X - μ) / σ
Anomaly if |Z-score| > threshold (typically 3)
```

### Global Aggregation (Federated Server)

The federated server aggregates local models using the FedAvg (Federated Averaging) algorithm:

-   **Algorithm**: FedAvg (Federated Averaging)
-   **Aggregation Formula**: `GlobalAccuracy = Σ(LocalAccuracy × Samples) / Σ(Samples)`
-   **Trigger**: After receiving 20 device model updates
-   **Output**: New global model version distributed to all devices

**Why Statistical Models?**

The platform uses statistical anomaly detection rather than neural networks for several reasons:

-   **Real-time Performance**: Instant computation without GPU requirements
-   **Lightweight**: Minimal memory footprint suitable for edge devices
-   **Scalability**: Efficiently handles 2000+ concurrent devices
-   **Proven Effectiveness**: Z-score method validated for IoT anomaly detection
-   **Interpretability**: Transparent decision-making for security applications

**Future Enhancement**: The architecture supports upgrading to neural network models (e.g., LSTM, autoencoders) if deeper pattern recognition is required.

## Project Structure

```
OST-2/
├── data/
│   ├── raw/                    # Original dataset files
│   └── processed/              # Preprocessed device CSV files (2407 devices)
├── scripts/
│   ├── 02_kafka_producer.py    # Kafka data streaming
│   ├── 03_flink_local_training.py  # Local model training
│   ├── 04_federated_aggregation.py # Global model aggregation
│   ├── 05_spark_analytics.py   # Batch and stream analytics
│   └── verify_platform.py      # Platform health check script
├── Implementation/
│   ├── services/               # Docker service configurations
│   ├── grafana/                # Grafana dashboard definitions
│   └── sql/                    # Database initialization scripts
├── frontend/                   # Device Viewer web application
├── models/
│   ├── local/                  # Per-device trained models
│   └── global/                 # Federated global models
├── notebooks/                  # Jupyter notebooks for analysis
├── config/                     # Configuration files
├── docker-compose.yml          # Docker orchestration
└── START.bat / STOP.bat        # Platform control scripts
```

## Verification and Troubleshooting

### Platform Health Check

Verify all components are running correctly:

```batch
python scripts\verify_platform.py
```

This script validates:

-   Docker container status (8 services)
-   Flink job execution (2 jobs expected)
-   Kafka topic availability (5 topics)
-   TimescaleDB table creation
-   Configuration correctness

**Expected Output**: All checks should pass with "PASS" status.

### Common Issues

**Issue: Docker containers fail to start**

-   Solution: Ensure Docker Desktop is running and has sufficient resources allocated
-   Check: `docker-compose ps` to view container status

**Issue: Flink jobs not running**

-   Solution: Check Flink logs with `docker logs flink-jobmanager`
-   Verify JARs are properly loaded in `/opt/flink/lib/`

**Issue: Kafka connection errors**

-   Solution: Wait 30-60 seconds after starting for Kafka broker initialization
-   Verify Kafka is ready: `docker logs kafka`

**Issue: No data in Grafana dashboards**

-   Solution: Ensure the Kafka producer is streaming data
-   Check database connection in Grafana settings
-   Verify TimescaleDB has data: Connect with provided credentials and query tables

### Viewing Logs

Access individual service logs:

```batch
docker logs <service-name>
```

Available services: `kafka`, `flink-jobmanager`, `flink-taskmanager`, `spark-master`, `timescaledb`, `grafana`

## Documentation

Additional documentation files:

-   `IMPLEMENTATION_GUIDE.md` - Detailed implementation steps and technical specifications
-   `FEDERATED_LEARNING_ARCHITECTURE.md` - In-depth federated learning concepts
-   `GRAFANA_SETUP_GUIDE.md` - Dashboard configuration and customization
-   `IMPLEMENTATION_REPORT.md` - System changes and configuration report

## License

This project is for educational and research purposes.

## Contact and Support

For issues, questions, or contributions, please refer to the project repository or contact the development team.

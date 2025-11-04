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

The platform uses **Statistical Online Learning** rather than traditional machine learning models. Each device maintains an independent statistical model that updates continuously in real-time.

#### Training Approach: Incremental Statistics

**Algorithm**: Z-score Anomaly Detection with Rolling Statistics

**How It Works:**

1. **Rolling Window**: Maintains last 100 data points per device
2. **Incremental Updates**: Calculates mean (μ) and standard deviation (σ) on each new data point
3. **No Batch Training**: Model updates happen instantly without accumulating training data
4. **Memory Efficient**: Only ~1KB per device (stores 100 values + 2 statistics)

**Model Structure:**

```python
{
    'mean': rolling average of last 100 values,
    'std': standard deviation of last 100 values,
    'samples': count since last model update,
    'version': model version counter
}
```

#### Training Triggers (Dual Condition)

The model is considered "trained" and sent to the Federated Server when **EITHER**:

-   **50 new data points** received since last update, **OR**
-   **60 seconds** elapsed since last update

This ensures both high-frequency devices and low-frequency devices get regular model updates.

#### Anomaly Detection Formula

**Z-Score Method:**

```
Z-score = |X - μ| / σ

Where:
- X = current sensor value
- μ = mean of last 100 values
- σ = standard deviation

Anomaly if |Z-score| > 2.5
Critical if |Z-score| > 5.0
```

**Example:**

-   Device mean: 45.3°C, std: 5.2°C
-   New reading: 62.8°C
-   Z-score: |62.8 - 45.3| / 5.2 = 3.37
-   **Result**: Anomaly detected (severity: warning)

#### Why Statistical Learning Instead of Neural Networks?

**Advantages:**

| Feature                | Statistical          | Neural Networks      |
| ---------------------- | -------------------- | -------------------- |
| **Training Time**      | Instant              | Hours/Days           |
| **Memory Usage**       | ~1KB per device      | MBs-GBs              |
| **Startup**            | Works immediately    | Needs training data  |
| **Scalability**        | 2000+ devices easily | Limited by resources |
| **Interpretability**   | Clear thresholds     | Black box            |
| **Edge Compatibility** | Perfect              | Requires GPU         |



#### Model Update Flow

```
1. New data arrives → Flink processes in real-time
2. Update rolling statistics (mean, std)
3. Check anomaly: if |Z-score| > 2.5 → Send to 'anomalies' topic
4. Check training trigger: if 50 rows OR 60 seconds
   → Package as local model → Send to 'local-model-updates' topic
5. Federated server aggregates these updates into global model
```

### Global Aggregation (Federated Server)

The federated server aggregates local models using the **FedAvg (Federated Averaging)** algorithm, adapted for statistical models rather than neural network weights.

#### Aggregation Process

**Algorithm**: Weighted Average based on sample count and accuracy

**Formula:**

```
GlobalAccuracy = Σ(LocalAccuracy_i × Samples_i) / Σ(Samples_i)

Where:
- LocalAccuracy_i = accuracy of device i's model
- Samples_i = number of samples device i processed
- Σ = sum across all devices in aggregation window
```

**Trigger Condition:**

-   Aggregates after receiving **20 device model updates**
-   Creates new global model version
-   Publishes to `global-model-updates` Kafka topic

**Example:**

```
Device 1: accuracy=0.85, samples=120
Device 2: accuracy=0.92, samples=80
Device 3: accuracy=0.78, samples=150

Global = (0.85×120 + 0.92×80 + 0.78×150) / (120+80+150)
       = (102 + 73.6 + 117) / 350
       = 0.836 (83.6% global accuracy)
```

#### Why FedAvg for Statistics?

**Traditional FedAvg**: Averages neural network weights across devices

**Adapted FedAvg**: Averages statistical measures (accuracy, performance metrics) weighted by sample count

**Benefits:**

-   Devices with more data have more influence (weighted by samples)
-   Global model represents collective behavior across all devices
-   Privacy-preserving: raw data never leaves devices
-   Handles heterogeneous devices (different data distributions)

#### Federated Learning Principle

**Privacy-Preserving Design:**

```
✅ SHARED: Model statistics (mean, std, accuracy)
❌ NEVER SHARED: Raw sensor readings, device locations, actual data values
```

Each device keeps its data local, only sharing learned patterns (statistics), which is the core principle of federated learning.

### Why Statistical Models?

The platform uses statistical anomaly detection rather than neural networks for several reasons:

**Technical Justification:**

-   **Real-time Performance**: Instant computation without GPU requirements - processes 1000s of events per second
-   **Lightweight**: Minimal memory footprint suitable for edge devices - works on Raspberry Pi
-   **Scalability**: Efficiently handles 2000+ concurrent devices without performance degradation
-   **Proven Effectiveness**: Z-score method is industry-standard for IoT anomaly detection (used by AWS, Azure IoT)
-   **Interpretability**: Transparent decision-making for security applications - auditable and explainable
-   **Zero Cold Start**: Works immediately with first data point - no training phase required
-   **Adaptive**: Automatically adjusts to new baseline as device behavior changes

**Future Enhancement**:

The architecture supports upgrading to neural network models (e.g., LSTM, autoencoders, transformers) if deeper pattern recognition is required:

-   **Phase 1** (Current): Statistical baseline for real-time detection
-   **Phase 2** (Future): Hybrid approach - statistics for real-time + neural networks for complex patterns
-   **Phase 3** (Future): Full deep learning with federated neural network training

Migration path is designed to maintain backward compatibility while adding advanced ML capabilities.

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

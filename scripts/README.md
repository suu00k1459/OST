# Scripts Organization Guide

## Overview

All scripts in this folder are now numbered to show the execution order. The system runs automatically via `START.bat` - no manual script execution needed.

---

## Script Execution Order

### Setup & Utilities (Prefix: 00\_)

These are supporting scripts, executed as needed, not part of main pipeline:

#### Stage 0: `data_preprocessor.py` (Optional but recommended)

- **Purpose**: Download the Edge-IIoTSet dataset from Kaggle, clean/normalize the dataset, generate the merged CSV and chunked preprocessed features to `data/processed/chunks/` for the pipeline.
- **When**: Run automatically by `START.bat` (or `pipeline_orchestrator.py`) if `data/processed/chunks/` is missing, or run manually when you want to regenerate data.
- **Prerequisite**: Place your Kaggle API token file at `./kaggle/kaggle.json` in the repository root. Docker Compose mounts `./kaggle` into `/root/.kaggle` inside the `data-preprocessor` and `jupyter-dev` containers. This is necessary for non-interactive Kaggle API access.
- **Manual Usage**: `python data_preprocessor.py` (ensure you have `kaggle.json` and required packages installed locally if not using containers)
- **Output**: Creates `data/raw/`, `data/processed/merged_data.csv`, `data/processed/preprocessor.pkl` (if joblib installed), and `data/processed/chunks/` containing `X_chunk_*.npz` and `y_chunk_*.npy` files.


#### `00_install_dependencies.py`

-   **Purpose**: Install required Python packages
-   **When**: Run once during initial setup
-   **Usage**: `python 00_install_dependencies.py`
-   **Output**: Installs all packages from requirements.txt

#### `00_model_manager.py`

-   **Purpose**: Manage federated models (load, save, versions)
-   **When**: Used by other services
-   **Functions**: Model persistence, versioning, loading

---

### Main Pipeline (Prefix: 01-05)

These run in strict order during normal operation:

#### Stage 1: `01_setup_kafka_topics.py`

-   **Purpose**: Create Kafka topics for data flow
-   **When**: Runs first, only once per startup
-   **Creates Topics**:
    -   `edge-iiot-stream` - Raw IoT data from devices
    -   `anomalies` - Detected anomalies from Flink (RCF-based)
    -   `local-model-updates` - Device model updates
    -   `global-model-updates` - Federated model aggregations
-   **Critical**: YES (pipeline cannot proceed without topics)
-   **Status**: Creates topics if they don't exist

#### Stage 2: `02_kafka_producer.py`

-   **Purpose**: Stream IoT data from CSV files to Kafka
-   **When**: Runs after topics are ready
-   **Configuration**:
    -   Source: `data/processed/` directory
    -   Mode: All available devices
    -   Rate: 5 events per second per device
    -   Repeat: Loops through data indefinitely
-   **Output**: Continuous stream to `edge-iiot-stream` topic
-   **Critical**: YES (supplies data to entire pipeline)
-   **Background**: YES (runs continuously)

#### Stage 3: `03_flink_local_training.py`

-   **Purpose**: Real-time local model training on edge devices
-   **When**: Runs after data streams are available
-   **Features**:
    -   Detects device anomalies in real-time
    -   Trains local models per device
    -   Publishes anomalies to `anomalies` topic
    -   Sends local models to `local-model-updates` topic
-   **Processing**: Streaming (continuous windows)
-   **Critical**: NO (optional but recommended)
-   **Background**: YES (runs continuously)

#### Stage 4: `04_federated_aggregation.py`

-   **Purpose**: Aggregate local models into global federated model
-   **When**: Runs after local models are being trained
-   **Features**:
    -   Collects local models from all devices
    -   Aggregates using FederatedAveraging algorithm
    -   Stores global model version in database
    -   Publishes to `global-model-updates` topic
-   **Frequency**: Periodic aggregation (every N batches)
-   **Critical**: NO (but increases system effectiveness)
-   **Background**: YES (runs continuously)

#### Stage 5: `05_spark_analytics_professional.py`

-   **Purpose**: Batch and stream analytics with global model evaluation
-   **When**: Runs after aggregation service is ready
-   **Three Main Functions**:

    **A. Batch Analysis**

    -   Daily aggregations of all data
    -   Statistical trends (avg, min, max, stddev)
    -   Device-level analytics
    -   Stores in `batch_analysis_results` table

    **B. Stream Analysis**

    -   Real-time 30-second windows
    -   Real-time 5-minute windows
    -   Statistical anomaly detection (complementary to Flink RCF)
    -   Stores in `stream_analysis_results` table

    **C. Model Evaluation**

    -   Loads global federated model
    -   Evaluates predictions against actual data
    -   Calculates model accuracy
    -   Stores in `model_evaluations` table

-   **Output Database**: TimescaleDB
-   **Tables Created**:

    -   `batch_analysis_results` - Daily stats
    -   `stream_analysis_results` - Real-time metrics
    -   `model_evaluations` - Model predictions and accuracy
    -   `dashboard_metrics` - Live metrics for Grafana

-   **Visualization**: Feeds Grafana dashboard
-   **Critical**: NO (but essential for monitoring)
-   **Background**: YES (runs continuously)

#### Stage 6: `06_setup_grafana.py`

-   **Purpose**: Automated Grafana dashboard configuration
-   **When**: Runs after all pipeline services are up
-   **Actions**:
    -   Creates TimescaleDB data source via Grafana API
    -   Creates "FLEAD - Federated Learning Monitoring" dashboard
    -   Configures 8 panels: stats, time-series graphs, and tables
    -   Sets 30-second auto-refresh
-   **Output**: Fully configured Grafana dashboard ready to use
-   **Manual Run**: `python scripts/06_setup_grafana.py`
-   **Critical**: NO (visualization only, not required for pipeline)
-   **Background**: NO (completes in ~1 second)

**Note**: The old manual Grafana setup process (documented in `GRAFANA.md`) is **deprecated**. The pipeline now automatically configures everything via API.

---

## How the Pipeline Works

### Data Flow Diagram

```
IoT Devices (CSV Data)
    |
    v
02_kafka_producer.py
    |
    v
Kafka Topics
    |
    +---> 03_flink_local_training.py
    |         |
    |         +---> anomalies topic
    |         +---> local-model-updates topic
    |
    v
TimescaleDB (raw data storage)
    |
    v
04_federated_aggregation.py
    |
    v
Global Model
    |
    v
05_spark_analytics_professional.py
    |
    +---> batch_analysis_results
    +---> stream_analysis_results
    +---> model_evaluations
    |
    v
Grafana Dashboard (Visualization)
```

---

## Running the System

### Automatic (Recommended)

```bash
# Windows
START.bat
```

This automatically:

1. Starts Docker containers (Kafka, TimescaleDB, Flink, Spark, Grafana)
2. Runs pipeline_orchestrator.py
3. Executes all scripts in correct order
4. Keeps all services running
Tip: Use the helper `scripts/cleanup_and_build.ps1` for safe cleanup and no-cache rebuilds.

Examples (PowerShell):

```powershell
# Cleanup, rebuild (no-cache) and do NOT start the stack
.\scripts\cleanup_and_build.ps1

# Cleanup, rebuild (no-cache) and start the stack
.\scripts\cleanup_and_build.ps1 -Start

# Cleanup, rebuild, and remove volumes (DESTRUCTIVE) + start
.\scripts\cleanup_and_build.ps1 -RemoveVolumes -Start
```

### Manual (Not Recommended)

```bash
# Do NOT do this - use START.bat instead
# Listed only for reference

cd scripts

# Step 1: Setup topics
python 01_setup_kafka_topics.py

# Step 2: Start producer (in background)
python 02_kafka_producer.py &

# Step 3: Start Flink training (in background)
python 03_flink_local_training.py &

# Step 4: Start aggregation (in background)
python 04_federated_aggregation.py &

# Step 5: Start analytics (in background)
python 05_spark_analytics_professional.py &
```

---

## File Dependencies

```
01_setup_kafka_topics.py
    (no dependencies)

02_kafka_producer.py
    depends on: 01_setup_kafka_topics.py
    requires: data/processed/ directory

03_flink_local_training.py
    depends on: 02_kafka_producer.py
    requires: Flink cluster running

04_federated_aggregation.py
    depends on: 03_flink_local_training.py
    requires: TimescaleDB, models directory

05_spark_analytics_professional.py
    depends on: 04_federated_aggregation.py
    requires: Spark cluster, TimescaleDB, global model
```

---

## Monitoring & Logs

All logs are stored in `../logs/` directory:

```
logs/
├── kafka_topics.log              # Topic creation
├── kafka_producer.log            # Data streaming
├── flink_training.log            # Local model training
├── federated_aggregation.log     # Model aggregation
└── spark_analytics.log           # Analytics processing
```

View logs in real-time:

```bash
# Windows PowerShell
Get-Content -Path ..\logs\kafka_producer.log -Wait

# Or use Docker
docker logs -f kafka_producer
```

---

## Troubleshooting

### Script Won't Start

1. Check Docker services are running: `docker-compose ps`
2. Check logs in `../logs/` directory
3. Verify Python packages installed: `pip list | grep -E "kafka|pyspark|tensorflow"`

### Data Not Flowing

1. Check Kafka topics exist: `docker exec kafka kafka-topics --bootstrap-server localhost:29092 --list`
2. Check producer is running: `docker logs kafka_producer`
3. Check Kafka has data: `docker exec kafka kafka-console-consumer --bootstrap-server localhost:29092 --topic edge-iiot-stream --from-beginning --max-messages 5`

### Analytics Not Showing

1. Wait 2-3 minutes for data to flow through pipeline
2. Check TimescaleDB tables: `docker exec timescaledb psql -U postgres -d flead_db -c "SELECT COUNT(*) FROM stream_analysis_results;"`
3. Check Grafana dashboard: http://localhost:3001 (admin/admin)

### Model Accuracy Low

1. Check global model loaded: Check logs in `spark_analytics.log`
2. Wait for more data: Model improves as it sees more patterns
3. Check model version: `docker exec timescaledb psql -U postgres -d flead_db -c "SELECT DISTINCT model_version FROM model_evaluations;"`

---

## Performance Tips

1. **Increase Data Rate**: Edit `02_kafka_producer.py`, change `rate` parameter (default: 5 events/sec)
2. **Adjust Batch Size**: Edit `05_spark_analytics_professional.py`, modify `BATCH_SIZE` constant
3. **Scale Devices**: Add more CSV files to `data/processed/` directory
4. **Monitoring**: Check system resources during peak loads

---

## Key Metrics Explained

### Batch Analysis Results

-   **avg_value**: Daily average across all devices
-   **min_value**: Minimum reading that day
-   **max_value**: Maximum reading that day
-   **stddev_value**: Standard deviation (variability)
-   **sample_count**: Number of data points

### Stream Analysis Results

-   **raw_value**: Latest device reading
-   **moving_avg_30s**: 30-second moving average
-   **moving_avg_5m**: 5-minute moving average
-   **anomaly_score**: Normalized anomaly score (0-1 scale, compatible with RCF)
-   **is_anomaly**: Boolean (true if anomaly detected)
-   **anomaly_confidence**: Confidence level (0-1)
-   **detection_method**: Algorithm used (e.g., 'spark_stddev', 'random_cut_forest')

### Model Evaluations

-   **model_accuracy**: Percentage of correct predictions
-   **prediction_result**: Model's predicted value
-   **actual_result**: Actual measured value
-   **is_correct**: Boolean (true if within tolerance)

---

## System Architecture

```
IoT Devices
    |
    v
STREAMING LAYER
  - Kafka (message broker)
  - Flink (local training)

    |
    v
AGGREGATION LAYER
  - Federated Aggregation
  - Global Model Manager

    |
    v
STORAGE LAYER
  - TimescaleDB (time-series data)
  - Model Repository

    |
    v
ANALYTICS LAYER
  - Spark Batch Processing
  - Spark Streaming
  - Model Evaluation

    |
    v
VISUALIZATION LAYER
  - Grafana Dashboard
  - Real-time metrics
```

---

## Quick Reference

| Script                               | Order | Type     | Critical | Background |
| ------------------------------------ | ----- | -------- | -------- | ---------- |
| `01_setup_kafka_topics.py`           | First | Setup    | YES      | NO         |
| `02_kafka_producer.py`               | 2nd   | Pipeline | YES      | YES        |
| `03_flink_local_training.py`         | 3rd   | Pipeline | NO       | YES        |
| `04_federated_aggregation.py`        | 4th   | Pipeline | NO       | YES        |
| `05_spark_analytics_professional.py` | 5th   | Pipeline | NO       | YES        |

---

## Contact & Support

For issues or questions:

1. Check logs in `../logs/` directory
2. Review this README for troubleshooting
3. Check Docker container status: `docker-compose ps`
4. Review START.bat for startup sequence

---

**Last Updated**: 2024
**System**: FLEAD (Federated Learning for Edge Anomaly Detection)
**Version**: 1.0
**Status**: Production Ready

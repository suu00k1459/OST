# Federated Learning Platform for Edge IoT Data



![FLEAD architecture](/Architecture%20Diagrams/diagram4.jpg)

**Key Features:**

-   Real-time streaming data processing with Apache Kafka
-   Distributed model training using Apache Flink
-   Federated model aggregation (FedAvg algorithm)
-   Time-series analytics with TimescaleDB and apache spark
-   Interactive visualization dashboards with Grafana
-   Support for 2000+ edge devices with statistical anomaly detection


**Core Technologies:**

-   Apache Kafka - Message streaming
-   Apache Flink - Real-time processing
-   Apache Spark - Batch analytics
-   TimescaleDB - Time-series database
-   Grafana - Visualization

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

## Stop the Project 

```batch
STOP.bat
```

## Access Points

| Service       | URL                   | Purpose         |
| ------------- | --------------------- | --------------- |
| Device Viewer | http://localhost:8082 | Browse devices  |
| Kafka UI      | http://localhost:8081 | Monitor streams |
| Grafana       | http://localhost:3001 | View dashboards |
| Flink UI      | http://localhost:8161 | Job monitoring  |

**Database:** localhost:5432 (user: flead, password: password)

## System Architecture

```
CSV Files → Kafka Producer → Kafka Topics
    ↓
Flink (Local Training) → Local Model Updates
    ↓
Federated Server (FedAvg) → Global Model
    ↓
Spark Analytics → TimescaleDB → Grafana
```

## Pipline Explanation

### 1. Data Streaming

Kafka producer streams 5 messages/second from randomly selected devices.

### 2. Local Training (Flink)

Each device trains using **Z-score anomaly detection**:

-   Maintains rolling window of 100 data points
-   Calculates mean (μ) and standard deviation (σ)
-   Detects anomaly if |Z-score| > 2.5

**Training trigger:** Every 50 rows OR every 60 seconds per device

**Z-score formula:**

```
Z = |X - μ| / σ
```

### 3. Federated Aggregation

Aggregates local models using FedAvg algorithm after receiving 20 device updates.

**Formula:**

```
Global Accuracy = Σ(Local Accuracy × Samples) / Σ(Samples)
```

### 4. Analytics & Visualization

Spark processes data and stores results in TimescaleDB. Grafana displays real-time dashboards with 5-second refresh.


| Component          | Processing Time   |
| ------------------ | ----------------- |
| Kafka streaming    | 5 messages/sec    |
| Flink processing   | <10ms per event   |
| Model training     | 50 rows or 60 sec |
| Global aggregation | Every 20 updates  |
| End-to-end latency | 5-15 seconds      |






-   **GRAFANA.md` - Dashboard setup guide**


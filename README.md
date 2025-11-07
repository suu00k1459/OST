# Federated Learning Platform for Edge IoT Data


## Project Architecture 
![FLEAD architecture](/project_architecture.png)
## Device Viewer
![Device Viewer](/Device%20Viewer.PNG)
## Pipline Moniter
![Pipline Moniter](/Moniter.PNG)

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



## Access Points

| Service       | URL                   | Purpose         |
| ------------- | --------------------- | --------------- |
| Device Viewer | http://localhost:8082 | Browse devices  |
| Kafka UI      | http://localhost:8081 | Monitor streams |
| Grafana       | http://localhost:3001 | View dashboards |
| Flink UI      | http://localhost:8161 | Job monitoring  |
| Monitoring     | http://localhost:5001 | Live system dashboard |

**Database:** localhost:5432 (user: flead, password: password)

### Grafana (Professional Dashboards)

-   **URL**: http://localhost:3001
-   **Login**: admin / admin
-   **Features**:
    -   Historical trends
    -   8 pre-configured panels
    -   Model accuracy graphs
    -   Device performance rankings
###  Monitoring dashboard

-   **URL**: http://localhost:5001
-   **Features**:
    -   Service logos (Kafka, Flink, TimescaleDB, Grafana)
    -   Real-time pipeline flow visualization
    -   Color-coded health indicators
    -   Recent activity feed
    -   Updates every 2 seconds


## Pipline Explanation
 - Kafka producer streams 5 messages/second from randomly selected devices.
 - Local Training (Flink) : Each device trains using Z-score anomaly detection 
 - Federated Aggregation : Aggregates local models using FedAvg algorithm after receiving 20 device updates.
 - Spark processes data and stores results in TimescaleDB. Grafana displays real-time dashboards with 5-second refresh
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

accuracy = min(0.95, 0.7 + (model['version'] * 0.02))

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




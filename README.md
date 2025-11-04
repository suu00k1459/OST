# Federated Learning Platform for Edge IoT Data

![FLEAD architecture](/Architecture%20Diagrams/diagram4.jpg)

## Dataset

-   **Source**: https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset
-   **Preprocessing**: https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac

## Run the platform

using the startup script:

```batch
./START.bat
```

This will launch the Device Viewer Website at http://localhost:8082

To stop all services:

```batch
./STOP.bat
```

---

### Access

**Device Viewer Website:**

-   **URL**: http://localhost:8082
-   **Port**: 8080
    **Kafka UI:**
-   **URL**: http://localhost:8081
-   **Port**: 8081
    **Grafana Dashboard:**
-   **URL**: http://localhost:3001
-   **Port**: 3001

---

## Device Viewer Website

The main interface for visualizing and exploring federated device data from Preprocessed CSV files.
![devive viewer website](/Device%20Viewer.PNG)

---

## TimeScale Database Config information :

Host: localhost
Port: 5432
Database: flead
Username: flead
Password: password

---

## System Architecture

### Pipeline Execution Order

```
1. Dataset Download
   └─> downloads dataset to data/raw/

2. Preprocessing
   └─> cleans data to data/processed/

3. Device Viewer
   └─> visualizes devices on http://localhost:8082

4. Data streaming :
   └─> using kafka Streaming

5. Local Training using Flink
   └─> trains models to models/local/

6. Federated Aggregation
   └─> creates global model in models/global/

7. Analytics 
   └─> Batch and Strean analytics and stores in TimescaleDB + generates report

8. Visualization
   └─>  dashboard  using graphana 
```
---


## Local Training (Flink):

 Algorithm: Z-score anomaly detection
 Model: Rolling statistics (mean, std)
 Training Trigger: Every 50 rows OR 60 seconds
 Update: Send statistics to Federated Server
## Global Aggregation (Federated Server):

 Algorithm: FedAvg (Federated Averaging)
 Formula: GlobalAccuracy = Σ(LocalAccuracy × Samples) / Σ(Samples)
 Trigger: After 20 device updates
 Output: New global model version

## Why Statistical (Not Neural Networks)?

 Fast: Real-time processing
 Lightweight: Works on edge devices
 Scalable: Handles 2000+ devices
 Effective: Z-score proven for IoT anomaly detection
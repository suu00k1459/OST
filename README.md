# Open source technologies for data science project

![FLEAD architecture](/Architecture%20Diagrams/diagram4.jpg)



## Data Set Link : 
**https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset**


## Data set preprocessing :
**https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac**


---

## Installation

###

1. **Install Python Dependencies**

    ```bash
    cd
    pip install -r requirements.txt
    ```

2. **Start TimescaleDB**

    ```bash
    docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=postgres timescale/timescaledb:latest-pg15
    ```

3. **Run Complete Pipeline**
    ```bash
    RUN_ALL.bat
    ```

---

## Pipeline Execution Order

```
1. Data Ingestion
   └─> downloads dataset to data/raw/

2. Preprocessing
   └─> cleans data to data/processed/

3. Local Training
   └─> trains models to models/local/

4. Federated Aggregation
   └─> creates global model in models/global/

5. Analytics (requires TimescaleDB)
   └─> stores in TimescaleDB + generates report

6. Visualization
   └─> creates dashboard PNG
```

---



### Backend Routes

```
GET  /api/status - System status
GET  /api/devices - List devices
GET  /api/devices/<id>/data - Device data
GET  /api/notebook/content - Notebook
POST /api/notebook/execute - Run notebook
GET  /api/dataset/raw - Raw files
GET  /api/dataset/processed - Processed files
GET  /api/kafka/status - Kafka status
POST /api/kafka/start - Start Kafka
POST /api/kafka/stop - Stop Kafka
GET  /api/docker/containers - Docker containers
POST /api/training/train-device/<id> - Train device
POST /api/training/train-all - Train all
GET  /api/training/device/<id>/model - Model architecture
POST /api/training/aggregate - Aggregate models
POST /api/pipeline/run - Run pipeline
```

### WebSocket Events

```
connect - Client connects
disconnect - Client disconnects
request_status - Status update
request_devices - Device list
status_update - Broadcast status
devices_update - Broadcast devices
device_trained - Training complete
device_training_start - Training started
training_progress - Progress update
notebook_output - Notebook logs
notebook_error - Notebook errors
notebook_complete - Notebook done
kafka_started - Kafka started
kafka_stopped - Kafka stopped
pipeline_* - Pipeline events
```



### 2. Start the System

```bash
./SETUP_FRONTEND.bat
```



### 3. Open in Browser

```
http://localhost:3000
```

---
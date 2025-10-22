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

## Run the project

1. Ensure TimescaleDB is running:

    ```bash
    docker ps | findstr timescaledb
    ```

2. Run complete pipeline:

    ```bash
    RUN_ALL.bat
    ```

---

## Stopping & Cleanup

### Stop Everything

```bash
STOP_ALL.bat
```

### Stop MongoDb Manualy

```bash
docker stop timescaledb
docker rm timescaledb
```

### Clean Generated Files

```bash
# Delete all outputs (optional)
rmdir /s /q data\raw
rmdir /s /q data\processed
rmdir /s /q models\local
rmdir /s /q models\global
rmdir /s /q outputs
```

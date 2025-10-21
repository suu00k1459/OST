# Open source technologies for data science project

![FLEAD architecture](/project_architecture.png)

## Team Assignments

### **SU YOUNG & ROBERT**

-   **Components**: Data Ingestion + Preprocessing + Analytics
-   **Scripts**:
    -   `scripts/1_data_ingestion.py`
    -   `scripts/1_preprocessing.py`
    -   `scripts/4_analytics.py`
-   **Tests**:
    -   `tests/1_TEST_DATA.bat`
    -   `tests/2_TEST_PREPROCESSING.bat`
    -   `tests/5_TEST_ANALYTICS.bat`

### **IMED & AMIR**

-   **Components**: Local Training + Federated Aggregation
-   **Scripts**:
    -   `scripts/2_local_training.py`
    -   `scripts/3_aggregation.py`
-   **Tests**:
    -   `tests/3_TEST_TRAINING.bat`
    -   `tests/4_TEST_AGGREGATION.bat`

### **YUSIF & AMIR**

-   **Components**: Visualization + Dashboard
-   **Scripts**:
    -   `scripts/5_visualization.py`
-   **Tests**:
    -   `tests/6_TEST_VISUALIZATION.bat`

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

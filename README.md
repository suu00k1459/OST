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

This will launch the Device Viewer Website at http://localhost:8080

To stop all services:

```batch
./STOP.bat
```

---

## Device Viewer Website

The main interface for visualizing and exploring federated device data from Preprocessed CSV files.
![devive viewer website](/Device%20Viewer.PNG)
### Features

-   Responsive card-based grid layout for device browsing
-   Device statistics: row count, column count, file size, modification date
-   Configurable pagination (12 devices per page by default)
-   Device detail pages with first 100 rows of data
-   Automatic handling of missing data with helpful guidance

### Access

-   **URL**: http://localhost:8080
-   **Port**: 8080


---

## System Architecture

### Pipeline Execution Order

```
1. Dataset Download
   └─> downloads dataset to data/raw/

2. Preprocessing
   └─> cleans data to data/processed/

3. Device Viewer
   └─> visualizes devices on http://localhost:8080

4. Data streaming : 
   └─> using kafka Streaming

5. Local Training using Flink
   └─> trains models to models/local/

6. Federated Aggregation 
   └─> creates global model in models/global/

7. Analytics (requires TimescaleDB)
   └─> stores in TimescaleDB + generates report

8. Visualization
   └─> creates dashboard PNG
```

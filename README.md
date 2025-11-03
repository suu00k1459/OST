# Federated Learning Platform for Edge IoT Data

![FLEAD architecture](/Architecture%20Diagrams/diagram4.jpg)

## Dataset

-   **Source**: https://www.kaggle.com/datasets/sibasispradhan/edge-iiotset-dataset
-   **Preprocessing**: https://www.kaggle.com/code/imedbenmadi/notebookf27d2cfbac

## Quick Start

Run the platform using the startup script:

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

The main interface for visualizing and exploring federated device data from CSV files.

### Features

-   Responsive card-based grid layout for device browsing
-   Device statistics: row count, column count, file size, modification date
-   Configurable pagination (12 devices per page by default)
-   Device detail pages with first 100 rows of data
-   Automatic handling of missing data with helpful guidance

### Access

-   **URL**: http://localhost:8080
-   **Port**: 8080

### Structure

```
website/
├── app.py                    Flask application
├── templates/
│   ├── base.html            Base layout
│   ├── index.html           Device listing page
│   └── device.html          Device detail page
├── static/
│   └── style.css            Dashboard styling
└── README.md                Detailed documentation
```

### Standalone Execution

If you prefer to run the website without START.bat:

```powershell
python .\website\app.py
```

---

## System Architecture

### Pipeline Execution Order

```
1. Data Ingestion
   └─> downloads dataset to data/raw/

2. Preprocessing
   └─> cleans data to data/processed/

3. Device Viewer
   └─> visualizes devices on http://localhost:8080

4. Local Training
   └─> trains models to models/local/

5. Federated Aggregation
   └─> creates global model in models/global/

6. Analytics (requires TimescaleDB)
   └─> stores in TimescaleDB + generates report

7. Visualization
   └─> creates dashboard PNG
```

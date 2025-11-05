# Grafana Setup Guide

## Step 1: Login

Open http://localhost:3001

-   Username: `admin`
-   Password: `admin`
-   Skip the password change

## Step 2: Add PostgreSQL Data Source

1. Click menu (☰) → **Connections** → **Data sources**
2. Click **"Add data source"**
3. Search for **PostgreSQL** and select it

## Step 3: Fill in Connection Details

Copy these values exactly:

**Name:**

```
FLEAD-TimescaleDB
```

**Connection:**

-   Host URL: `timescaledb:5432` ⚠️ **IMPORTANT: Use `timescaledb`, NOT `localhost`**
-   Database name: `flead`

**Authentication:**

-   Username: `flead`
-   Password: `password`

**TLS/SSL Mode:**

-   Select: `disable`

**PostgreSQL Options:**

-   Version: `12+`
-   TimescaleDB: ✅ Check this box

**Leave everything else as default.**

Click **"Save & test"** at the bottom.

You should see: ✅ "Database Connection OK"

## Step 4: Verify Data is Flowing

Before creating dashboards, verify the pipeline is working:

```powershell
# Check if services are running
docker ps

# Check local models count (should be > 0 and increasing)
docker exec -it timescaledb psql -U flead -d flead -c "SELECT COUNT(*) FROM local_models;"

# Check federated models count
docker exec -it timescaledb psql -U flead -d flead -c "SELECT COUNT(*) FROM federated_models;"

# Check latest updates
docker exec -it timescaledb psql -U flead -d flead -c "SELECT created_at FROM local_models ORDER BY created_at DESC LIMIT 1;"
```

**✅ Expected Results:**

-   local_models: Thousands of rows, constantly increasing
-   federated_models: Hundreds of rows, updates every ~20 seconds
-   Latest timestamp: Within the last minute

## Step 5: Create Dashboards

### Quick Method: Use Explore to Test Queries

1. Click **Explore** (compass icon on left sidebar)
2. Select your data source: `FLEAD-TimescaleDB`
3. Switch to **Code** mode (toggle at top right)
4. Test each query below

### Dashboard 1: Real-Time Monitoring

**Panel 1: Total Local Models Trained**

```sql
SELECT COUNT(*) as "Total Models"
FROM local_models;
```

**Panel 2: Total Federated Models**

```sql
SELECT COUNT(*) as "Global Models"
FROM federated_models;
```

**Panel 3: Active Devices (Last Hour)**

```sql
SELECT COUNT(DISTINCT device_id) as "Active Devices"
FROM local_models
WHERE created_at > NOW() - INTERVAL '1 hour';
```

**Panel 4: Latest Global Model Accuracy**

```sql
SELECT accuracy
FROM federated_models
ORDER BY created_at DESC
LIMIT 1;
```

**Panel 5: Model Training Over Time (Graph)**

```sql
SELECT
  created_at AS "time",
  COUNT(*) as "Models Trained"
FROM local_models
WHERE $__timeFilter(created_at)
GROUP BY time_bucket('1 minute', created_at)
ORDER BY 1;
```

_Note: Set visualization to "Time series" and format as "Graph"_

**Panel 6: Federated Aggregation Progress (Graph)**

```sql
SELECT
  created_at AS "time",
  aggregation_round as "Round",
  accuracy as "Accuracy",
  num_devices as "Devices"
FROM federated_models
WHERE $__timeFilter(created_at)
ORDER BY created_at;
```

**Panel 7: Average Accuracy by Device (Top 20)**

```sql
SELECT
  device_id,
  AVG(accuracy) as avg_accuracy,
  COUNT(*) as training_count
FROM local_models
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY device_id
ORDER BY avg_accuracy DESC
LIMIT 20;
```

**Panel 8: Model Training Rate (Per Minute)**

```sql
SELECT
  time_bucket('1 minute', created_at) AS "time",
  COUNT(*) as "Models/Min"
FROM local_models
WHERE $__timeFilter(created_at)
GROUP BY 1
ORDER BY 1;
```

### Dashboard 2: Device Analytics

**Panel 1: Device Training Distribution**

```sql
SELECT
  device_id,
  COUNT(*) as model_count,
  AVG(accuracy) as avg_accuracy,
  MAX(samples_processed) as max_samples
FROM local_models
WHERE created_at > NOW() - INTERVAL '6 hours'
GROUP BY device_id
ORDER BY model_count DESC
LIMIT 50;
```

**Panel 2: Samples Processed Over Time**

```sql
SELECT
  created_at AS "time",
  device_id,
  samples_processed
FROM local_models
WHERE $__timeFilter(created_at)
AND device_id IN (
  SELECT device_id FROM local_models
  GROUP BY device_id
  ORDER BY COUNT(*) DESC
  LIMIT 10
)
ORDER BY created_at;
```

**Panel 3: Model Version Distribution**

```sql
SELECT
  model_version,
  COUNT(*) as count
FROM local_models
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY model_version
ORDER BY model_version;
```

### Dashboard 3: Federated Learning Metrics

**Panel 1: Aggregation Timeline**

```sql
SELECT
  created_at AS "time",
  aggregation_round,
  num_devices,
  accuracy
FROM federated_models
WHERE $__timeFilter(created_at)
ORDER BY created_at;
```

**Panel 2: Global Model Accuracy Trend**

```sql
SELECT
  created_at AS "time",
  accuracy as "Global Model Accuracy"
FROM federated_models
WHERE $__timeFilter(created_at)
ORDER BY created_at;
```

_Set visualization to "Time series" with line chart_

**Panel 3: Participating Devices per Round**

```sql
SELECT
  created_at AS "time",
  num_devices as "Devices in Aggregation"
FROM federated_models
WHERE $__timeFilter(created_at)
ORDER BY created_at;
```

**Panel 4: Latest Federated Model Details**

```sql
SELECT
  id,
  global_version,
  aggregation_round,
  num_devices,
  ROUND(accuracy::numeric, 4) as accuracy,
  created_at
FROM federated_models
ORDER BY created_at DESC
LIMIT 10;
```

_Set visualization to "Table"_

## Step 6: Configure Dashboard Settings

For each dashboard:

1. **Time Range**: Set to "Last 1 hour" or "Last 6 hours"
2. **Refresh**: Click time picker → Set "Refresh every" to `10s` or `30s`
3. **Title**: Give your dashboard a meaningful name
4. **Save**: Click 💾 icon at top

## Useful Queries for Exploration

## Useful Queries for Exploration

**Count all local models:**

```sql
SELECT COUNT(*) as total_models FROM local_models;
```

**Count federated models:**

```sql
SELECT COUNT(*) as global_models FROM federated_models;
```

**Latest training activity:**

```sql
SELECT
  device_id,
  accuracy,
  samples_processed,
  created_at
FROM local_models
ORDER BY created_at DESC
LIMIT 20;
```

**Device performance comparison:**

```sql
SELECT
  device_id,
  COUNT(*) as training_count,
  AVG(accuracy) as avg_accuracy,
  MAX(model_version) as latest_version,
  SUM(samples_processed) as total_samples
FROM local_models
GROUP BY device_id
ORDER BY training_count DESC
LIMIT 20;
```

**Hourly training statistics:**

```sql
SELECT
  time_bucket('1 hour', created_at) as hour,
  COUNT(*) as models_trained,
  COUNT(DISTINCT device_id) as unique_devices,
  AVG(accuracy) as avg_accuracy
FROM local_models
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

**Global model evolution:**

```sql
SELECT
  global_version,
  aggregation_round,
  num_devices,
  accuracy,
  created_at
FROM federated_models
ORDER BY global_version DESC
LIMIT 20;
```

**Recent Spark analytics (if available):**

```sql
SELECT * FROM dashboard_metrics
ORDER BY updated_at DESC
LIMIT 10;
```

**Batch analysis results (if available):**

```sql
SELECT * FROM batch_analysis_results
ORDER BY created_at DESC
LIMIT 10;
```

## Troubleshooting

**"Database Connection Failed" or "dial tcp connection refused"?**

You're using `localhost:5432` instead of `timescaledb:5432`. Go back to your data source settings and change the Host URL to `timescaledb:5432`.

**Why `timescaledb` and not `localhost`?**

Because Grafana runs inside a Docker container. From inside the container, `localhost` means the container itself, not your computer. Use the Docker container name `timescaledb` to connect to the database container.

**"No data points" or empty graphs?**

1. **Check time range**: Make sure you're viewing "Last 1 hour" or "Last 6 hours", not a historical period
2. **Verify data exists**:
    ```powershell
    docker exec -it timescaledb psql -U flead -d flead -c "SELECT COUNT(*), MAX(created_at) FROM local_models;"
    ```
3. **Check if data is recent**: The MAX(created_at) should be within the last few minutes

**Queries return 0 results?**

1. **Start the pipeline if not running:**

    ```powershell
    cd "d:\OLD DESKTOP\Current Projects\OST-2"
    python scripts/pipeline_orchestrator.py
    ```

2. **Verify Flink job is running:**

    ```powershell
    docker exec flink-jobmanager flink list
    ```

    Should show "Local Training Job" with status RUNNING

3. **Check Kafka consumer groups:**

    ```powershell
    docker exec kafka kafka-consumer-groups --bootstrap-server kafka:29092 --list
    ```

    Should show "federated-aggregation" group

4. **Verify database tables exist:**
    ```powershell
    docker exec -it timescaledb psql -U flead -d flead -c "\dt"
    ```
    Should list: local_models, federated_models, dashboard_metrics, etc.

**Time series not showing as graph?**

1. Make sure your query has a column named `time` or uses `AS "time"`
2. Use `$__timeFilter(created_at)` in WHERE clause for time-series data
3. Set visualization type to "Time series" or "Graph"
4. In panel settings, set "Time field" to the correct column

**"relation does not exist" error?**

The table hasn't been created yet. This happens if:

-   Pipeline never ran successfully
-   Docker containers were recreated (data lost without volumes)

**Solution:**

```powershell
# Recreate tables manually
docker exec -it timescaledb psql -U flead -d flead

# Then paste these CREATE TABLE statements:
CREATE TABLE IF NOT EXISTS local_models (
    id SERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    model_version INT NOT NULL,
    global_version INT NOT NULL,
    accuracy FLOAT NOT NULL,
    samples_processed INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS federated_models (
    id SERIAL PRIMARY KEY,
    global_version INT NOT NULL,
    aggregation_round INT NOT NULL,
    num_devices INT NOT NULL,
    accuracy FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_local_models_created_at ON local_models(created_at);
CREATE INDEX IF NOT EXISTS idx_local_models_device_id ON local_models(device_id);
CREATE INDEX IF NOT EXISTS idx_federated_models_created_at ON federated_models(created_at);

# Exit psql
\q
```

**Dashboard shows old data?**

Refresh is not enabled. Click the time picker (top right) and set "Refresh every" to `10s` or `30s`.

## Current System Status (as of setup)

✅ **Working:**

-   Kafka Producer: Sending 73,000+ messages
-   Flink Training: Consuming and producing model updates
-   Federated Aggregation: Processing 175+ model updates (0 lag)
-   Database: 3,489 local models + 218 federated models
-   All Docker containers running

❌ **Not Working:**

-   Grafana dashboards: Need to be configured (that's what this guide fixes!)

## Performance Tips

1. **Use time_bucket for aggregations**: TimescaleDB's `time_bucket()` is optimized for time-series data
2. **Limit data range**: Always use `WHERE created_at > NOW() - INTERVAL '...'` to avoid scanning entire table
3. **Add indexes**: If queries are slow, add indexes on commonly filtered columns
4. **Use $\_\_timeFilter()**: This Grafana macro automatically filters by the dashboard time range

## Complete Dashboard JSON (Import Ready)

Copy this entire JSON and import it into Grafana (+ → Import → Paste JSON):

```json
{
    "dashboard": {
        "title": "FLEAD - Federated Learning Monitoring",
        "tags": ["flead", "federated-learning", "iot"],
        "timezone": "browser",
        "refresh": "30s",
        "time": {
            "from": "now-1h",
            "to": "now"
        },
        "panels": [
            {
                "id": 1,
                "title": "Total Local Models",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 0, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT COUNT(*) FROM local_models",
                        "format": "table"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": { "mode": "thresholds" },
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                { "value": null, "color": "green" },
                                { "value": 1000, "color": "yellow" },
                                { "value": 5000, "color": "red" }
                            ]
                        }
                    }
                }
            },
            {
                "id": 2,
                "title": "Global Models Created",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 6, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT COUNT(*) FROM federated_models",
                        "format": "table"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "color": { "mode": "palette-classic" }
                    }
                }
            },
            {
                "id": 3,
                "title": "Active Devices (Last Hour)",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 12, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT COUNT(DISTINCT device_id) FROM local_models WHERE created_at > NOW() - INTERVAL '1 hour'",
                        "format": "table"
                    }
                ]
            },
            {
                "id": 4,
                "title": "Latest Global Accuracy",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 18, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT ROUND(accuracy::numeric, 4) as accuracy FROM federated_models ORDER BY created_at DESC LIMIT 1",
                        "format": "table"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "min": 0,
                        "max": 1
                    }
                }
            },
            {
                "id": 5,
                "title": "Model Training Rate (Per Minute)",
                "type": "timeseries",
                "gridPos": { "h": 8, "w": 12, "x": 0, "y": 4 },
                "targets": [
                    {
                        "rawSql": "SELECT time_bucket('1 minute', created_at) AS time, COUNT(*) as value FROM local_models WHERE $__timeFilter(created_at) GROUP BY 1 ORDER BY 1",
                        "format": "time_series"
                    }
                ]
            },
            {
                "id": 6,
                "title": "Global Model Accuracy Trend",
                "type": "timeseries",
                "gridPos": { "h": 8, "w": 12, "x": 12, "y": 4 },
                "targets": [
                    {
                        "rawSql": "SELECT created_at AS time, accuracy as value FROM federated_models WHERE $__timeFilter(created_at) ORDER BY created_at",
                        "format": "time_series"
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "percentunit",
                        "min": 0,
                        "max": 1
                    }
                }
            },
            {
                "id": 7,
                "title": "Top Devices by Training Count",
                "type": "table",
                "gridPos": { "h": 8, "w": 12, "x": 0, "y": 12 },
                "targets": [
                    {
                        "rawSql": "SELECT device_id, COUNT(*) as training_count, ROUND(AVG(accuracy)::numeric, 4) as avg_accuracy, SUM(samples_processed) as total_samples FROM local_models WHERE created_at > NOW() - INTERVAL '1 hour' GROUP BY device_id ORDER BY training_count DESC LIMIT 20",
                        "format": "table"
                    }
                ]
            },
            {
                "id": 8,
                "title": "Recent Federated Models",
                "type": "table",
                "gridPos": { "h": 8, "w": 12, "x": 12, "y": 12 },
                "targets": [
                    {
                        "rawSql": "SELECT global_version, aggregation_round, num_devices, ROUND(accuracy::numeric, 4) as accuracy, created_at FROM federated_models ORDER BY created_at DESC LIMIT 15",
                        "format": "table"
                    }
                ]
            }
        ]
    }
}
```

## Quick Start Steps

1. **Open Grafana**: http://localhost:3001 (admin/admin)
2. **Add Data Source**: Connections → Data sources → Add PostgreSQL
    - Host: `timescaledb:5432`
    - Database: `flead`
    - User: `flead`
    - Password: `password`
3. **Import Dashboard**: + → Import → Paste the JSON above
4. **Set Refresh**: Top right → Refresh every 30s
5. **Done!** Watch your real-time federated learning data

---

## Summary

Your FLEAD pipeline is **fully functional**:

-   ✅ 3,489 local models trained
-   ✅ 218 global federated models aggregated
-   ✅ Real-time data flowing every second
-   ✅ All services operating correctly

This guide provides the Grafana configuration to visualize all that data! 🎉

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
grafana-postgresql-datasource
```

**Connection:**

-   Host URL: `localhost:5432`
-   Database name: `flead`

**Authentication:**

-   Username: `flead`
-   Password: `password`

**TLS/SSL Mode:**

-   Select: `disable`

**PostgreSQL Options:**

-   Version: `12+` (or `9.3`)
-   TimescaleDB: ✅ Check this box

**Leave everything else as default.**

Click **"Save & test"** at the bottom.

You should see: ✅ "Database Connection OK"

## Step 4: Test the Connection

1. Click **Explore** (compass icon on left sidebar)
2. Select your data source: `grafana-postgresql-datasource`
3. Run this query:

```sql
SELECT * FROM anomalies ORDER BY detected_at DESC LIMIT 10;
```

If you see data, it works!

## Step 5: Create a Dashboard

**Option 1: Quick Panel**

1. Click **+** → **Dashboard** → **Add new panel**
2. Paste any query from below
3. Click **Apply**

**Option 2: Import JSON**

1. Click **+** → **Import**
2. Paste the JSON at the end of this file
3. Select your data source
4. Click **Import**

## Useful Queries

**Count total anomalies:**

```sql
SELECT count(*) FROM anomalies;
```

**Anomalies in last hour:**

```sql
SELECT count(*) FROM anomalies
WHERE detected_at > NOW() - INTERVAL '1 hour';
```

**Anomalies over time (graph):**

```sql
SELECT
  detected_at AS time,
  count(*)
FROM anomalies
WHERE detected_at > NOW() - INTERVAL '1 hour'
GROUP BY time
ORDER BY time;
```

**Top 10 devices with most anomalies:**

```sql
SELECT
  device_id,
  count(*) as anomalies
FROM anomalies
GROUP BY device_id
ORDER BY count(*) DESC
LIMIT 10;
```

**Average model accuracy:**

```sql
SELECT avg(accuracy) FROM local_models;
```

**Global models:**

```sql
SELECT * FROM federated_models ORDER BY created_at DESC;
```

## Enable Auto-Refresh

1. Click the time picker (top right corner)
2. Set "Refresh every" to `10s`
3. Click **Apply**

## Troubleshooting

**"Database Connection Failed"?**

Try changing Host URL from `localhost:5432` to `timescaledb:5432`

**No data in queries?**

Check if services are running:

```powershell
docker ps
docker exec flink-jobmanager flink list
```

Check if database has data:

```powershell
docker exec -it timescaledb psql -U flead -d flead -c "SELECT COUNT(*) FROM anomalies;"
```

**Still not working?**

Wait 2-3 minutes after starting the platform for data to accumulate.

## Simple Dashboard JSON

Import this for a basic dashboard:

```json
{
    "dashboard": {
        "title": "FLEAD Monitoring",
        "refresh": "10s",
        "panels": [
            {
                "id": 1,
                "title": "Total Anomalies",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 0, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT count(*) FROM anomalies"
                    }
                ]
            },
            {
                "id": 2,
                "title": "Active Devices",
                "type": "stat",
                "gridPos": { "h": 4, "w": 6, "x": 6, "y": 0 },
                "targets": [
                    {
                        "rawSql": "SELECT count(DISTINCT device_id) FROM local_models"
                    }
                ]
            },
            {
                "id": 3,
                "title": "Recent Anomalies",
                "type": "table",
                "gridPos": { "h": 8, "w": 12, "x": 0, "y": 4 },
                "targets": [
                    {
                        "rawSql": "SELECT device_id, detected_at FROM anomalies ORDER BY detected_at DESC LIMIT 20"
                    }
                ]
            }
        ]
    }
}
```

---

Done! Your Grafana should now show data from the platform.

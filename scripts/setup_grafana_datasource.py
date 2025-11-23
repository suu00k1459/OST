"""
Setup Grafana PostgreSQL Data Source and Create Sample Dashboard
Automatically connects Grafana to TimescaleDB and creates an IoT data dashboard
"""

import requests
import json
import time
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

GRAFANA_URL = "http://localhost:3001"
GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "admin"

# Database connection details (must match TimescaleDB settings)
DB_HOST = "timescaledb"
DB_PORT = 5432
DB_NAME = "flead"
DB_USER = "flead"
DB_PASSWORD = "password"

def wait_for_grafana(max_attempts=30):
    """Wait for Grafana to be ready"""
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{GRAFANA_URL}/api/health", timeout=5)
            if response.status_code == 200:
                logger.info("✓ Grafana is ready")
                return True
        except requests.exceptions.ConnectionError:
            pass
        
        logger.info(f"Waiting for Grafana... ({attempt + 1}/{max_attempts})")
        time.sleep(2)
    
    logger.error("Grafana did not become ready in time")
    return False

def get_datasource_id_by_name(auth, name):
    """Get datasource ID by name"""
    try:
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources",
            auth=auth,
            timeout=5
        )
        response.raise_for_status()
        
        for ds in response.json():
            if ds.get('name') == name:
                return ds.get('id')
        return None
    except Exception as e:
        logger.warning(f"Error getting datasource: {e}")
        return None

def create_or_update_datasource(auth):
    """Create or update PostgreSQL data source"""
    logger.info("Setting up PostgreSQL data source...")
    
    # Check if datasource already exists
    existing_id = get_datasource_id_by_name(auth, "TimescaleDB")
    
    payload = {
        "name": "TimescaleDB",
        "type": "postgres",
        "access": "proxy",
        "url": f"{DB_HOST}:{DB_PORT}",
        "database": DB_NAME,
        "user": DB_USER,
        "secureJsonData": {
            "password": DB_PASSWORD
        },
        "jsonData": {
            "sslmode": "disable",
            "maxOpenConns": 0,
            "maxIdleConns": 2,
            "connMaxLifetime": 14400
        },
        "isDefault": True
    }
    
    if existing_id:
        # Update existing datasource
        logger.info(f"Updating existing datasource (ID: {existing_id})...")
        response = requests.put(
            f"{GRAFANA_URL}/api/datasources/{existing_id}",
            json=payload,
            auth=auth,
            timeout=10
        )
    else:
        # Create new datasource
        logger.info("Creating new datasource...")
        response = requests.post(
            f"{GRAFANA_URL}/api/datasources",
            json=payload,
            auth=auth,
            timeout=10
        )
    
    if response.status_code in [200, 201]:
        result = response.json()
        logger.info(f"✓ PostgreSQL datasource configured: {result.get('message', 'Success')}")
        return result.get('id') or existing_id
    else:
        logger.error(f"Failed to create datasource: {response.status_code}")
        logger.error(response.text)
        return None

def create_dashboard(auth, datasource_id):
    """Create sample IoT data dashboard"""
    logger.info("Creating sample dashboard...")
    
    dashboard = {
        "dashboard": {
            "title": "IoT Data Live",
            "tags": ["iot", "live", "realtime"],
            "timezone": "UTC",
            "panels": [
                {
                    "id": 1,
                    "title": "Total Records",
                    "type": "stat",
                    "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {
                            "refId": "A",
                            "rawSql": "SELECT COUNT(*) as count FROM iot_data",
                            "format": "table",
                            "datasourceId": datasource_id
                        }
                    ],
                    "options": {
                        "graphMode": "none",
                        "orientation": "auto",
                        "textMode": "auto",
                        "colorMode": "value",
                        "reduceOptions": {
                            "values": False,
                            "fields": "",
                            "calcs": ["lastNotNull"]
                        }
                    }
                },
                {
                    "id": 2,
                    "title": "Active Devices",
                    "type": "stat",
                    "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
                    "targets": [
                        {
                            "refId": "A",
                            "rawSql": "SELECT COUNT(DISTINCT device_id) as count FROM iot_data",
                            "format": "table",
                            "datasourceId": datasource_id
                        }
                    ],
                    "options": {
                        "graphMode": "none",
                        "orientation": "auto",
                        "textMode": "auto",
                        "colorMode": "value",
                        "reduceOptions": {
                            "values": False,
                            "fields": "",
                            "calcs": ["lastNotNull"]
                        }
                    }
                },
                {
                    "id": 3,
                    "title": "Data Over Time",
                    "type": "timeseries",
                    "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8},
                    "targets": [
                        {
                            "refId": "A",
                            "rawSql": "SELECT ts as time, COUNT(*) as count FROM iot_data GROUP BY time_bucket('10 seconds', ts) ORDER BY time",
                            "format": "timeseries",
                            "datasourceId": datasource_id
                        }
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "custom": {}
                        },
                        "overrides": []
                    },
                    "options": {
                        "legend": {"calcs": [], "displayMode": "list"},
                        "tooltip": {"mode": "multi"}
                    }
                },
                {
                    "id": 4,
                    "title": "Recent Device Activity",
                    "type": "table",
                    "gridPos": {"x": 0, "y": 12, "w": 12, "h": 8},
                    "targets": [
                        {
                            "refId": "A",
                            "rawSql": "SELECT device_id, COUNT(*) as count, MAX(ts) as last_seen FROM iot_data GROUP BY device_id ORDER BY last_seen DESC LIMIT 20",
                            "format": "table",
                            "datasourceId": datasource_id
                        }
                    ]
                }
            ],
            "refresh": "5s",
            "time": {
                "from": "now-1h",
                "to": "now"
            },
            "version": 0,
            "uid": "iot-live-dashboard"
        },
        "overwrite": True
    }
    
    response = requests.post(
        f"{GRAFANA_URL}/api/dashboards/db",
        json=dashboard,
        auth=auth,
        timeout=10
    )
    
    if response.status_code in [200, 201]:
        result = response.json()
        logger.info(f"✓ Dashboard created: {result.get('message', 'Success')}")
        logger.info(f"  Dashboard URL: {GRAFANA_URL}/d/{result.get('uid', 'iot-live-dashboard')}")
        return True
    else:
        logger.error(f"Failed to create dashboard: {response.status_code}")
        logger.error(response.text)
        return False

def main():
    logger.info("="*70)
    logger.info("Grafana Setup: PostgreSQL DataSource + IoT Dashboard")
    logger.info("="*70)
    
    # Wait for Grafana to be ready
    if not wait_for_grafana():
        logger.error("Grafana is not accessible")
        sys.exit(1)
    
    # Setup authentication
    auth = (GRAFANA_USER, GRAFANA_PASSWORD)
    
    try:
        # Create or update PostgreSQL datasource
        datasource_id = create_or_update_datasource(auth)
        if not datasource_id:
            logger.error("Failed to setup datasource")
            sys.exit(1)
        
        # Create dashboard
        if create_dashboard(auth, datasource_id):
            logger.info("="*70)
            logger.info("✓ Grafana setup complete!")
            logger.info(f"  Access Grafana: {GRAFANA_URL}")
            logger.info(f"  Username: {GRAFANA_USER}")
            logger.info(f"  Password: {GRAFANA_PASSWORD}")
            logger.info("="*70)
        else:
            logger.warning("Dashboard creation skipped, but datasource is ready")
            
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

"""
Grafana Datasource and Dashboard Setup
Automatically configures Grafana PostgreSQL datasource and creates sample dashboards
for IoT device monitoring and analytics
"""

import requests
import json
import time
import logging
import os
from typing import Dict, Optional, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment or defaults
GRAFANA_URL = os.getenv('GRAFANA_URL', 'http://localhost:3000')
GRAFANA_ADMIN_USER = os.getenv('GRAFANA_ADMIN_USER', 'admin')
GRAFANA_ADMIN_PASSWORD = os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin')

# Database configuration
DB_HOST = os.getenv('TIMESCALEDB_HOST', 'timescaledb')
DB_PORT = os.getenv('TIMESCALEDB_PORT', '5432')
DB_NAME = os.getenv('TIMESCALEDB_NAME', 'iot_db')
DB_USER = os.getenv('TIMESCALEDB_USER', 'iot_user')
DB_PASSWORD = os.getenv('TIMESCALEDB_PASSWORD', 'iot_password')

# Retry configuration
MAX_RETRIES = 30
RETRY_DELAY = 5


def wait_for_grafana() -> bool:
    """Wait for Grafana to be ready"""
    logger.info(f"Waiting for Grafana at {GRAFANA_URL}...")
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(f"{GRAFANA_URL}/api/health", timeout=5)
            if response.status_code == 200:
                logger.info("✓ Grafana is ready")
                return True
        except requests.exceptions.RequestException:
            pass
        
        if attempt < MAX_RETRIES - 1:
            logger.info(f"  Attempt {attempt + 1}/{MAX_RETRIES} - Grafana not ready yet, retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        else:
            logger.error(f"✗ Grafana did not respond after {MAX_RETRIES} attempts")
            return False
    
    return False


def get_grafana_auth_headers() -> Dict[str, str]:
    """Get authorization headers for Grafana API"""
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {get_or_create_api_token()}'
    }


def get_or_create_api_token() -> str:
    """Get existing API token or create a new one"""
    # Use basic auth to get token
    headers = {'Content-Type': 'application/json'}
    
    try:
        # Check for existing tokens
        response = requests.get(
            f"{GRAFANA_URL}/api/auth/keys",
            auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
            headers=headers
        )
        
        if response.status_code == 200:
            tokens = response.json()
            if tokens and len(tokens) > 0:
                return tokens[0]['key']
        
        # Create new API token if none exists
        token_data = {
            "name": "IOT Pipeline Token",
            "role": "Admin"
        }
        
        response = requests.post(
            f"{GRAFANA_URL}/api/auth/keys",
            auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
            headers=headers,
            json=token_data
        )
        
        if response.status_code == 200:
            return response.json()['key']
        else:
            logger.error(f"Failed to create API token: {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"Error getting API token: {e}")
        return None


def create_datasource() -> bool:
    """Create PostgreSQL datasource in Grafana"""
    logger.info("Creating PostgreSQL datasource...")
    
    datasource_payload = {
        "name": "TimescaleDB IoT",
        "type": "postgres",
        "url": f"{DB_HOST}:{DB_PORT}",
        "access": "proxy",
        "jsonData": {
            "postgresVersion": 13,
            "sslmode": "disable",
            "tlsSkipVerify": True
        },
        "secureJsonData": {
            "password": DB_PASSWORD
        },
        "database": DB_NAME,
        "user": DB_USER,
        "isDefault": True
    }
    
    try:
        response = requests.post(
            f"{GRAFANA_URL}/api/datasources",
            headers=get_grafana_auth_headers(),
            json=datasource_payload
        )
        
        if response.status_code in [200, 409]:  # 409 = already exists
            logger.info("✓ PostgreSQL datasource configured")
            return True
        else:
            logger.error(f"Failed to create datasource: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Error creating datasource: {e}")
        return False


def create_dashboard() -> bool:
    """Create sample dashboard with IoT monitoring panels"""
    logger.info("Creating monitoring dashboard...")
    
    dashboard = {
        "dashboard": {
            "title": "IoT Device Analytics",
            "description": "Real-time monitoring and analytics for IoT devices",
            "tags": ["iot", "monitoring", "realtime"],
            "timezone": "browser",
            "panels": [
                {
                    "id": 1,
                    "title": "Active Devices",
                    "type": "stat",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    "targets": [
                        {
                            "expr": "SELECT COUNT(DISTINCT device_id) as count FROM sensor_data WHERE timestamp > now() - interval '5 minutes'",
                            "format": "table",
                            "refId": "A"
                        }
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "color": {"mode": "thresholds"},
                            "mappings": [],
                            "thresholds": {
                                "mode": "absolute",
                                "steps": [
                                    {"color": "red", "value": None},
                                    {"color": "yellow", "value": 500},
                                    {"color": "green", "value": 1000}
                                ]
                            }
                        }
                    }
                },
                {
                    "id": 2,
                    "title": "Sensor Data Timeline",
                    "type": "timeseries",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                    "targets": [
                        {
                            "expr": "SELECT timestamp, device_id, value FROM sensor_data ORDER BY timestamp DESC LIMIT 1000",
                            "format": "timeseries",
                            "refId": "B"
                        }
                    ]
                },
                {
                    "id": 3,
                    "title": "Device Status Distribution",
                    "type": "piechart",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                    "targets": [
                        {
                            "expr": "SELECT status, COUNT(*) as count FROM devices GROUP BY status",
                            "format": "table",
                            "refId": "C"
                        }
                    ]
                },
                {
                    "id": 4,
                    "title": "Anomaly Detection Alerts",
                    "type": "table",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
                    "targets": [
                        {
                            "expr": "SELECT timestamp, device_id, anomaly_score FROM anomalies WHERE anomaly_score > 0.8 ORDER BY timestamp DESC LIMIT 100",
                            "format": "table",
                            "refId": "D"
                        }
                    ]
                }
            ],
            "refresh": "30s",
            "schemaVersion": 35,
            "version": 0
        }
    }
    
    try:
        response = requests.post(
            f"{GRAFANA_URL}/api/dashboards/db",
            headers=get_grafana_auth_headers(),
            json=dashboard
        )
        
        if response.status_code in [200, 412]:  # 412 = already exists
            logger.info("✓ Monitoring dashboard created")
            return True
        else:
            logger.error(f"Failed to create dashboard: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Error creating dashboard: {e}")
        return False


def verify_setup() -> bool:
    """Verify Grafana setup is complete"""
    logger.info("Verifying Grafana setup...")
    
    try:
        headers = get_grafana_auth_headers()
        
        # Check datasources
        response = requests.get(
            f"{GRAFANA_URL}/api/datasources",
            headers=headers
        )
        
        if response.status_code == 200:
            datasources = response.json()
            if any(ds['type'] == 'postgres' for ds in datasources):
                logger.info("✓ PostgreSQL datasource verified")
            else:
                logger.warning("⚠ No PostgreSQL datasource found")
                return False
        else:
            logger.error(f"Failed to retrieve datasources: {response.status_code}")
            return False
        
        # Check dashboards
        response = requests.get(
            f"{GRAFANA_URL}/api/search?query=IoT",
            headers=headers
        )
        
        if response.status_code == 200:
            dashboards = response.json()
            if any('IoT' in db.get('title', '') for db in dashboards):
                logger.info("✓ IoT dashboard verified")
            else:
                logger.warning("⚠ No IoT dashboard found")
        else:
            logger.error(f"Failed to retrieve dashboards: {response.status_code}")
        
        return True
    
    except Exception as e:
        logger.error(f"Error verifying setup: {e}")
        return False


def main():
    """Main setup orchestration"""
    logger.info("=" * 60)
    logger.info("GRAFANA DATASOURCE AND DASHBOARD SETUP")
    logger.info("=" * 60)
    
    # Wait for Grafana
    if not wait_for_grafana():
        logger.error("✗ Could not connect to Grafana")
        return False
    
    # Create datasource
    if not create_datasource():
        logger.error("✗ Failed to create datasource")
        return False
    
    time.sleep(2)
    
    # Create dashboard
    if not create_dashboard():
        logger.error("✗ Failed to create dashboard")
        return False
    
    time.sleep(2)
    
    # Verify setup
    if not verify_setup():
        logger.warning("⚠ Setup verification encountered issues")
        return False
    
    logger.info("=" * 60)
    logger.info("✓ GRAFANA SETUP COMPLETE")
    logger.info(f"  Access Grafana at: {GRAFANA_URL}")
    logger.info("=" * 60)
    
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

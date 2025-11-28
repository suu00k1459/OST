"""
Database Configuration Utility
Always use Docker service names so everything works inside/outside Docker.
"""

import os
from typing import Dict, Any


def get_db_config() -> Dict[str, Any]:
    """
    Always point to the Docker DB service hostname: timescaledb
    """
    return {
        "host": os.getenv("DB_HOST", "timescaledb"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "flead"),
        "user": os.getenv("DB_USER", "flead"),
        "password": os.getenv("DB_PASSWORD", "password"),
    }


def get_kafka_config() -> Dict[str, str]:
    """
    Always use Docker Kafka broker hostnames.
    """
    return {
        "bootstrap_servers": os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "kafka-broker-1:29092,"
            "kafka-broker-2:29093,"
            "kafka-broker-3:29094,"
            "kafka-broker-4:29095"
        )
    }


def get_grafana_config() -> Dict[str, str]:
    """
    Inside pipeline, Grafana is always accessed through docker service 'grafana'
    Dashboard is exposed on port 3001 externally but inside Docker it's 3000.
    """
    return {
        "url": os.getenv("GRAFANA_URL", "http://grafana:3000"),
        "user": os.getenv("GRAFANA_USER", "admin"),
        "password": os.getenv("GRAFANA_PASSWORD", "admin"),
    }


def print_config_info():
    print("Database Config:", get_db_config())
    print("Kafka Config:", get_kafka_config())
    print("Grafana Config:", get_grafana_config())


if __name__ == "__main__":
    print_config_info()

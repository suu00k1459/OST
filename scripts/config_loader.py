"""
Database Configuration Utility
Automatically detects if running inside Docker or locally
"""

import os
from typing import Dict

def get_db_config() -> Dict[str, any]:
    """
    Get database configuration based on environment
    
    Returns:
        dict: Database connection parameters
    """
    
    # Check if running inside Docker container
    is_docker = os.path.exists('/.dockerenv')
    
    if is_docker:
        # Inside Docker: use service names from docker-compose
        return {
            'host': os.getenv('DB_HOST', 'timescaledb'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'flead'),
            'user': os.getenv('DB_USER', 'flead'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }
    else:
        # Outside Docker: use localhost (assumes docker-compose up running)
        return {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'flead'),
            'user': os.getenv('DB_USER', 'flead'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }

def get_kafka_config() -> Dict[str, str]:
    """
    Get Kafka configuration based on environment
    
    Returns:
        dict: Kafka connection parameters
    """
    
    is_docker = os.path.exists('/.dockerenv')
    
    if is_docker:
        # Inside Docker: use service name
        return {
            'bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        }
    else:
        # Outside Docker: use localhost
        return {
            'bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        }

def get_grafana_config() -> Dict[str, str]:
    """
    Get Grafana configuration based on environment
    
    Returns:
        dict: Grafana connection parameters
    """
    
    is_docker = os.path.exists('/.dockerenv')
    
    if is_docker:
        # Inside Docker: use service name
        return {
            'url': os.getenv('GRAFANA_URL', 'http://grafana:3000'),
            'user': os.getenv('GRAFANA_USER', 'admin'),
            'password': os.getenv('GRAFANA_PASSWORD', 'admin')
        }
    else:
        # Outside Docker: use localhost
        return {
            'url': os.getenv('GRAFANA_URL', 'http://localhost:3001'),
            'user': os.getenv('GRAFANA_USER', 'admin'),
            'password': os.getenv('GRAFANA_PASSWORD', 'admin')
        }

def print_config_info():
    """Print current configuration (for debugging)"""
    is_docker = os.path.exists('/.dockerenv')
    print(f"Running in Docker: {is_docker}")
    print(f"Database Config: {get_db_config()}")
    print(f"Kafka Config: {get_kafka_config()}")
    print(f"Grafana Config: {get_grafana_config()}")

if __name__ == "__main__":
    print_config_info()

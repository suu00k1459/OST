"""
Real-time Monitoring Dashboard for FLEAD Pipeline
Provides HTTP API for pipeline health status and metrics
"""

import logging
import time
from flask import Flask, jsonify
from datetime import datetime
import psycopg2
from kafka import KafkaConsumer
import os
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'timescaledb'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'flead'),
    'user': os.getenv('DB_USER', 'flead'),
    'password': os.getenv('DB_PASSWORD', 'password')
}

KAFKA_BROKERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka-broker-1:29092,kafka-broker-2:29093,kafka-broker-3:29094,kafka-broker-4:29095').split(',')

# Global metrics
metrics = {
    'kafka_connected': False,
    'database_connected': False,
    'messages_count': 0,
    'last_update': None,
    'status': 'INITIALIZING'
}


def check_kafka_connection():
    """Check Kafka connectivity"""
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BROKERS,
            group_id='monitoring-dashboard',
            auto_offset_reset='latest',
            consumer_timeout_ms=2000
        )
        consumer.close()
        metrics['kafka_connected'] = True
        logger.info("✓ Kafka connected")
    except Exception as e:
        metrics['kafka_connected'] = False
        logger.error(f"✗ Kafka connection failed: {e}")


def check_database_connection():
    """Check database connectivity"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Get message count
        cursor.execute("SELECT COUNT(*) FROM iot_messages;")
        metrics['messages_count'] = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        metrics['database_connected'] = True
        logger.info(f"✓ Database connected ({metrics['messages_count']} messages)")
    except Exception as e:
        metrics['database_connected'] = False
        logger.error(f"✗ Database connection failed: {e}")


def health_check_loop():
    """Background thread for health checks"""
    while True:
        try:
            check_kafka_connection()
            check_database_connection()
            
            if metrics['kafka_connected'] and metrics['database_connected']:
                metrics['status'] = 'HEALTHY'
            elif metrics['kafka_connected'] or metrics['database_connected']:
                metrics['status'] = 'DEGRADED'
            else:
                metrics['status'] = 'UNHEALTHY'
            
            metrics['last_update'] = datetime.utcnow().isoformat()
        except Exception as e:
            logger.error(f"Health check error: {e}")
        
        time.sleep(10)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': metrics['status'],
        'kafka': 'connected' if metrics['kafka_connected'] else 'disconnected',
        'database': 'connected' if metrics['database_connected'] else 'disconnected',
        'timestamp': metrics['last_update']
    }), 200 if metrics['status'] == 'HEALTHY' else 503


@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Get pipeline metrics"""
    return jsonify({
        'status': metrics['status'],
        'kafka_connected': metrics['kafka_connected'],
        'database_connected': metrics['database_connected'],
        'messages_count': metrics['messages_count'],
        'last_update': metrics['last_update']
    })


@app.route('/', methods=['GET'])
def index():
    """Dashboard homepage"""
    return jsonify({
        'service': 'FLEAD Monitoring Dashboard',
        'version': '1.0',
        'endpoints': [
            '/health - Health status',
            '/metrics - Pipeline metrics',
            '/docs - API documentation'
        ]
    })


if __name__ == '__main__':
    # Start health check background thread
    health_thread = threading.Thread(target=health_check_loop, daemon=True)
    health_thread.start()
    
    logger.info("Starting Monitoring Dashboard...")
    app.run(host='0.0.0.0', port=5001, debug=False)

"""
Real-time Monitoring Dashboard for FLEAD Pipeline
Provides HTTP API for pipeline health status and metrics.
"""

import logging
import time
from datetime import datetime
import os
import threading

from flask import Flask, jsonify
import psycopg2
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------
# Configuration (overridable via env in docker-compose)
# ---------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "timescaledb"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "flead"),
    "user": os.getenv("DB_USER", "flead"),
    "password": os.getenv("DB_PASSWORD", "password"),
}

# Default uses PLAINTEXT 9092 on all 4 brokers; docker-compose will set env too
KAFKA_BROKERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka-broker-1:9092",
).split(",")

# Global metrics
metrics = {
    "kafka_connected": False,
    "database_connected": False,
    "messages_count": 0,
    "last_update": None,
    "status": "INITIALIZING",
}


# ---------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------
def check_kafka_connection() -> None:
    """Check Kafka connectivity (simple consumer with short internal retry)."""
    from kafka.errors import NoBrokersAvailable  # local import to avoid hard dependency if unused

    ok = False
    last_err: Exception | None = None

    for attempt in range(1, 4):  # quick 3 attempts
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BROKERS,
                group_id="monitoring-dashboard",
                auto_offset_reset="latest",
                consumer_timeout_ms=2000,
            )
            consumer.close()
            ok = True
            break
        except NoBrokersAvailable as e:
            last_err = e
            logger.warning(
                "Kafka not ready yet for monitoring-dashboard (attempt %d/3): %s",
                attempt,
                e,
            )
            time.sleep(1.0)
        except Exception as e:
            last_err = e
            logger.warning(
                "Unexpected error creating monitoring-dashboard consumer (attempt %d/3): %s",
                attempt,
                e,
            )
            break

    if ok:
        metrics["kafka_connected"] = True
        logger.info("✓ Kafka connected (%s)", ",".join(KAFKA_BROKERS))
    else:
        metrics["kafka_connected"] = False
        logger.error("✗ Kafka connection failed: %s", last_err)


def check_database_connection() -> None:
    """Check database connectivity and count rows in iot_data."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # IMPORTANT: use iot_data, not iot_messages
        cur.execute("SELECT COUNT(*) FROM iot_data;")
        metrics["messages_count"] = cur.fetchone()[0]

        cur.close()
        conn.close()
        metrics["database_connected"] = True
        logger.info(
            "✓ Database connected (%d rows in iot_data)",
            metrics["messages_count"],
        )
    except Exception as e:
        metrics["database_connected"] = False
        logger.error("✗ Database connection failed: %s", e)


def health_check_loop() -> None:
    """Background thread that refreshes health every 10s."""
    while True:
        try:
            check_kafka_connection()
            check_database_connection()

            if metrics["kafka_connected"] and metrics["database_connected"]:
                metrics["status"] = "HEALTHY"
            elif metrics["kafka_connected"] or metrics["database_connected"]:
                metrics["status"] = "DEGRADED"
            else:
                metrics["status"] = "UNHEALTHY"

            metrics["last_update"] = datetime.utcnow().isoformat()
        except Exception as e:
            logger.error("Health check error: %s", e)

        time.sleep(10)


# ---------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return (
        jsonify(
            {
                "status": metrics["status"],
                "kafka": "connected" if metrics["kafka_connected"] else "disconnected",
                "database": "connected"
                if metrics["database_connected"]
                else "disconnected",
                "timestamp": metrics["last_update"],
            }
        ),
        200 if metrics["status"] == "HEALTHY" else 503,
    )


@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Get pipeline metrics."""
    return jsonify(
        {
            "status": metrics["status"],
            "kafka_connected": metrics["kafka_connected"],
            "database_connected": metrics["database_connected"],
            "messages_count": metrics["messages_count"],
            "last_update": metrics["last_update"],
        }
    )


@app.route("/", methods=["GET"])
def index():
    """Dashboard homepage (simple JSON)."""
    return jsonify(
        {
            "service": "FLEAD Monitoring Dashboard",
            "version": "1.0",
            "endpoints": [
                "/health - Health status",
                "/metrics - Pipeline metrics",
            ],
        }
    )


if __name__ == "__main__":
    # Start health check background thread
    health_thread = threading.Thread(target=health_check_loop, daemon=True)
    health_thread.start()

    logger.info("Starting Monitoring Dashboard on 0.0.0.0:5001…")
    app.run(host="0.0.0.0", port=5001, debug=False)

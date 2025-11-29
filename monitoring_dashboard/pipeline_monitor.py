#!/usr/bin/env python3
"""
FLEAD Pipeline Live Monitor
Real-time visualization of the entire federated learning pipeline
Kafka → Flink → Federated Aggregation → TimescaleDB → Grafana
"""

from flask import Flask, render_template, jsonify
import psycopg2
import subprocess
import shutil
from datetime import datetime
import json
import os
import socket
import logging

# --------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("kafka").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# Flask app – in Docker we expect /app as WORKDIR and templates in /app/templates
# --------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder="/app/templates",
    static_folder="/app/static",
)

# --------------------------------------------------------------------
# Database configuration – uses env vars from docker-compose
# --------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "timescaledb"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "flead"),
    "user": os.getenv("DB_USER", "flead"),
    "password": os.getenv("DB_PASSWORD", "password"),
}

# Kafka bootstrap – same env as other services
KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka-broker-1:9092",
)

# --------------------------------------------------------------------
# Service definitions
# --------------------------------------------------------------------
TCP_SERVICES = {
    # Core Kafka broker (single)
    "kafka-broker-1": ("kafka-broker-1", 9092),

    # Storage
    "timescaledb": ("timescaledb", 5432),

    # Stream / batch engines
    "flink-jobmanager": ("flink-jobmanager", 8081),
    "spark-master": ("spark-master", 7077),

    # Visualization / UIs
    "grafana": ("grafana", 3000),
    "kafka-ui": ("kafka-ui", 8080),
    "device-viewer": ("device-viewer", 5000),
    "monitoring-dashboard": ("monitoring-dashboard", 5000),  # this app
}

# Logical Python services (conceptual; we infer state from DB)
LOGICAL_COMPONENTS = [
    "timescaledb-collector",
    "federated-aggregator",
    "spark-analytics",
]

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def get_db_connection():
    """Return TimescaleDB connection or None."""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        return None


def _tcp_check(host: str, port: int, timeout: float = 2.0) -> bool:
    """Simple TCP connection check – works inside Docker without docker CLI."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_service_tcp(service_name: str) -> str:
    """
    Check if a Docker service is reachable over TCP.
    Returns: 'running', 'stopped', or 'unknown'
    """
    endpoint = TCP_SERVICES.get(service_name)
    if endpoint is None:
        return "unknown"

    host, port = endpoint
    return "running" if _tcp_check(host, port) else "stopped"


def get_kafka_message_count(topic: str) -> int:
    """
    Get Kafka topic message count.

    Priority:
      1. kafka-python directly (inside container)
      2. docker exec + GetOffsetShell (host mode)

    On error: returns 0.
    """
    # Try kafka-python first
    try:
        from kafka import KafkaConsumer, TopicPartition  # type: ignore
    except ImportError:
        KafkaConsumer = None  # type: ignore
        TopicPartition = None  # type: ignore

    if KafkaConsumer is not None and TopicPartition is not None:
        try:
            bootstrap = [
                b.strip()
                for b in KAFKA_BOOTSTRAP_SERVERS.split(",")
                if b.strip()
            ]
            consumer = KafkaConsumer(
                bootstrap_servers=bootstrap,
                enable_auto_commit=False,
                group_id=None,
                consumer_timeout_ms=1000,
            )
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                consumer.close()
                return 0

            total = 0
            for p in partitions:
                tp = TopicPartition(topic, p)
                consumer.assign([tp])
                consumer.seek_to_end(tp)
                end = consumer.position(tp)
                total += end

            consumer.close()
            return total
        except Exception as e:
            logger.warning(
                f"Kafka (kafka-python) message count failed for {topic}: {e}"
            )

    # Fallback: docker exec (host only)
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "kafka-broker-1",
                "kafka-run-class",
                "kafka.tools.GetOffsetShell",
                "--broker-list",
                KAFKA_BOOTSTRAP_SERVERS,
                "--topic",
                topic,
                "--time",
                "-1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        total = 0
        for line in result.stdout.strip().split("\n"):
            if ":" in line:
                total += int(line.split(":")[-1])
        return total
    except Exception as e:
        logger.warning(
            f"Kafka message count (docker exec) failed for {topic}: {e}"
        )
        return 0


def get_flink_jobs():
    """
    Get Flink job status.

    Priority:
      1. Flink REST API (works from inside Docker network)
      2. docker exec + `flink list` (host mode fallback)
    """
    # --- Try REST API first (preferred in Docker) ---
    try:
        import requests  # type: ignore

        resp = requests.get(
            "http://flink-jobmanager:8081/jobs/overview",
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for job in data.get("jobs", []):
            jobs.append(
                {
                    "status": job.get("state", "UNKNOWN"),
                    "name": job.get("name", "Unknown"),
                }
            )
        return jobs
    except Exception as e:
        logger.info(
            f"Flink REST query failed or unavailable, "
            f"falling back to docker exec: {e}"
        )

    # --- Fallback: docker exec (host) ---
    try:
        result = subprocess.run(
            ["docker", "exec", "flink-jobmanager", "flink", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        jobs = []
        for line in result.stdout.split("\n"):
            if "RUNNING" in line or "FINISHED" in line:
                jobs.append(
                    {
                        "status": "RUNNING" if "RUNNING" in line else "FINISHED",
                        "name": line.split(":", 1)[-1].strip()
                        if ":" in line
                        else "Unknown",
                    }
                )
        return jobs
    except Exception as e:
        logger.info(f"Flink job query (docker exec) skipped/failed: {e}")
        return []


def _empty_db_stats():
    """Default DB stats structure so UI never sees None."""
    return {
        "local_models": {
            "total": 0,
            "last_minute": 0,
            "last_5min": 0,
            "latest": None,
        },
        "federated_models": {
            "total": 0,
            "last_minute": 0,
            "last_5min": 0,
            "latest": None,
        },
        "dashboard_metrics": {
            "total": 0,
            "last_minute": 0,
            "last_5min": 0,
            "latest": None,
        },
    }


def get_database_stats():
    """Get database statistics from TimescaleDB (or safe zeros on error)."""
    conn = get_db_connection()
    if not conn:
        return _empty_db_stats()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    'local_models' AS table_name,
                    COUNT(*) AS total_records,
                    COUNT(*) FILTER (
                        WHERE created_at > NOW() - INTERVAL '1 minute'
                    ) AS last_minute,
                    COUNT(*) FILTER (
                        WHERE created_at > NOW() - INTERVAL '5 minutes'
                    ) AS last_5min,
                    MAX(created_at) AS latest_record
                FROM local_models
                UNION ALL
                SELECT 
                    'federated_models',
                    COUNT(*),
                    COUNT(*) FILTER (
                        WHERE created_at > NOW() - INTERVAL '1 minute'
                    ),
                    COUNT(*) FILTER (
                        WHERE created_at > NOW() - INTERVAL '5 minutes'
                    ),
                    MAX(created_at)
                FROM federated_models
                UNION ALL
                -- Dashboard metrics = IoT traffic stats from iot_data
                SELECT 
                    'dashboard_metrics',
                    COUNT(*),
                    COUNT(*) FILTER (
                        WHERE ts > NOW() - INTERVAL '1 minute'
                    ),
                    COUNT(*) FILTER (
                        WHERE ts > NOW() - INTERVAL '5 minutes'
                    ),
                    MAX(ts)
                FROM iot_data;
                """
            )

            rows = cur.fetchall()
            stats = _empty_db_stats()
            for row in rows:
                name = row[0]
                stats[name] = {
                    "total": row[1],
                    "last_minute": row[2],
                    "last_5min": row[3],
                    "latest": row[4].isoformat() if row[4] else None,
                }
            return stats
    except Exception as e:
        logger.error(f"Database stats query failed: {e}")
        return _empty_db_stats()
    finally:
        conn.close()

def get_recent_models():
    """Get recent local model training activity."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    device_id,
                    model_version,
                    global_version,
                    accuracy,
                    samples_processed,
                    created_at
                FROM local_models
                ORDER BY created_at DESC
                LIMIT 10;
                """
            )

            models = []
            for row in cur.fetchall():
                models.append(
                    {
                        "device_id": row[0],
                        "model_version": row[1],
                        "global_version": row[2],
                        "accuracy": float(row[3]),
                        "samples": row[4],
                        "timestamp": row[5].isoformat(),
                    }
                )
            return models
    except Exception as e:
        logger.error(f"Recent models query failed: {e}")
        return []
    finally:
        conn.close()


def get_python_processes_host():
    """
    (Host-only) Get running Python pipeline processes on the Windows host.

    Inside the Docker container this will just return [] because
    PowerShell won't be available.
    """
    try:
        # Check if powershell is available before trying to run it
        if shutil.which("powershell") is None:
            return []

        result = subprocess.run(
            [
                "powershell",
                "-Command",
                "Get-Process python | "
                "Select-Object Id, @{Name='CommandLine';Expression={"
                "(Get-WmiObject Win32_Process -Filter \"ProcessId=$($_.Id)\").CommandLine"
                "}} | Where-Object { $_.CommandLine -like '*scripts*' } | ConvertTo-Json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not result.stdout.strip():
            return []

        processes_raw = json.loads(result.stdout)
        if isinstance(processes_raw, dict):
            processes_raw = [processes_raw]

        processes = []
        for proc in processes_raw:
            cmd = proc.get("CommandLine", "") or ""
            if "kafka_producer" in cmd:
                processes.append(
                    {"name": "Kafka Producer", "pid": proc["Id"], "status": "running"}
                )
            elif "federated_aggregation" in cmd:
                processes.append(
                    {
                        "name": "Federated Aggregation",
                        "pid": proc["Id"],
                        "status": "running",
                    }
                )
            elif "spark_analytics" in cmd:
                processes.append(
                    {"name": "Spark Analytics", "pid": proc["Id"], "status": "running"}
                )
        return processes
    except Exception as e:
        logger.info(
            f"Process check skipped/failed (likely inside Docker): {e}"
        )
        return []


# --------------------------------------------------------------------
# Flask routes
# --------------------------------------------------------------------
@app.route("/")
def index():
    """Main dashboard page."""
    return render_template("pipeline_monitor.html")


@app.route("/api/status")
def get_status():
    """Get complete pipeline status (JSON for the dashboard)."""

    # 1) Container-level service health via TCP
    docker_services = {
        name: check_service_tcp(name) for name in TCP_SERVICES.keys()
    }

    # 2) Database-driven logical health (collector / aggregator / analytics)
    db_stats = get_database_stats()

    # Timescaledb collector: if we've ingested ANY iot/local models, mark running
    iot_count = 0
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM iot_data;")
                iot_count = cur.fetchone()[0]
        except Exception as e:
            logger.info(f"iot_data count check failed: {e}")
        finally:
            conn.close()

    if iot_count > 0 or db_stats["local_models"]["total"] > 0:
        docker_services["timescaledb-collector"] = "running"
    else:
        docker_services["timescaledb-collector"] = "unknown"

    # Federated aggregator: look at federated_models table
    if db_stats["federated_models"]["total"] > 0:
        docker_services["federated-aggregator"] = "running"
    else:
        docker_services["federated-aggregator"] = "unknown"
        
    # Spark analytics: treat as running whenever spark-master is up
    spark_status = "running" if docker_services.get("spark-master") == "running" else "unknown"
    docker_services["spark-analytics"] = spark_status

    # 3) Kafka topic stats
    kafka_stats = {
        "edge-iiot-stream": get_kafka_message_count("edge-iiot-stream"),
        "local-model-updates": get_kafka_message_count("local-model-updates"),
        "global-model-updates": get_kafka_message_count("global-model-updates"),
    }

    # 4) Flink jobs
    flink_jobs = get_flink_jobs()

    # 5) Recent model activity
    recent_models = get_recent_models()

    # 6) Python “services”
    host_python = get_python_processes_host()
    if host_python:
        python_processes = host_python
    else:
        python_processes = []
        for comp_name, display_name in [
            ("timescaledb-collector", "TimescaleDB Collector"),
            ("federated-aggregator", "Federated Aggregator"),
            ("spark-analytics", "Spark Analytics"),
        ]:
            if docker_services.get(comp_name) == "running":
                python_processes.append(
                    {"name": display_name, "pid": 0, "status": "running"}
                )

    # ----------------- HEALTH LOGIC -----------------
    has_kafka_flow = kafka_stats["edge-iiot-stream"] > 0
    has_local_models = db_stats["local_models"]["total"] > 0
    has_global_models = db_stats["federated_models"]["total"] > 0
    collector_ok = docker_services.get("timescaledb-collector") == "running"
    aggregator_ok = docker_services.get("federated-aggregator") == "running"

    # Spark analytics is nice-to-have, not required for "healthy"
    analytics_ok = spark_status == "running"

    core_signals = [
        has_kafka_flow,
        has_local_models,
        has_global_models,
        collector_ok,
        aggregator_ok,
    ]

    if all(core_signals):
        pipeline_health = "healthy"
    elif any(core_signals):
        pipeline_health = "degraded"
    else:
        pipeline_health = "unknown"
    # ---------------------------------------------------

    return jsonify(
        {
            "timestamp": datetime.now().isoformat(),
            "docker_services": docker_services,
            "kafka": kafka_stats,
            "flink": flink_jobs,
            "database": db_stats,
            "recent_models": recent_models,
            "python_processes": python_processes,
            "pipeline_health": pipeline_health,
        }
    )


@app.route("/api/health")
def health_check():
    """Quick health check endpoint."""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# --------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" FLEAD Pipeline Monitor Starting...")
    print("=" * 70)
    print("[DASHBOARD] http://localhost:5001")
    print("[UPDATE] Real-time updates every 2 seconds")
    print("[MONITORING] Kafka → Flink → Database → Grafana")
    print("=" * 70)
    # In the container we listen on 0.0.0.0:5000 and docker-compose maps 5001:5000
    app.run(host="0.0.0.0", port=5000, debug=False)

"""
Simple Kafka to TimescaleDB Collector
Directly reads IoT data from Kafka and writes to database for Grafana visualization.
Bypasses Flink/Spark complexity - just collects and stores real-time data.

Topic: edge-iiot-stream
Table: iot_data(ts, device_id, value, label)
"""

import json
import logging
import time
from datetime import datetime
import sys

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Configuration (inside Docker: hosts are service names)
# ---------------------------------------------------------------------

# Multi-broker cluster – PLAINTEXT ports (must match docker-compose)
KAFKA_BROKERS = [
    "kafka-broker-1:9092",
    "kafka-broker-2:9092",
    "kafka-broker-3:9092",
    "kafka-broker-4:9092",
]
KAFKA_TOPIC = "edge-iiot-stream"
GROUP_ID = "timescaledb-collector"

# Database (matches docker-compose + 00_init_database.py)
DB_HOST = "timescaledb"
DB_PORT = 5432
DB_NAME = "flead"
DB_USER = "flead"
DB_PASSWORD = "password"

# Batch behaviour
BATCH_SIZE = 1000
INSERT_INTERVAL_SECONDS = 10


class KafkaToTimescaleDB:
    """Collect Kafka data and write to TimescaleDB."""

    def __init__(self):
        self.kafka_consumer = None
        self.db_conn = None
        self.batch = []
        self.last_insert_time = time.time()
        self.total_messages = 0
        self.total_inserts = 0

    # --------------------------------------------------------------
    # Connections
    # --------------------------------------------------------------
    def connect_kafka(self) -> bool:
        """Connect to Kafka with retries."""
        max_retries = 30
        delay = 5

        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                self.kafka_consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BROKERS,
                    group_id=GROUP_ID,
                    auto_offset_reset="earliest",
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=10000,
                    max_poll_records=500,
                    connections_max_idle_ms=540000,
                )
                logger.info(
                    "✓ Connected to Kafka brokers: %s",
                    ", ".join(KAFKA_BROKERS),
                )
                return True
            except NoBrokersAvailable as e:
                last_err = e
                logger.warning(
                    "Kafka not ready yet for timescaledb-collector "
                    "(attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    e,
                )
                time.sleep(delay)
            except Exception as e:
                last_err = e
                logger.warning(
                    "Error connecting to Kafka (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    e,
                )
                time.sleep(delay)

        logger.error(
            "✗ Failed to connect to Kafka after %d attempts: %s",
            max_retries,
            last_err,
        )
        return False

    def connect_db(self) -> bool:
        """Connect to TimescaleDB with retries."""
        max_retries = 5
        delay = 5

        for attempt in range(max_retries):
            try:
                self.db_conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    database=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    connect_timeout=10,
                )
                logger.info(
                    "✓ Connected to TimescaleDB: %s:%s/%s",
                    DB_HOST,
                    DB_PORT,
                    DB_NAME,
                )
                return True
            except Exception as e:
                logger.warning(
                    "DB connection attempt %d/%d failed: %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    logger.info("Retrying in %ds…", delay)
                    time.sleep(delay)
                else:
                    logger.error(
                        "✗ Failed to connect to database after %d attempts",
                        max_retries,
                    )
                    return False

    # --------------------------------------------------------------
    # Schema
    # --------------------------------------------------------------
    def create_tables(self) -> bool:
        """
        Ensure iot_data and dashboard_metrics tables exist (idempotent).
        """
        try:
            cur = self.db_conn.cursor()

            # iot_data for raw sensor events
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS iot_data (
                    ts        TIMESTAMPTZ NOT NULL,
                    device_id TEXT        NOT NULL,
                    value     DOUBLE PRECISION,
                    label     INT
                );

                SELECT create_hypertable('iot_data', 'ts', if_not_exists => TRUE);

                CREATE INDEX IF NOT EXISTS idx_iot_data_device_ts
                    ON iot_data (device_id, ts);
                """
            )

            # NEW: dashboard_metrics snapshot table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_metrics (
                    id BIGSERIAL PRIMARY KEY,
                    updated_at           TIMESTAMPTZ NOT NULL,
                    total_messages       BIGINT,
                    messages_last_minute BIGINT,
                    messages_last_5min   BIGINT
                );

                SELECT create_hypertable(
                    'dashboard_metrics',
                    'updated_at',
                    if_not_exists => TRUE
                );
                """
            )

            self.db_conn.commit()
            logger.info("✓ iot_data & dashboard_metrics tables ready")
            cur.close()
            return True
        except Exception as e:
            logger.error("✗ Failed to create tables: %s", e)
            self.db_conn.rollback()
            return False

    # --------------------------------------------------------------
    # Dashboard metrics snapshots
    # --------------------------------------------------------------
    def write_dashboard_snapshot(self) -> None:
        """
        Compute a small snapshot of the current stream load and store
        it in dashboard_metrics. Called after each batch insert.
        """
        try:
            cur = self.db_conn.cursor()

            # Total messages ever ingested
            cur.execute("SELECT COUNT(*) FROM iot_data;")
            total_messages = cur.fetchone()[0] or 0

            # Activity in last 1 minute
            cur.execute(
                """
                SELECT COUNT(*)
                FROM iot_data
                WHERE ts > NOW() - INTERVAL '1 minute';
                """
            )
            last_minute = cur.fetchone()[0] or 0

            # Activity in last 5 minutes
            cur.execute(
                """
                SELECT COUNT(*)
                FROM iot_data
                WHERE ts > NOW() - INTERVAL '5 minutes';
                """
            )
            last_5min = cur.fetchone()[0] or 0

            cur.execute(
                """
                INSERT INTO dashboard_metrics (
                    updated_at,
                    total_messages,
                    messages_last_minute,
                    messages_last_5min
                )
                VALUES (NOW(), %s, %s, %s);
                """,
                (total_messages, last_minute, last_5min),
            )

            logger.debug(
                "Dashboard snapshot written: total=%s, 1m=%s, 5m=%s",
                total_messages,
                last_minute,
                last_5min,
            )
            cur.close()

        except Exception as e:
            logger.error("✗ Failed to write dashboard snapshot: %s", e)
            # don't raise; we don't want to kill the collector because of metrics only

    # --------------------------------------------------------------
    # Insertion
    # --------------------------------------------------------------
    def insert_batch(self) -> None:
        """Insert current batch into iot_data and update dashboard_metrics."""
        if not self.batch:
            return

        try:
            cur = self.db_conn.cursor()

            data_tuples = []
            for msg in self.batch:
                ts_raw = msg.get("timestamp")
                if isinstance(ts_raw, str):
                    try:
                        ts = datetime.fromisoformat(ts_raw)
                    except Exception:
                        ts = datetime.utcnow()
                else:
                    ts = datetime.utcnow()

                device_id = msg.get("device_id", "device_0")
                value = float(msg.get("value", 0.0))
                label = int(msg.get("label", 0))

                data_tuples.append((ts, device_id, value, label))

            execute_values(
                cur,
                "INSERT INTO iot_data (ts, device_id, value, label) VALUES %s",
                data_tuples,
            )

            # NEW: after inserting sensor data, record a snapshot row
            self.write_dashboard_snapshot()

            self.db_conn.commit()
            self.total_inserts += len(self.batch)
            logger.info(
                "✓ Inserted %d rows (total inserts: %d)",
                len(self.batch),
                self.total_inserts,
            )

            self.batch = []
            self.last_insert_time = time.time()
            cur.close()

        except Exception as e:
            logger.error("✗ Failed to insert batch: %s", e)
            self.db_conn.rollback()

    # --------------------------------------------------------------
    # Main loop
    # --------------------------------------------------------------
    def run(self) -> None:
        """Main collector loop."""
        if not self.connect_kafka():
            sys.exit(1)
        if not self.connect_db():
            sys.exit(1)
        if not self.create_tables():
            sys.exit(1)

        logger.info(
            "Starting collection from topic '%s' (batch=%d, interval=%ds)",
            KAFKA_TOPIC,
            BATCH_SIZE,
            INSERT_INTERVAL_SECONDS,
        )

        try:
            for message in self.kafka_consumer:
                try:
                    data = message.value

                    if "device_id" not in data:
                        data["device_id"] = f"device_{self.total_messages % 2400}"

                    self.batch.append(data)
                    self.total_messages += 1

                    time_since_last = time.time() - self.last_insert_time
                    if (
                        len(self.batch) >= BATCH_SIZE
                        or time_since_last >= INSERT_INTERVAL_SECONDS
                    ):
                        self.insert_batch()

                    if self.total_messages % 100 == 0:
                        logger.info(
                            "Progress: %d messages processed",
                            self.total_messages,
                        )

                except Exception as e:
                    logger.error("Error processing message: %s", e)

        except KeyboardInterrupt:
            logger.info("Shutting down collector…")
        except Exception as e:
            logger.error("Collector error: %s", e)
        finally:
            if self.batch:
                self.insert_batch()

            logger.info(
                "Final stats: %d messages seen, %d rows inserted",
                self.total_messages,
                self.total_inserts,
            )
            if self.kafka_consumer:
                self.kafka_consumer.close()
            if self.db_conn:
                self.db_conn.close()


if __name__ == "__main__":
    collector = KafkaToTimescaleDB()
    collector.run()

#!/usr/bin/env python3
"""
Dashboard metrics updater for FLEAD

Periodically aggregates simple KPIs into dashboard_metrics so that:
- pipeline_monitor.py stops showing zeros
- Grafana can plot longitudinal KPIs

Reads from:
  - iot_data
  - local_models
  - federated_models

Writes into:
  - dashboard_metrics(updated_at, total_iot, total_local_models, total_federated_models)
"""

import logging
import time
from datetime import datetime

import psycopg2

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# DB config – matches your other services
# ---------------------------------------------------------------------
DB_HOST = "timescaledb"
DB_PORT = 5432
DB_NAME = "flead"
DB_USER = "flead"
DB_PASSWORD = "password"

INTERVAL_SECONDS = 15  # how often to write a new metrics row (optimized from 30s)


class DashboardMetricsUpdater:
    def __init__(self):
        self.conn = None

    def connect_db(self) -> bool:
        max_retries = 10
        delay = 5

        for attempt in range(1, max_retries + 1):
            try:
                self.conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    dbname=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    connect_timeout=10,
                )
                self.conn.autocommit = False
                logger.info("✓ Connected to TimescaleDB for dashboard_metrics")
                return True
            except Exception as e:
                logger.warning(
                    "DB connect attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    e,
                )
                if attempt < max_retries:
                    time.sleep(delay)
        logger.error("✗ Could not connect to DB after %d attempts", max_retries)
        return False

    def ensure_table(self) -> bool:
        """
        Create dashboard_metrics table if it doesn't exist.
        Matches schema from 00_init_database.py
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_metrics (
                    id           BIGSERIAL,
                    metric_name  TEXT            NOT NULL,
                    metric_value DOUBLE PRECISION NOT NULL,
                    metric_unit  TEXT            NOT NULL,
                    device_id    TEXT,
                    timestamp    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                    CONSTRAINT dashboard_metrics_unique_name_ts
                        UNIQUE (metric_name, timestamp)
                );

                SELECT create_hypertable('dashboard_metrics', 'timestamp', if_not_exists => TRUE);

                CREATE INDEX IF NOT EXISTS idx_dashboard_metrics_name
                    ON dashboard_metrics (metric_name, timestamp);
                """
            )
            self.conn.commit()
            cur.close()
            logger.info("✓ dashboard_metrics table ready")
            return True
        except Exception as e:
            # It might fail if hypertable already exists or other race conditions, 
            # but usually safe to ignore if table exists.
            logger.warning("⚠ ensure_table warning (might be safe if table exists): %s", e)
            self.conn.rollback()
            return True  # Assume it exists

    def compute_kpis(self):
        """Return (total_iot, total_local, total_federated, total_anomalies)."""
        try:
            cur = self.conn.cursor()

            # raw IoT rows
            try:
                cur.execute("SELECT COUNT(*) FROM iot_data;")
                total_iot = cur.fetchone()[0]
            except Exception:
                total_iot = 0

            # local model rows
            try:
                cur.execute("SELECT COUNT(*) FROM local_models;")
                total_local = cur.fetchone()[0]
            except Exception:
                total_local = 0

            # federated model rows
            try:
                cur.execute("SELECT COUNT(*) FROM federated_models;")
                total_fed = cur.fetchone()[0]
            except Exception:
                total_fed = 0

            # anomalies count
            try:
                cur.execute("SELECT COUNT(*) FROM anomalies;")
                total_anomalies = cur.fetchone()[0]
            except Exception:
                total_anomalies = 0

            cur.close()
            return total_iot, total_local, total_fed, total_anomalies

        except Exception as e:
            logger.error("✗ Failed to compute KPIs: %s", e)
            return 0, 0, 0, 0

    def insert_metrics_row(self, total_iot, total_local, total_fed, total_anomalies):
        """Insert rows into dashboard_metrics (one per KPI)."""
        try:
            cur = self.conn.cursor()
            now = datetime.utcnow()
            
            # We insert 4 rows, one for each metric
            metrics = [
                ("total_iot_count", float(total_iot), "count"),
                ("total_local_models_count", float(total_local), "count"),
                ("total_federated_models_count", float(total_fed), "count"),
                ("total_anomalies_count", float(total_anomalies), "count"),
            ]

            for name, val, unit in metrics:
                cur.execute(
                    """
                    INSERT INTO dashboard_metrics
                        (metric_name, metric_value, metric_unit, timestamp, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (metric_name, timestamp) DO NOTHING;
                    """,
                    (name, val, unit, now, now),
                )

            self.conn.commit()
            cur.close()
            logger.info(
                "✓ Inserted dashboard_metrics rows: iot=%d, local=%d, fed=%d, anomalies=%d",
                total_iot,
                total_local,
                total_fed,
                total_anomalies,
            )
        except Exception as e:
            logger.error("✗ Failed to insert dashboard_metrics row: %s", e)
            self.conn.rollback()

    def run(self):
        if not self.connect_db():
            return
        if not self.ensure_table():
            return

        logger.info(
            "Starting dashboard_metrics updater (interval=%ds)",
            INTERVAL_SECONDS,
        )

        try:
            while True:
                total_iot, total_local, total_fed, total_anomalies = self.compute_kpis()
                self.insert_metrics_row(total_iot, total_local, total_fed, total_anomalies)
                time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Stopping dashboard_metrics updater (Ctrl+C)")
        finally:
            if self.conn:
                self.conn.close()


if __name__ == "__main__":
    DashboardMetricsUpdater().run()

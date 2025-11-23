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

INTERVAL_SECONDS = 30  # how often to write a new metrics row


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

        Only requirements from pipeline_monitor:
          - table name: dashboard_metrics
          - column: updated_at TIMESTAMPTZ
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_metrics (
                    id                      SERIAL PRIMARY KEY,
                    updated_at              TIMESTAMPTZ NOT NULL,
                    total_iot               BIGINT NOT NULL,
                    total_local_models      BIGINT NOT NULL,
                    total_federated_models  BIGINT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_dashboard_metrics_updated_at
                    ON dashboard_metrics(updated_at);
                """
            )
            self.conn.commit()
            cur.close()
            logger.info("✓ dashboard_metrics table ready")
            return True
        except Exception as e:
            logger.error("✗ Failed to ensure dashboard_metrics table: %s", e)
            self.conn.rollback()
            return False

    def compute_kpis(self):
        """Return (total_iot, total_local, total_federated)."""
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

            cur.close()
            return total_iot, total_local, total_fed

        except Exception as e:
            logger.error("✗ Failed to compute KPIs: %s", e)
            return 0, 0, 0

    def insert_metrics_row(self, total_iot, total_local, total_fed):
        """Insert a single row into dashboard_metrics."""
        try:
            cur = self.conn.cursor()
            now = datetime.utcnow()
            cur.execute(
                """
                INSERT INTO dashboard_metrics
                    (updated_at, total_iot, total_local_models, total_federated_models)
                VALUES (%s, %s, %s, %s);
                """,
                (now, total_iot, total_local, total_fed),
            )
            self.conn.commit()
            cur.close()
            logger.info(
                "✓ Inserted dashboard_metrics row: iot=%d, local=%d, fed=%d",
                total_iot,
                total_local,
                total_fed,
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
                total_iot, total_local, total_fed = self.compute_kpis()
                self.insert_metrics_row(total_iot, total_local, total_fed)
                time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Stopping dashboard_metrics updater (Ctrl+C)")
        finally:
            if self.conn:
                self.conn.close()


if __name__ == "__main__":
    DashboardMetricsUpdater().run()

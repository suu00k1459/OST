"""XGBoost-based forecasting pipeline for FLEAD/TimescaleDB.

Reads recent IoT metrics from a TimescaleDB table, trains an XGBoost regressor
on lagged values, and writes short-horizon forecasts back into another table.

This script is designed to be run as a long-lived background service.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Tuple, List, Optional

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from xgboost import XGBRegressor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (override via environment variables to match your schema)
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "flead")
DB_USER = os.getenv("DB_USER", "flead")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# Source table: where raw or aggregated metrics live
# Adjust these to match your actual schema (or set env vars)
SOURCE_TABLE = os.getenv("FORECAST_SOURCE_TABLE", "iot_metrics")
TIME_COL = os.getenv("FORECAST_TIME_COL", "ts")
DEVICE_COL = os.getenv("FORECAST_DEVICE_COL", "device_id")
VALUE_COL = os.getenv("FORECAST_VALUE_COL", "value")

# Target table: where we will store forecasts
FORECAST_TABLE = os.getenv("FORECAST_TABLE", "iot_forecasts")

# How much history to use & forecast horizon
HISTORY_HOURS = int(os.getenv("FORECAST_HISTORY_HOURS", "6"))
LAG_STEPS = int(os.getenv("FORECAST_LAG_STEPS", "24"))           # past points as features
FORECAST_HORIZON = int(os.getenv("FORECAST_HORIZON", "12"))      # future points per device

# Service loop timing
TRAIN_INTERVAL_SECONDS = int(os.getenv("FORECAST_INTERVAL_SECONDS", "300"))  # 5 minutes

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    conn.autocommit = True
    return conn

def ensure_forecast_table(conn) -> None:
    """Create the forecast table if it does not exist.

    Schema is generic; adapt column names if needed.
    """
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {FORECAST_TABLE} (
        id              BIGSERIAL PRIMARY KEY,
        {DEVICE_COL}    TEXT NOT NULL,
        {TIME_COL}      TIMESTAMPTZ NOT NULL,
        forecast_value  DOUBLE PRECISION NOT NULL,
        horizon_step    INTEGER NOT NULL,
        model_name      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    logger.info("✓ Ensured forecast table exists: %s", FORECAST_TABLE)

def fetch_recent_data(conn) -> pd.DataFrame:
    """Fetch recent history from the source table as a pandas DataFrame."""
    cutoff_time = datetime.utcnow() - timedelta(hours=HISTORY_HOURS)
    query = f"""
        SELECT {DEVICE_COL} AS device_id,
               {TIME_COL}   AS ts,
               {VALUE_COL}  AS value
        FROM {SOURCE_TABLE}
        WHERE {TIME_COL} >= %s
        ORDER BY device_id, ts
    """
    df = pd.read_sql(query, conn, params=[cutoff_time])
    if df.empty:
        logger.warning("No data returned from %s since %s", SOURCE_TABLE, cutoff_time)
    else:
        logger.info("Fetched %d rows from %s", len(df), SOURCE_TABLE)
    return df

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def build_supervised_sequences(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Create lagged features and targets for supervised learning.

    For each device, we create rows like:
        X = [v(t-1), v(t-2), ..., v(t-LAG_STEPS)]
        y = v(t)
    """
    X_list: List[np.ndarray] = []
    y_list: List[float] = []

    for device_id, g in df.groupby("device_id"):
        g = g.sort_values("ts")
        values = g["value"].values.astype(float)
        if len(values) <= LAG_STEPS:
            continue

        for idx in range(LAG_STEPS, len(values)):
            window = values[idx - LAG_STEPS: idx]
            target = values[idx]
            X_list.append(window)
            y_list.append(target)

    if not X_list:
        logger.warning("No supervised sequences could be built (too little data)")
        return np.empty((0, LAG_STEPS)), np.empty((0,))

    X = np.vstack(X_list)
    y = np.array(y_list)
    logger.info("Built supervised dataset: X=%s, y=%s", X.shape, y.shape)
    return X, y

# ---------------------------------------------------------------------------
# Model training & forecasting
# ---------------------------------------------------------------------------

def train_xgboost_regressor(X: np.ndarray, y: np.ndarray) -> Optional[XGBRegressor]:
    if X.size == 0 or y.size == 0:
        logger.warning("Not enough data to train XGBoost model")
        return None

    model = XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        n_jobs=4,
        tree_method="hist",
    )
    logger.info("Training XGBoost model...")
    model.fit(X, y)
    logger.info("✓ XGBoost training complete")
    return model

def make_forecasts_per_device(
    model: XGBRegressor,
    df: pd.DataFrame
) -> List[Tuple[str, datetime, float, int, str]]:
    """Generate multi-step forecasts per device.

    Returns list of tuples ready for bulk insert:
        (device_id, ts_forecast, forecast_value, horizon_step, model_name)
    """
    if model is None or df.empty:
        return []

    rows: List[Tuple[str, datetime, float, int, str]] = []
    model_name = "xgboost_regressor"

    # 🔹 Ensure timestamps are proper pandas datetimes
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])

    for device_id, g in df.groupby("device_id"):
        g = g.sort_values("ts")
        values = g["value"].values.astype(float)
        times = g["ts"]

        if len(values) < LAG_STEPS:
            continue

        # Start from the last observed window
        window = values[-LAG_STEPS:].copy()

        # Last observed timestamp as a Python datetime
        last_ts = times.iloc[-1]
        if hasattr(last_ts, "to_pydatetime"):
            last_ts = last_ts.to_pydatetime()

        # Infer step size from recent timestamps, default to 1 minute
        if len(times) >= 2:
            step_delta = times.iloc[-1] - times.iloc[-2]  # pandas Timedelta
            try:
                step = step_delta.to_pytimedelta()  # convert to datetime.timedelta
            except AttributeError:
                step = timedelta(seconds=float(step_delta.total_seconds()))
        else:
            step = timedelta(minutes=1)

        for h in range(1, FORECAST_HORIZON + 1):
            x_input = window.reshape(1, -1)
            y_hat = float(model.predict(x_input)[0])

            # ✅ Safe: Python datetime + Python timedelta
            forecast_ts = last_ts + h * step
            rows.append((str(device_id), forecast_ts, y_hat, h, model_name))

            # Update window: drop oldest, append new prediction
            window = np.roll(window, -1)
            window[-1] = y_hat

    logger.info("Generated %d forecast rows", len(rows))
    return rows

def insert_forecasts(conn, rows: List[Tuple[str, datetime, float, int, str]]) -> None:
    if not rows:
        logger.info("No forecast rows to insert")
        return

    insert_sql = f"""
    INSERT INTO {FORECAST_TABLE} ({DEVICE_COL}, {TIME_COL}, forecast_value, horizon_step, model_name)
    VALUES %s
    """
    with conn.cursor() as cur:
        execute_values(cur, insert_sql, rows)
    logger.info("✓ Inserted %d forecast rows into %s", len(rows), FORECAST_TABLE)

# ---------------------------------------------------------------------------
# Main service loop
# ---------------------------------------------------------------------------

def run_forecasting_service():
    logger.info("Starting XGBoost forecasting service...")
    logger.info("Source table:   %s", SOURCE_TABLE)
    logger.info("Forecast table: %s", FORECAST_TABLE)

    conn = None
    try:
        conn = get_db_connection()
        ensure_forecast_table(conn)

        while True:
            try:
                logger.info("=== Forecasting cycle started ===")
                df = fetch_recent_data(conn)
                if df.empty:
                    logger.info("No data available; sleeping %ds", TRAIN_INTERVAL_SECONDS)
                    time.sleep(TRAIN_INTERVAL_SECONDS)
                    continue

                X, y = build_supervised_sequences(df)
                model = train_xgboost_regressor(X, y)
                if model is None:
                    logger.info("Model not trained; sleeping %ds", TRAIN_INTERVAL_SECONDS)
                    time.sleep(TRAIN_INTERVAL_SECONDS)
                    continue

                rows = make_forecasts_per_device(model, df)
                insert_forecasts(conn, rows)

            except Exception as e:
                logger.error("Error in forecasting cycle: %s", e, exc_info=True)

            logger.info("Sleeping %ds before next training/forecast cycle...", TRAIN_INTERVAL_SECONDS)
            time.sleep(TRAIN_INTERVAL_SECONDS)

    finally:
        if conn is not None:
            conn.close()
            logger.info("DB connection closed")

if __name__ == "__main__":
    run_forecasting_service()

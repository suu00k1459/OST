-- ============================================
-- Load TimescaleDB Extension
-- ============================================
CREATE EXTENSION IF NOT EXISTS timescaledb;

--------------------------------------------------
-- Federated Metrics Table
--------------------------------------------------
CREATE TABLE IF NOT EXISTS federated_metrics (
    ts TIMESTAMPTZ NOT NULL,
    round INT,
    metric TEXT,
    value DOUBLE PRECISION
);

SELECT create_hypertable(
    'federated_metrics',
    'ts',
    if_not_exists => TRUE
);

--------------------------------------------------
-- Forecasting Table
-- PK MUST include partitioning key (ts)
--------------------------------------------------
CREATE TABLE IF NOT EXISTS device_forecast (
    id BIGSERIAL,
    device_id INT NOT NULL,
    metric_name TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    forecast_value DOUBLE PRECISION NOT NULL,
    horizon_minutes INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Composite PK (VALID for hypertables)
    PRIMARY KEY (device_id, metric_name, ts, horizon_minutes)
);

SELECT create_hypertable(
    'device_forecast',
    'ts',
    if_not_exists => TRUE
);

--------------------------------------------------
-- Raw Archive Table
-- (No primary key → avoids Timescale error)
--------------------------------------------------
CREATE TABLE IF NOT EXISTS device_raw_archive (
    id BIGSERIAL,
    device_id INT NOT NULL,
    metric_name TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    extra JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable(
    'device_raw_archive',
    'ts',
    if_not_exists => TRUE
);

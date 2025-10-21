CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS federated_metrics (
ts TIMESTAMPTZ NOT NULL,
round INT,
metric TEXT,
value DOUBLE PRECISION
);
SELECT create_hypertable('federated_metrics','ts', if_not_exists => TRUE);
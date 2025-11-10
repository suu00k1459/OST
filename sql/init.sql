-- Ensure TimescaleDB extension is loaded
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Explicitly create user if it doesn't exist
-- This fixes the "password authentication failed" error on some machines
DO $$ 
BEGIN 
  CREATE USER flead WITH PASSWORD 'password'; 
EXCEPTION WHEN duplicate_object THEN 
  RAISE NOTICE 'User flead already exists'; 
END 
$$;

-- Grant all privileges to flead user
ALTER USER flead WITH CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE flead TO flead;

-- Create the federated_metrics table
CREATE TABLE IF NOT EXISTS federated_metrics (
    ts TIMESTAMPTZ NOT NULL,
    round INT,
    metric TEXT,
    value DOUBLE PRECISION
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('federated_metrics','ts', if_not_exists => TRUE);

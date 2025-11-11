"""
Database Initialization Script
Creates all required tables in TimescaleDB for the FLEAD pipeline
Run this BEFORE starting the pipeline to ensure database schema exists

Automatically detects if running inside Docker or locally
"""

import psycopg2
import logging
import time
import os
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import config loader for environment detection
import sys
sys.path.insert(0, os.path.dirname(__file__))
from config_loader import get_db_config

# Database configuration - auto-detect Docker vs local
db_config = get_db_config()
DB_HOST = db_config['host']
DB_PORT = db_config['port']
DB_NAME = db_config['database']
DB_USER = db_config['user']
DB_PASSWORD = db_config['password']

logger.info(f"Database Config: host={DB_HOST}, port={DB_PORT}, database={DB_NAME}, user={DB_USER}")

# SQL statements for table creation
CREATE_TABLES_SQL = """
-- Drop existing tables if they exist (for clean start)
DROP TABLE IF EXISTS local_models CASCADE;
DROP TABLE IF EXISTS federated_models CASCADE;
DROP TABLE IF EXISTS dashboard_metrics CASCADE;
DROP TABLE IF EXISTS batch_analysis_results CASCADE;
DROP TABLE IF EXISTS stream_analysis_results CASCADE;
DROP TABLE IF EXISTS model_evaluations CASCADE;

-- Create local_models table (stores per-device model training results)
-- Note: Primary key includes created_at for TimescaleDB hypertable compatibility
CREATE TABLE local_models (
    id BIGSERIAL,
    device_id TEXT NOT NULL,
    model_version INT NOT NULL,
    global_version INT NOT NULL,
    accuracy FLOAT NOT NULL,
    samples_processed INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Create federated_models table (stores aggregated global models)
CREATE TABLE federated_models (
    id BIGSERIAL,
    global_version INT NOT NULL,
    aggregation_round INT NOT NULL,
    num_devices INT NOT NULL,
    accuracy FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Create dashboard_metrics table (for Grafana live metrics)
CREATE TABLE dashboard_metrics (
    id BIGSERIAL,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    metric_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Create batch_analysis_results table (Spark batch analytics)
CREATE TABLE batch_analysis_results (
    id BIGSERIAL PRIMARY KEY,
    analysis_type TEXT NOT NULL,
    result_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create stream_analysis_results table (Spark streaming analytics)
CREATE TABLE stream_analysis_results (
    id BIGSERIAL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    analysis_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Create model_evaluations table (Global model performance tracking)
CREATE TABLE model_evaluations (
    id BIGSERIAL,
    global_version INT NOT NULL,
    evaluation_data JSONB NOT NULL,
    accuracy FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Convert tables to TimescaleDB hypertables (for time-series optimization)
SELECT create_hypertable('local_models', 'created_at', if_not_exists => TRUE);
SELECT create_hypertable('federated_models', 'created_at', if_not_exists => TRUE);
SELECT create_hypertable('dashboard_metrics', 'created_at', if_not_exists => TRUE);
SELECT create_hypertable('stream_analysis_results', 'created_at', if_not_exists => TRUE);
SELECT create_hypertable('model_evaluations', 'created_at', if_not_exists => TRUE);

-- Create indexes for better query performance (after hypertable creation)
CREATE INDEX idx_local_models_device_id ON local_models(device_id, created_at DESC);
CREATE INDEX idx_federated_models_global_version ON federated_models(global_version);
CREATE INDEX idx_dashboard_metrics_name ON dashboard_metrics(metric_name);
CREATE INDEX idx_model_evaluations_version ON model_evaluations(global_version);
"""


def wait_for_database(max_retries: int = 60, retry_interval: int = 2) -> bool:
    """Wait for TimescaleDB to be ready with improved retry logic"""
    logger.info("Waiting for TimescaleDB to be ready...")
    logger.info(f"Connection details: host={DB_HOST}:{DB_PORT}, database={DB_NAME}, user={DB_USER}")
    logger.info(f"Max retries: {max_retries} (total wait time: ~{max_retries * retry_interval}s)")
    
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=10  # Increased from 5 to 10 seconds
            )
            conn.close()
            logger.info("✓ TimescaleDB is ready and user authenticated")
            time.sleep(2)  # Extra delay to ensure full initialization
            return True
        except psycopg2.OperationalError as e:
            error_msg = str(e)
            attempt_num = i + 1
            
            # Check if this is an authentication error
            if "password authentication failed" in error_msg or "FATAL" in error_msg:
                if attempt_num % 10 == 0:  # Log every 10 attempts
                    logger.info(f"  Waiting for user authentication to be ready... ({attempt_num}/{max_retries})")
                    logger.debug(f"    PostgreSQL is still initializing the user account")
            else:
                if attempt_num % 10 == 0:
                    logger.info(f"  Waiting for database connection... ({attempt_num}/{max_retries})")
            
            if i < max_retries - 1:
                time.sleep(retry_interval)
            else:
                logger.error(f"✗ Could not connect to database after {max_retries} attempts")
                logger.error(f"  Error: {error_msg}")
                logger.error(f"")
                logger.error(f"   If you see 'password authentication failed':")
                logger.error(f"     - The database user is not fully initialized yet")
                logger.error(f"     - Run: docker-compose down -v")
                logger.error(f"     - Then: docker-compose up -d")
                logger.error(f"")
                logger.error(f"  Troubleshooting:")
                logger.error(f"    1. Check if Docker is running: docker ps")
                logger.error(f"    2. Check timescaledb logs: docker logs timescaledb -f")
                logger.error(f"    3. Verify credentials match in docker-compose.yml and init.sql")
                logger.error(f"    4. Check if volume is corrupted: docker volume ls | grep timescaledb")
                return False
    
    return False


def init_database() -> bool:
    """Initialize database schema"""
    logger.info("=" * 70)
    logger.info("DATABASE INITIALIZATION")
    logger.info("=" * 70)
    
    # Wait for database to be available
    if not wait_for_database():
        return False
    
    # Connect and create tables
    try:
        logger.info("\nConnecting to TimescaleDB...")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        logger.info("✓ Connected to database")
        
        # Execute table creation
        logger.info("\nCreating database schema...")
        cursor.execute(CREATE_TABLES_SQL)
        
        logger.info("✓ Tables created successfully")
        
        # Verify tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        logger.info("\nCreated tables:")
        for table in tables:
            logger.info(f"  ✓ {table[0]}")
        
        # Verify hypertables
        cursor.execute("""
            SELECT hypertable_name 
            FROM timescaledb_information.hypertables
            ORDER BY hypertable_name;
        """)
        hypertables = cursor.fetchall()
        
        if hypertables:
            logger.info("\nTimescaleDB hypertables:")
            for ht in hypertables:
                logger.info(f"  ✓ {ht[0]}")
        
        cursor.close()
        conn.close()
        
        logger.info("\n" + "=" * 70)
        logger.info("✓ DATABASE INITIALIZATION COMPLETE")
        logger.info("=" * 70)
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ Database initialization failed: {e}")
        return False


def main():
    """Main entry point"""
    try:
        success = init_database()
        if success:
            logger.info("\n✓ Database is ready for the pipeline")
            return 0
        else:
            logger.error("\n✗ Database initialization failed")
            return 1
    except KeyboardInterrupt:
        logger.info("\nInitialization cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())

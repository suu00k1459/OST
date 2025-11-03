"""
Spark Batch Analytics Job
Long-term trend analysis and batch anomaly detection on historical IoT data
Reads from TimescaleDB, processes with Spark SQL and MLlib
Writes analytics results back to TimescaleDB

Features:
- Time-series trend analysis (daily, weekly aggregations)
- Statistical anomaly detection
- Device performance metrics
- Predictive maintenance signals
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

from pyspark.sql import SparkSession, Window, DataFrame
from pyspark.sql.functions import (
    col, avg, stddev, min as spark_min, max as spark_max,
    count, sum as spark_sum, datediff, hour, dayofweek, 
    row_number, lag, abs as spark_abs, when, lit,
    to_timestamp, date_format, date_add, current_timestamp
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType, TimestampType
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.stat import Correlation
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'timescaledb',
    'port': 5432,
    'database': 'flead',
    'user': 'flead',
    'password': 'password'
}

# Spark configuration
SPARK_MASTER = 'spark://spark-master:7077'
BATCH_WINDOW_HOURS = 24  # Process last 24 hours
ANOMALY_THRESHOLD_STD = 2.5  # Standard deviations for anomaly detection


class SparkAnalyticsJob:
    """Spark batch analytics for IoT data"""
    
    def __init__(self):
        """Initialize Spark session"""
        self.spark = SparkSession.builder \
            .appName('FLEAD-Batch-Analytics') \
            .master(SPARK_MASTER) \
            .config('spark.sql.extensions', 'io.delta.sql.DeltaSparkSessionExtension') \
            .config('spark.sql.catalog.spark_catalog', 'org.apache.spark.sql.delta.catalog.DeltaCatalog') \
            .getOrCreate()
        
        self.spark.sparkContext.setLogLevel('INFO')
        logger.info("✓ Spark session initialized")
        
        self.db_connection = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database connection"""
        try:
            self.db_connection = psycopg2.connect(**DB_CONFIG)
            logger.info("✓ Connected to TimescaleDB")
            
            # Create output tables if not exist
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS analytics_daily_stats (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        analysis_date DATE NOT NULL,
                        metric_name TEXT NOT NULL,
                        avg_value FLOAT,
                        min_value FLOAT,
                        max_value FLOAT,
                        stddev_value FLOAT,
                        sample_count INT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS anomalies_batch (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        metric_name TEXT NOT NULL,
                        anomaly_type TEXT NOT NULL,
                        value FLOAT,
                        expected_range_min FLOAT,
                        expected_range_max FLOAT,
                        severity TEXT,
                        analysis_window_start TIMESTAMPTZ,
                        analysis_window_end TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS predictive_signals (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        signal_type TEXT NOT NULL,
                        description TEXT,
                        confidence FLOAT,
                        predicted_issue TEXT,
                        recommended_action TEXT,
                        analysis_timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                # Create hypertables
                for table in ['analytics_daily_stats', 'anomalies_batch', 'predictive_signals']:
                    try:
                        cursor.execute(f"""
                            SELECT create_hypertable('{table}', 'created_at', if_not_exists => TRUE)
                        """)
                    except:
                        pass
                
                self.db_connection.commit()
                logger.info("✓ Analytics tables ready")
        
        except Exception as e:
            logger.error(f"✗ Database error: {e}")
            raise
    
    def read_from_timescaledb(self, query: str) -> DataFrame:
        """Read data from TimescaleDB using Spark SQL"""
        try:
            # Read using JDBC connector
            df = self.spark.read \
                .format('jdbc') \
                .option('url', f"jdbc:postgresql://{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}") \
                .option('user', DB_CONFIG['user']) \
                .option('password', DB_CONFIG['password']) \
                .option('query', query) \
                .load()
            
            logger.info(f"✓ Read {df.count()} rows from TimescaleDB")
            return df
        
        except Exception as e:
            logger.error(f"✗ Error reading from TimescaleDB: {e}")
            raise
    
    def calculate_daily_statistics(self) -> None:
        """Calculate daily statistics for all devices"""
        try:
            logger.info("\n" + "=" * 70)
            logger.info("Calculating Daily Statistics...")
            logger.info("=" * 70)
            
            # Read metrics from TimescaleDB
            query = f"""
                SELECT 
                    device_id,
                    time,
                    value
                FROM federated_metrics
                WHERE time > NOW() - INTERVAL '{BATCH_WINDOW_HOURS} hours'
                ORDER BY device_id, time
            """
            
            df = self.read_from_timescaledb(query)
            
            if df.count() == 0:
                logger.warning("⚠ No data available for analysis")
                return
            
            # Add date column
            df = df.withColumn('analysis_date', to_timestamp(col('time')).cast('date'))
            
            # Calculate statistics per device per day
            stats_df = df.groupBy(col('device_id'), col('analysis_date')) \
                .agg(
                    avg(col('value')).alias('avg_value'),
                    spark_min(col('value')).alias('min_value'),
                    spark_max(col('value')).alias('max_value'),
                    stddev(col('value')).alias('stddev_value'),
                    count(col('value')).alias('sample_count')
                )
            
            # Save to database
            for row in stats_df.collect():
                try:
                    with self.db_connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO analytics_daily_stats
                            (device_id, analysis_date, metric_name, avg_value, min_value, 
                             max_value, stddev_value, sample_count)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            row['device_id'],
                            row['analysis_date'],
                            'generic_metric',
                            float(row['avg_value']) if row['avg_value'] else None,
                            float(row['min_value']) if row['min_value'] else None,
                            float(row['max_value']) if row['max_value'] else None,
                            float(row['stddev_value']) if row['stddev_value'] else None,
                            int(row['sample_count'])
                        ))
                    self.db_connection.commit()
                except Exception as e:
                    logger.warning(f"Error saving stats: {e}")
            
            logger.info(f"✓ Calculated statistics for {stats_df.count()} device-days")
        
        except Exception as e:
            logger.error(f"Error calculating daily statistics: {e}")
    
    def detect_batch_anomalies(self) -> None:
        """Detect anomalies in historical data using statistical methods"""
        try:
            logger.info("\n" + "=" * 70)
            logger.info("Detecting Batch Anomalies...")
            logger.info("=" * 70)
            
            # Read metrics from TimescaleDB
            query = f"""
                SELECT 
                    device_id,
                    time,
                    value
                FROM federated_metrics
                WHERE time > NOW() - INTERVAL '{BATCH_WINDOW_HOURS} hours'
                ORDER BY device_id, time
            """
            
            df = self.read_from_timescaledb(query)
            
            if df.count() == 0:
                logger.warning("⚠ No data available for anomaly detection")
                return
            
            # Calculate statistics per device
            window_spec = Window.partitionBy('device_id')
            df_with_stats = df.withColumn(
                'device_avg', avg(col('value')).over(window_spec)
            ).withColumn(
                'device_stddev', stddev(col('value')).over(window_spec)
            )
            
            # Detect anomalies
            anomalies_df = df_with_stats.withColumn(
                'z_score', spark_abs((col('value') - col('device_avg')) / (col('device_stddev') + 0.0001))
            ).filter(
                col('z_score') > ANOMALY_THRESHOLD_STD
            ).withColumn(
                'expected_min', col('device_avg') - (ANOMALY_THRESHOLD_STD * col('device_stddev'))
            ).withColumn(
                'expected_max', col('device_avg') + (ANOMALY_THRESHOLD_STD * col('device_stddev'))
            ).withColumn(
                'severity', when(col('z_score') > ANOMALY_THRESHOLD_STD * 2, 'critical')
                           .when(col('z_score') > ANOMALY_THRESHOLD_STD, 'warning')
                           .otherwise('normal')
            )
            
            # Save anomalies to database
            anomalies = anomalies_df.collect()
            
            for row in anomalies:
                try:
                    with self.db_connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO anomalies_batch
                            (device_id, metric_name, anomaly_type, value, expected_range_min,
                             expected_range_max, severity, analysis_window_start, analysis_window_end)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            row['device_id'],
                            'value',
                            'statistical_outlier',
                            float(row['value']),
                            float(row['expected_min']),
                            float(row['expected_max']),
                            row['severity'],
                            row['time'],
                            row['time']
                        ))
                    self.db_connection.commit()
                except Exception as e:
                    logger.warning(f"Error saving anomaly: {e}")
            
            logger.info(f"✓ Detected {len(anomalies)} anomalies")
        
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
    
    def generate_predictive_signals(self) -> None:
        """Generate predictive maintenance signals"""
        try:
            logger.info("\n" + "=" * 70)
            logger.info("Generating Predictive Signals...")
            logger.info("=" * 70)
            
            # Read recent anomalies
            query = """
                SELECT 
                    device_id,
                    COUNT(*) as anomaly_count,
                    AVG(CAST(value AS FLOAT)) as avg_anomaly_value,
                    MAX(created_at) as latest_anomaly
                FROM anomalies_batch
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY device_id
                HAVING COUNT(*) > 3
            """
            
            try:
                with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    devices_at_risk = cursor.fetchall()
            except:
                devices_at_risk = []
            
            # Generate signals
            for device in devices_at_risk:
                try:
                    device_id = device['device_id']
                    anomaly_count = device['anomaly_count']
                    confidence = min(0.95, anomaly_count * 0.15)
                    
                    signal_record = {
                        'device_id': device_id,
                        'signal_type': 'predictive_maintenance',
                        'description': f'{anomaly_count} anomalies detected in last 7 days',
                        'confidence': float(confidence),
                        'predicted_issue': 'Potential device degradation',
                        'recommended_action': 'Schedule maintenance inspection',
                        'analysis_timestamp': datetime.now().isoformat()
                    }
                    
                    with self.db_connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO predictive_signals
                            (device_id, signal_type, description, confidence, 
                             predicted_issue, recommended_action, analysis_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            signal_record['device_id'],
                            signal_record['signal_type'],
                            signal_record['description'],
                            signal_record['confidence'],
                            signal_record['predicted_issue'],
                            signal_record['recommended_action'],
                            signal_record['analysis_timestamp']
                        ))
                    self.db_connection.commit()
                    
                    logger.info(f"  Device {device_id}: Confidence {confidence:.2%} - "
                              f"{signal_record['recommended_action']}")
                
                except Exception as e:
                    logger.warning(f"Error saving signal: {e}")
            
            logger.info(f"✓ Generated {len(devices_at_risk)} predictive signals")
        
        except Exception as e:
            logger.error(f"Error generating predictive signals: {e}")
    
    def run(self):
        """Run all analytics jobs"""
        try:
            logger.info("=" * 70)
            logger.info("FLEAD Spark Batch Analytics Job")
            logger.info("=" * 70)
            logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
            logger.info(f"Spark Master: {SPARK_MASTER}")
            logger.info(f"Analysis Window: {BATCH_WINDOW_HOURS} hours")
            logger.info(f"Anomaly Threshold: {ANOMALY_THRESHOLD_STD} std deviations")
            logger.info("=" * 70)
            
            # Run analytics jobs
            self.calculate_daily_statistics()
            self.detect_batch_anomalies()
            self.generate_predictive_signals()
            
            logger.info("\n" + "=" * 70)
            logger.info("✓ Batch Analytics Job Completed")
            logger.info("=" * 70)
        
        except Exception as e:
            logger.error(f"Error in analytics job: {e}")
            import traceback
            traceback.print_exc()
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self.spark:
                self.spark.stop()
            if self.db_connection:
                self.db_connection.close()
            logger.info("✓ Cleanup complete")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


def main():
    """Main entry point"""
    job = SparkAnalyticsJob()
    try:
        job.run()
    finally:
        job.cleanup()


if __name__ == '__main__':
    main()

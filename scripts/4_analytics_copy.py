"""
Analytics Component - TimescaleDB Integration
Team: SU YOUNG, ROBERT
Stores IoT data and model results in TimescaleDB, performs analytics
"""

import json
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from pathlib import Path

# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '../config/settings.json')
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

# TimescaleDB configuration
DB_CONFIG = config['timescaledb']
HOST = DB_CONFIG['host']
PORT = DB_CONFIG['port']
DATABASE = DB_CONFIG['database']
USER = DB_CONFIG['user']
PASSWORD = DB_CONFIG['password']


def connect_timescaledb():
    """Create connection to TimescaleDB"""
    try:
        conn = psycopg2.connect(
            host=HOST,
            port=PORT,
            database=DATABASE,
            user=USER,
            password=PASSWORD
        )
        print(f"✓ Connected to TimescaleDB at {HOST}:{PORT}/{DATABASE}")
        return conn
    except psycopg2.Error as e:
        print(f"✗ Failed to connect to TimescaleDB: {e}")
        raise


def initialize_database(conn):
    """Create tables if they don't exist"""
    cursor = conn.cursor()
    
    try:
        # Create hypertable for sensor data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS iot_sensor_data (
                time TIMESTAMPTZ NOT NULL,
                device_id TEXT NOT NULL,
                temperature FLOAT,
                humidity FLOAT,
                light FLOAT,
                voltage FLOAT
            );
            
            SELECT create_hypertable('iot_sensor_data', 'time', 
                    if_not_exists => TRUE);
        """)
        
        # Create model results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_results (
                time TIMESTAMPTZ NOT NULL,
                device_id TEXT NOT NULL,
                predicted_temperature FLOAT,
                actual_temperature FLOAT,
                model_error FLOAT,
                model_path TEXT
            );
            
            SELECT create_hypertable('model_results', 'time', 
                    if_not_exists => TRUE);
        """)
        
        # Create aggregation results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aggregation_results (
                time TIMESTAMPTZ NOT NULL,
                round_number INT,
                aggregation_method TEXT,
                model_path TEXT,
                metrics JSONB
            );
            
            SELECT create_hypertable('aggregation_results', 'time', 
                    if_not_exists => TRUE);
        """)
        
        conn.commit()
        print("✓ Database tables initialized")
        
    except psycopg2.Error as e:
        print(f"✗ Error initializing database: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def store_processed_data(conn, data_path):
    """Store processed IoT data in TimescaleDB"""
    cursor = conn.cursor()
    
    try:
        # Read processed data
        df = pd.read_csv(data_path)
        print(f"✓ Loaded {len(df)} records from {data_path}")
        
        # Prepare data for insertion
        records = []
        for _, row in df.iterrows():
            records.append((
                datetime.now(),
                str(row.get('device_id', 'unknown')),
                float(row.get('temperature', 0.0)),
                float(row.get('humidity', 0.0)),
                float(row.get('light', 0.0)),
                float(row.get('voltage', 0.0))
            ))
        
        # Insert data
        execute_values(
            cursor,
            """
            INSERT INTO iot_sensor_data (time, device_id, temperature, humidity, light, voltage)
            VALUES %s
            """,
            records,
            page_size=1000
        )
        
        conn.commit()
        print(f"✓ Stored {len(records)} sensor records in TimescaleDB")
        
    except Exception as e:
        print(f"✗ Error storing data: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def store_model_results(conn, model_results):
    """Store model evaluation results"""
    cursor = conn.cursor()
    
    try:
        for device_id, metrics in model_results.items():
            cursor.execute("""
                INSERT INTO model_results 
                (time, device_id, predicted_temperature, actual_temperature, model_error, model_path)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                device_id,
                float(metrics.get('predicted', 0.0)),
                float(metrics.get('actual', 0.0)),
                float(metrics.get('error', 0.0)),
                metrics.get('path', '')
            ))
        
        conn.commit()
        print(f"✓ Stored model results for {len(model_results)} devices")
        
    except Exception as e:
        print(f"✗ Error storing model results: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def compute_analytics(conn):
    """Compute analytics from stored data"""
    cursor = conn.cursor()
    
    try:
        # Device statistics
        cursor.execute("""
            SELECT 
                device_id,
                COUNT(*) as record_count,
                AVG(temperature) as avg_temp,
                MIN(temperature) as min_temp,
                MAX(temperature) as max_temp,
                AVG(humidity) as avg_humidity,
                AVG(light) as avg_light,
                AVG(voltage) as avg_voltage
            FROM iot_sensor_data
            GROUP BY device_id
            ORDER BY record_count DESC
        """)
        
        device_stats = cursor.fetchall()
        print(f"✓ Computed statistics for {len(device_stats)} devices")
        
        # Anomaly detection - temperature outliers
        cursor.execute("""
            SELECT 
                device_id,
                COUNT(*) as anomaly_count,
                AVG(temperature) as avg_anomaly_temp
            FROM iot_sensor_data
            WHERE temperature > (
                SELECT AVG(temperature) + 3*STDDEV(temperature) 
                FROM iot_sensor_data
            )
            GROUP BY device_id
            HAVING COUNT(*) > 0
        """)
        
        anomalies = cursor.fetchall()
        print(f"✓ Detected anomalies in {len(anomalies)} devices")
        
        return device_stats, anomalies
        
    except Exception as e:
        print(f"✗ Error computing analytics: {e}")
        raise
    finally:
        cursor.close()


def generate_report(device_stats, anomalies):
    """Generate analytics report"""
    report = {
        'timestamp': datetime.now().isoformat(),
        'device_statistics': [],
        'anomalies_detected': [],
        'summary': {}
    }
    
    # Add device statistics
    for stat in device_stats:
        report['device_statistics'].append({
            'device_id': stat[0],
            'record_count': stat[1],
            'avg_temperature': float(stat[2]) if stat[2] else 0.0,
            'min_temperature': float(stat[3]) if stat[3] else 0.0,
            'max_temperature': float(stat[4]) if stat[4] else 0.0,
            'avg_humidity': float(stat[5]) if stat[5] else 0.0,
            'avg_light': float(stat[6]) if stat[6] else 0.0,
            'avg_voltage': float(stat[7]) if stat[7] else 0.0
        })
    
    # Add anomalies
    for anomaly in anomalies:
        report['anomalies_detected'].append({
            'device_id': anomaly[0],
            'anomaly_count': anomaly[1],
            'avg_anomaly_temperature': float(anomaly[2]) if anomaly[2] else 0.0
        })
    
    # Summary
    report['summary'] = {
        'total_devices': len(device_stats),
        'devices_with_anomalies': len(anomalies),
        'total_records': sum(stat[1] for stat in device_stats)
    }
    
    return report


def save_report(report):
    """Save report to file"""
    output_dir = os.path.join(os.path.dirname(__file__), '../outputs/analytics')
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    report_path = os.path.join(output_dir, 'analytics_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"✓ Report saved to {report_path}")
    return report_path


def main():
    """Main analytics pipeline"""
    print("=" * 60)
    print("ANALYTICS - TimescaleDB Integration")
    print("=" * 60)
    
    try:
        # Connect to TimescaleDB
        conn = connect_timescaledb()
        
        # Initialize database
        initialize_database(conn)
        
        # Store processed data
        processed_data_path = os.path.join(
            os.path.dirname(__file__), 
            '../data/processed/processed_iot_data.csv'
        )
        if os.path.exists(processed_data_path):
            store_processed_data(conn, processed_data_path)
        else:
            print(f"⚠ Processed data not found at {processed_data_path}")
        
        # Compute analytics
        device_stats, anomalies = compute_analytics(conn)
        
        # Generate and save report
        report = generate_report(device_stats, anomalies)
        save_report(report)
        
        # Close connection
        conn.close()
        print("✓ Connection closed")
        
        print("=" * 60)
        print("ANALYTICS COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Analytics failed: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

"""
Simple Kafka to TimescaleDB Collector
Directly reads IoT data from Kafka and writes to database for Grafana visualization
Bypasses Flink/Spark complexity - just collects and stores real-time data
"""

import json
import logging
import time
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BROKERS = ['kafka-broker-1:29092', 'kafka-broker-2:29093', 'kafka-broker-3:29094', 'kafka-broker-4:29095']
KAFKA_TOPIC = 'edge-iiot-stream'
GROUP_ID = 'timescaledb-collector'

# Database
DB_HOST = 'localhost'
DB_PORT = 5432
DB_NAME = 'flead'
DB_USER = 'flead'
DB_PASSWORD = 'password'

# Batch settings
BATCH_SIZE = 1000
INSERT_INTERVAL_SECONDS = 10

class KafkaToTimescaleDB:
    """Collect Kafka data and write to TimescaleDB"""
    
    def __init__(self):
        self.kafka_consumer = None
        self.db_conn = None
        self.batch = []
        self.last_insert_time = time.time()
        self.total_messages = 0
        self.total_inserts = 0
        
    def connect_kafka(self):
        """Connect to Kafka"""
        try:
            self.kafka_consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKERS,
                group_id=GROUP_ID,
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
                max_poll_records=500,
                connections_max_idle_ms=540000
            )
            logger.info(f"Connected to Kafka brokers: {KAFKA_BROKERS}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def connect_db(self):
        """Connect to TimescaleDB"""
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.db_conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    database=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    connect_timeout=10
                )
                logger.info(f"Connected to TimescaleDB: {DB_HOST}:{DB_PORT}/{DB_NAME}")
                return True
            except Exception as e:
                logger.warning(f"DB connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to database after {max_retries} attempts")
                    return False
        return False
    
    def create_tables(self):
        """Create necessary tables if they don't exist"""
        try:
            cursor = self.db_conn.cursor()
            
            # IoT data table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS iot_data (
                    ts TIMESTAMPTZ NOT NULL,
                    device_id TEXT NOT NULL,
                    value DOUBLE PRECISION,
                    label INT
                );
                
                SELECT create_hypertable('iot_data', 'ts', if_not_exists => TRUE);
                
                CREATE INDEX IF NOT EXISTS idx_iot_data_device_ts ON iot_data (device_id, ts);
            """)
            
            self.db_conn.commit()
            logger.info("Tables created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            self.db_conn.rollback()
            return False
        finally:
            cursor.close()
    
    def insert_batch(self):
        """Insert batch of data into database"""
        if not self.batch:
            return
        
        try:
            cursor = self.db_conn.cursor()
            
            # Prepare data for insertion
            data_tuples = [
                (
                    datetime.fromisoformat(msg['timestamp']) if isinstance(msg.get('timestamp'), str) else datetime.now(),
                    msg['device_id'],
                    float(msg.get('value', 0.0)),
                    int(msg.get('label', 0))
                )
                for msg in self.batch
            ]
            
            # Batch insert
            execute_values(
                cursor,
                "INSERT INTO iot_data (ts, device_id, value, label) VALUES %s",
                data_tuples
            )
            
            self.db_conn.commit()
            self.total_inserts += len(self.batch)
            logger.info(f"Inserted {len(self.batch)} records. Total: {self.total_inserts}")
            
            self.batch = []
            self.last_insert_time = time.time()
            
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            self.db_conn.rollback()
        finally:
            cursor.close()
    
    def run(self):
        """Main collector loop"""
        if not self.connect_kafka():
            sys.exit(1)
        
        if not self.connect_db():
            sys.exit(1)
        
        if not self.create_tables():
            sys.exit(1)
        
        logger.info(f"Starting collection from Kafka topic: {KAFKA_TOPIC}")
        logger.info(f"Batch size: {BATCH_SIZE}, insert interval: {INSERT_INTERVAL_SECONDS}s")
        
        try:
            for message in self.kafka_consumer:
                try:
                    # Parse message
                    data = message.value
                    
                    # Add device_id if not present
                    if 'device_id' not in data:
                        data['device_id'] = f"device_{self.total_messages % 2400}"
                    
                    self.batch.append(data)
                    self.total_messages += 1
                    
                    # Check if we should insert
                    time_since_last_insert = time.time() - self.last_insert_time
                    should_insert = (
                        len(self.batch) >= BATCH_SIZE or 
                        time_since_last_insert >= INSERT_INTERVAL_SECONDS
                    )
                    
                    if should_insert:
                        self.insert_batch()
                    
                    if self.total_messages % 100 == 0:
                        logger.info(f"Progress: {self.total_messages} messages processed")
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.error(f"Collector error: {e}")
        finally:
            # Insert any remaining data
            if self.batch:
                self.insert_batch()
            
            logger.info(f"Final stats: {self.total_messages} messages, {self.total_inserts} inserts")
            
            if self.kafka_consumer:
                self.kafka_consumer.close()
            if self.db_conn:
                self.db_conn.close()

if __name__ == '__main__':
    collector = KafkaToTimescaleDB()
    collector.run()

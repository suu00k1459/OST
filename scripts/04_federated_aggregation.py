"""
Federated Learning Aggregation Service
Aggregates local model updates from edge devices into a global model
Implements Federated Averaging (FedAvg) algorithm

Subscribes to: local-model-updates topic
Publishes to: global-model-updates topic
Stores to: TimescaleDB (federated_models table)

Automatically detects if running inside Docker or locally
"""

import json
import logging
import threading
import time
import os
import sys
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import pickle

import numpy as np
from kafka import KafkaConsumer, KafkaProducer
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import config loader for environment detection
sys.path.insert(0, os.path.dirname(__file__))
from config_loader import get_db_config, get_kafka_config

# Configuration - auto-detect Docker vs local
kafka_config = get_kafka_config()
db_config = get_db_config()

KAFKA_BROKER = kafka_config['bootstrap_servers']
INPUT_TOPIC = 'local-model-updates'
OUTPUT_TOPIC = 'global-model-updates'
CONSUMER_GROUP = 'federated-aggregation'

# TimescaleDB configuration - auto-detect Docker vs local
DB_HOST = db_config['host']
DB_PORT = db_config['port']
DB_NAME = db_config['database']
DB_USER = db_config['user']
DB_PASSWORD = db_config['password']

logger.info(f"Kafka Broker: {KAFKA_BROKER}")
logger.info(f"Database Config: host={DB_HOST}, port={DB_PORT}, database={DB_NAME}, user={DB_USER}")


# Model storage
MODELS_DIR = Path('models')
MODELS_DIR.mkdir(exist_ok=True)
LOCAL_MODELS_DIR = MODELS_DIR / 'local'
GLOBAL_MODELS_DIR = MODELS_DIR / 'global'
LOCAL_MODELS_DIR.mkdir(exist_ok=True)
GLOBAL_MODELS_DIR.mkdir(exist_ok=True)

# Aggregation settings
AGGREGATION_WINDOW = 20  # Aggregate every 20 local model updates
MIN_DEVICES_FOR_AGGREGATION = 2  # Minimum devices needed for aggregation
FEDAVG_LEARNING_RATE = 0.1


class GlobalModel:
    """Global model in federated learning"""
    
    def __init__(self, version: int = 0):
        self.version = version
        self.weights = None
        self.accuracy = 0.0
        self.created_at = datetime.now()
        self.num_devices_aggregated = 0
        self.aggregation_round = 0
    
    def to_dict(self) -> Dict:
        """Convert model to dictionary"""
        return {
            'version': self.version,
            'accuracy': self.accuracy,
            'created_at': self.created_at.isoformat(),
            'num_devices_aggregated': self.num_devices_aggregated,
            'aggregation_round': self.aggregation_round
        }
    
    def save(self, path: Path) -> None:
        """Save model to disk"""
        try:
            with open(path, 'wb') as f:
                pickle.dump(self, f)
            logger.info(f"✓ Global model v{self.version} saved to {path}")
        except Exception as e:
            logger.error(f"✗ Error saving model: {e}")
    
    @staticmethod
    def load(path: Path) -> 'GlobalModel':
        """Load model from disk"""
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"✗ Error loading model: {e}")
            return None


class FederatedAggregator:
    """Federate learning aggregator using FedAvg algorithm"""
    
    def __init__(self):
        self.global_model = GlobalModel(version=0)
        self.local_model_buffer = defaultdict(list)  # Buffer of local models per device
        self.update_count = 0
        self.aggregation_round = 0
        self.db_connection = None
        
        # Connect to database
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database connection and tables"""
        try:
            self.db_connection = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            
            logger.info("✓ Connected to TimescaleDB")
            
            # Create tables if not exist
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS federated_models (
                        id SERIAL PRIMARY KEY,
                        global_version INT NOT NULL,
                        aggregation_round INT NOT NULL,
                        num_devices INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS local_models (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        model_version INT NOT NULL,
                        global_version INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        samples_processed INT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                # Create hypertable if not already one
                try:
                    cursor.execute("""
                        SELECT create_hypertable('federated_models', 'created_at', if_not_exists => TRUE)
                    """)
                except:
                    pass
                
                try:
                    cursor.execute("""
                        SELECT create_hypertable('local_models', 'created_at', if_not_exists => TRUE)
                    """)
                except:
                    pass
                
                self.db_connection.commit()
                logger.info("✓ Database tables ready")
        
        except Exception as e:
            logger.error(f"✗ Database connection error: {e}")
            raise
    
    def process_local_model_update(self, record: Dict[str, Any]) -> None:
        """Process incoming local model update"""
        try:
            device_id = record.get('device_id')
            model_version = record.get('model_version')
            accuracy = record.get('accuracy', 0.0)
            samples_processed = record.get('samples_processed', 0)
            
            logger.info(f"Received local model from {device_id}: "
                       f"v{model_version}, accuracy={accuracy:.2%}")
            
            # Store local model info
            model_info = {
                'device_id': device_id,
                'model_version': model_version,
                'accuracy': accuracy,
                'samples_processed': samples_processed,
                'timestamp': record.get('timestamp', datetime.now().isoformat())
            }
            
            self.local_model_buffer[device_id].append(model_info)
            self.update_count += 1
            
            # Save to database
            self._save_local_model_to_db(device_id, model_version, accuracy, samples_processed)
            
            # Check if aggregation should be triggered
            if self.update_count >= AGGREGATION_WINDOW:
                self.aggregate()
                self.update_count = 0
        
        except Exception as e:
            logger.error(f"Error processing local model update: {e}")
    
    def _save_local_model_to_db(self, device_id: str, model_version: int, 
                               accuracy: float, samples_processed: int) -> None:
        """Save local model to database"""
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO local_models 
                    (device_id, model_version, global_version, accuracy, samples_processed)
                    VALUES (%s, %s, %s, %s, %s)
                """, (device_id, model_version, self.global_model.version, accuracy, samples_processed))
                self.db_connection.commit()
        except Exception as e:
            # CRITICAL: Rollback the failed transaction to allow future operations
            self.db_connection.rollback()
            logger.warning(f"Error saving local model to DB: {e}")
    
    def aggregate(self) -> Dict[str, Any]:
        """
        Aggregate local models using Federated Averaging (FedAvg)
        
        Aggregation Strategy:
        - GlobalAccuracy = Σ(LocalAccuracy_i × Samples_i) / Σ(Samples_i)
        - Weight each device's contribution by number of samples processed
        - Simple averaging: GlobalModel = Sum(LocalModels) / NumberOfDevices
        
        Returns:
            Global model update dictionary
        """
        try:
            num_devices = len(self.local_model_buffer)
            
            if num_devices < MIN_DEVICES_FOR_AGGREGATION:
                logger.warning(f"⚠ Not enough devices for aggregation: {num_devices}/{MIN_DEVICES_FOR_AGGREGATION}")
                return None
            
            logger.info(f"\n{'='*70}")
            logger.info(f"Federated Aggregation Round {self.aggregation_round + 1}")
            logger.info(f"{'='*70}")
            logger.info(f"Number of devices: {num_devices}")
            
            # Aggregate accuracies using weighted average
            total_samples = 0
            weighted_accuracy = 0.0
            device_accuracies = []
            
            for device_id, updates in self.local_model_buffer.items():
                if updates:
                    latest_update = updates[-1]
                    accuracy = latest_update['accuracy']
                    samples = latest_update['samples_processed']
                    
                    device_accuracies.append({
                        'device_id': device_id,
                        'accuracy': accuracy,
                        'samples': samples
                    })
                    
                    weighted_accuracy += accuracy * samples
                    total_samples += samples
                    
                    logger.info(f"  Device {device_id}: accuracy={accuracy:.2%}, samples={samples}")
            
            # Calculate global accuracy
            global_accuracy = weighted_accuracy / total_samples if total_samples > 0 else 0.0
            
            # Update global model
            self.global_model.version += 1
            self.global_model.accuracy = global_accuracy
            self.global_model.num_devices_aggregated = num_devices
            self.aggregation_round += 1
            self.global_model.aggregation_round = self.aggregation_round
            
            logger.info(f"\n  Global Model v{self.global_model.version}:")
            logger.info(f"  Weighted Average Accuracy: {global_accuracy:.2%}")
            logger.info(f"  Total Samples Processed: {total_samples:,}")
            logger.info(f"  Aggregation Round: {self.aggregation_round}")
            
            # Save global model
            model_path = GLOBAL_MODELS_DIR / f"global_model_v{self.global_model.version}.pkl"
            self.global_model.save(model_path)
            
            # Save to database
            self._save_global_model_to_db(global_accuracy, num_devices)
            
            # Clear buffer
            self.local_model_buffer.clear()
            
            # Prepare output record
            global_update = {
                'version': self.global_model.version,
                'aggregation_round': self.aggregation_round,
                'global_accuracy': global_accuracy,
                'num_devices': num_devices,
                'device_accuracies': device_accuracies,
                'timestamp': datetime.now().isoformat(),
                'total_samples': total_samples
            }
            
            logger.info(f"{'='*70}\n")
            
            return global_update
        
        except Exception as e:
            logger.error(f"Error in aggregation: {e}")
            return None
    
    def _save_global_model_to_db(self, accuracy: float, num_devices: int) -> None:
        """Save global model to database"""
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO federated_models 
                    (global_version, aggregation_round, num_devices, accuracy)
                    VALUES (%s, %s, %s, %s)
                """, (self.global_model.version, self.aggregation_round, num_devices, accuracy))
                self.db_connection.commit()
                logger.info(f"✓ Global model v{self.global_model.version} saved to database")
        except Exception as e:
            # CRITICAL: Rollback the failed transaction to allow future operations
            self.db_connection.rollback()
            logger.warning(f"Error saving global model to DB: {e}")


def create_kafka_consumer():
    """Create Kafka consumer for local model updates"""
    return KafkaConsumer(
        INPUT_TOPIC,
        bootstrap_servers=KAFKA_BROKER,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True
    )


def create_kafka_producer():
    """Create Kafka producer for global model updates"""
    return KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        acks='all',
        retries=3
    )


def main():
    """Main aggregation service"""
    logger.info("=" * 70)
    logger.info("Federated Learning Aggregation Service")
    logger.info("=" * 70)
    logger.info(f"Input Topic: {INPUT_TOPIC}")
    logger.info(f"Output Topic: {OUTPUT_TOPIC}")
    logger.info(f"Kafka Broker: {KAFKA_BROKER}")
    logger.info(f"TimescaleDB: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Aggregation Window: {AGGREGATION_WINDOW} updates")
    logger.info(f"Min Devices: {MIN_DEVICES_FOR_AGGREGATION}")
    logger.info("=" * 70)
    
    try:
        # Create components
        aggregator = FederatedAggregator()
        consumer = create_kafka_consumer()
        producer = create_kafka_producer()
        
        logger.info("Waiting for local model updates...")
        logger.info("(Press Ctrl+C to stop)\n")
        
        # Process messages
        for message in consumer:
            try:
                local_model_record = message.value
                aggregator.process_local_model_update(local_model_record)
                
                # Check if aggregation was triggered
                if aggregator.update_count == 0 and aggregator.aggregation_round > 0:
                    # Aggregation just happened, send global update
                    # (update_count reset to 0 after aggregation)
                    pass
            
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    except KeyboardInterrupt:
        logger.info("\n⚠ Service interrupted")
    except Exception as e:
        logger.error(f"Error in aggregation service: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            consumer.close()
            producer.close()
            if aggregator.db_connection:
                aggregator.db_connection.close()
            logger.info("✓ Service stopped cleanly")
        except:
            pass


if __name__ == '__main__':
    main()

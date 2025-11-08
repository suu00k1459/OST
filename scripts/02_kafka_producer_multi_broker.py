"""
Multi-Broker Kafka Producer for Edge-IIoT
Distributes 2400 IoT devices across 4 Kafka brokers (600 devices per broker)
Each broker receives data from its assigned device subset

Simulates real-world distributed IoT scenario where:
- Broker 1 (port 29092): Devices 0-599
- Broker 2 (port 29093): Devices 600-1199
- Broker 3 (port 29094): Devices 1200-1799
- Broker 4 (port 29095): Devices 1800-2399

Usage:
    python scripts/02_kafka_producer_multi_broker.py --source data/processed --rate 10

The producer maintains separate connections to all 4 brokers and distributes
device messages based on device_id modulo 4.
"""

import json
import time
import argparse
import random
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Generator, Optional, Tuple

import pandas as pd
import numpy as np
from kafka import KafkaProducer
from kafka.errors import KafkaError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiBrokerProducer:
    """Kafka producer distributing data across 4 brokers"""
    
    # Broker configuration (Docker internal addresses)
    BROKERS = {
        'broker_1': 'localhost:9092',
        'broker_2': 'localhost:9093',
        'broker_3': 'localhost:9094',
        'broker_4': 'localhost:9095'
    }
    
    BROKER_BOOTSTRAP_SERVERS = "localhost:9092,localhost:9093,localhost:9094,localhost:9095"
    
    # Device distribution
    DEVICES_PER_BROKER = 600
    TOTAL_DEVICES = 2400
    
    def __init__(self, 
                 topic: str = 'edge-iiot-stream',
                 rows_per_second: int = 10,
                 repeat: bool = True):
        """
        Initialize Multi-Broker Kafka producer
        
        Args:
            topic: Target topic name (shared across all brokers)
            rows_per_second: Streaming rate
            repeat: Loop and restart from beginning when finished
        """
        self.topic = topic
        self.rows_per_second = rows_per_second
        self.interval = 1.0 / rows_per_second
        self.repeat = repeat
        
        # Single producer connecting to all brokers
        self.producer = None
        self.messages_sent = 0
        self.errors = 0
        self.start_time = None
        
        # Device distribution mapping
        self.device_to_broker = {}  # Maps device_id -> broker_index (0-3)
        
        logger.info(f"Multi-Broker Producer initialized:")
        logger.info(f"  Brokers: {self.BROKER_BOOTSTRAP_SERVERS}")
        logger.info(f"  Topic: {self.topic}")
        logger.info(f"  Device distribution: 600 devices per broker")
        logger.info(f"  Broker 1: devices_0-599")
        logger.info(f"  Broker 2: devices_600-1199")
        logger.info(f"  Broker 3: devices_1200-1799")
        logger.info(f"  Broker 4: devices_1800-2399")
        
    def get_broker_for_device(self, device_id: str) -> int:
        """
        Get broker index (0-3) for a device based on device_id
        Uses modulo 4 to distribute devices across 4 brokers
        
        Args:
            device_id: Device identifier (e.g., 'device_0')
            
        Returns:
            Broker index (0-3)
        """
        # Extract numeric part from device_id (e.g., 'device_0' -> 0)
        try:
            device_num = int(device_id.split('_')[-1])
        except (ValueError, IndexError):
            # Fallback: use hash if format is unexpected
            device_num = hash(device_id) % self.TOTAL_DEVICES
        
        broker_idx = (device_num // self.DEVICES_PER_BROKER) % 4
        return broker_idx
    
    def connect(self):
        """Connect to all brokers in cluster"""
        try:
            logger.info(f"Connecting to multi-broker cluster...")
            logger.info(f"Bootstrap servers: {self.BROKER_BOOTSTRAP_SERVERS}")
            
            self.producer = KafkaProducer(
                bootstrap_servers=self.BROKER_BOOTSTRAP_SERVERS.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=5,
                max_in_flight_requests_per_connection=1,
                request_timeout_ms=60000,
                partitioner=self._partition_by_broker
            )
            logger.info(f"Successfully connected to all 4 Kafka brokers")
            
        except Exception as e:
            logger.error(f"Failed to connect to Kafka brokers: {e}")
            logger.error(f"Ensure Docker containers are running:")
            logger.error(f"  docker-compose up -d")
            raise
    
    def _partition_by_broker(self, key, all_partitions, available_partitions):
        """Custom partitioner to route messages to appropriate broker"""
        if key is None:
            return random.choice(available_partitions)
        
        # Extract broker index from key
        try:
            broker_idx = int(key)
            # Route to partition matching broker
            for partition in all_partitions:
                if partition.leader == broker_idx:
                    return partition
        except (ValueError, TypeError):
            pass
        
        return random.choice(available_partitions)
    
    def discover_device_files(self, directory: str) -> List[str]:
        """
        Discover all device_*.csv files in directory
        
        Args:
            directory: Path to directory
            
        Returns:
            List of device file paths sorted by device number
        """
        data_dir = Path(directory)
        device_files = sorted(data_dir.glob('device_*.csv'), 
                            key=lambda x: int(x.stem.split('_')[-1]))
        
        if not device_files:
            logger.warning(f"No device files found in {directory}")
            return []
        
        logger.info(f"Discovered {len(device_files)} device files")
        return [str(f) for f in device_files]
    
    def load_and_distribute_devices(self, directory: str) -> Dict[int, List[Tuple[str, pd.DataFrame]]]:
        """
        Load device files and organize by broker
        
        Args:
            directory: Path to device CSV files
            
        Returns:
            Dictionary mapping broker_idx -> list of (device_id, dataframe) tuples
        """
        device_files = self.discover_device_files(directory)
        
        if not device_files:
            logger.error(f"No CSV files found in {directory}")
            return {}
        
        # Organize devices by broker
        broker_devices = {0: [], 1: [], 2: [], 3: []}
        
        for device_file in device_files:
            device_path = Path(device_file)
            device_id = device_path.stem  # e.g., "device_0"
            
            try:
                df = pd.read_csv(device_file, nrows=100)  # Limit rows for demo
                broker_idx = self.get_broker_for_device(device_id)
                broker_devices[broker_idx].append((device_id, df))
                self.device_to_broker[device_id] = broker_idx
                
                logger.info(f"Loaded {device_id}: {len(df)} rows → Broker {broker_idx + 1}")
                
            except Exception as e:
                logger.error(f"Failed to load {device_path.name}: {e}")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Device Distribution Summary:")
        logger.info(f"{'='*70}")
        for broker_idx in range(4):
            num_devices = len(broker_devices[broker_idx])
            device_ids = [dev_id for dev_id, _ in broker_devices[broker_idx]]
            if device_ids:
                logger.info(f"Broker {broker_idx + 1} (port {9092 + broker_idx}): {num_devices} devices")
                logger.info(f"  Device range: {device_ids[0]} - {device_ids[-1]}")
            else:
                logger.info(f"Broker {broker_idx + 1}: No devices")
        logger.info(f"{'='*70}\n")
        
        return broker_devices
    
    def stream_from_broker_devices(self, broker_devices: Dict[int, List[Tuple[str, pd.DataFrame]]]) -> Generator:
        """
        Stream data from devices, randomly rotating through all devices
        
        Args:
            broker_devices: Dictionary of devices organized by broker
            
        Yields:
            Kafka messages with device_id and broker info
        """
        # Flatten all devices
        all_devices = []
        for broker_idx in range(4):
            for device_id, df in broker_devices[broker_idx]:
                for _, row in df.iterrows():
                    record = row.to_dict()
                    # Convert to JSON-serializable types
                    for key, value in list(record.items()):
                        if pd.isna(value):
                            record[key] = None
                        elif isinstance(value, (np.integer, np.floating)):
                            record[key] = float(value)
                        elif isinstance(value, np.bool_):
                            record[key] = bool(value)
                    
                    all_devices.append({
                        'device_id': device_id,
                        'broker_idx': broker_idx,
                        'record': record
                    })
        
        if not all_devices:
            logger.error("No device data loaded")
            return
        
        logger.info(f"Ready to stream {len(all_devices)} total device records")
        
        iteration = 0
        while True:
            iteration += 1
            
            # Randomly select a device record
            selected = random.choice(all_devices)
            device_id = selected['device_id']
            broker_idx = selected['broker_idx']
            record = selected['record']
            
            # Get metric value
            metric_value = record.get('tcp.ack', record.get('tcp.seq', 0.0))
            if metric_value is None or metric_value == 0.0:
                metric_value = 0.0
            
            message = {
                'device_id': device_id,
                'broker': f'broker_{broker_idx + 1}',
                'timestamp': datetime.now().isoformat(),
                'data': float(metric_value),
                'raw_features': record
            }
            
            yield message, device_id, broker_idx
    
    def send_messages(self, broker_devices: Dict[int, List[Tuple[str, pd.DataFrame]]]):
        """
        Main streaming loop - sends messages to Kafka
        
        Args:
            broker_devices: Dictionary of devices organized by broker
        """
        if not self.producer:
            raise RuntimeError("Producer not connected. Call connect() first.")
        
        self.start_time = time.time()
        message_generator = self.stream_from_broker_devices(broker_devices)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Starting message stream at {self.rows_per_second} msgs/sec")
        logger.info(f"Press Ctrl+C to stop")
        logger.info(f"{'='*70}\n")
        
        try:
            last_log_time = time.time()
            msg_count_since_log = 0
            
            for message, device_id, broker_idx in message_generator:
                try:
                    # Send message with device_id as key (for partitioning)
                    future = self.producer.send(
                        self.topic,
                        value=message,
                        key=device_id.encode('utf-8'),
                        partition=broker_idx  # Route to correct broker
                    )
                    future.get(timeout=10)
                    
                    self.messages_sent += 1
                    msg_count_since_log += 1
                    
                    # Log progress every 100 messages
                    if self.messages_sent % 100 == 0:
                        elapsed = time.time() - self.start_time
                        actual_rate = self.messages_sent / elapsed
                        logger.info(f"Progress: {self.messages_sent} msgs sent | "
                                  f"Device: {device_id} → Broker {broker_idx + 1} | "
                                  f"Actual rate: {actual_rate:.2f} msgs/sec")
                    
                    # Throttle to desired rate
                    time.sleep(self.interval)
                    
                except KafkaError as e:
                    logger.error(f"Kafka error: {e}")
                    self.errors += 1
                    if self.errors > 10:
                        logger.error(f"Too many errors ({self.errors}). Stopping.")
                        break
                
        except KeyboardInterrupt:
            logger.info(f"\nShutdown signal received")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Gracefully shutdown producer and log statistics"""
        if self.producer:
            self.producer.flush()
            self.producer.close()
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        logger.info(f"\n{'='*70}")
        logger.info(f"PRODUCER SHUTDOWN")
        logger.info(f"{'='*70}")
        logger.info(f"Total messages sent: {self.messages_sent}")
        logger.info(f"Total errors: {self.errors}")
        logger.info(f"Elapsed time: {elapsed:.2f} seconds")
        if elapsed > 0:
            logger.info(f"Average rate: {self.messages_sent / elapsed:.2f} msgs/sec")
        logger.info(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description='Multi-Broker Edge-IIoT Kafka Producer')
    parser.add_argument('--source', type=str, default='data/processed',
                       help='Path to device CSV files or directory')
    parser.add_argument('--rate', type=int, default=10,
                       help='Messages per second')
    parser.add_argument('--topic', type=str, default='edge-iiot-stream',
                       help='Kafka topic name')
    
    args = parser.parse_args()
    
    producer = MultiBrokerProducer(
        topic=args.topic,
        rows_per_second=args.rate
    )
    
    try:
        producer.connect()
        broker_devices = producer.load_and_distribute_devices(args.source)
        
        if broker_devices:
            producer.send_messages(broker_devices)
        else:
            logger.error("Failed to load device data")
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

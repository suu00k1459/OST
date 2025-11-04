"""
Edge-IIoT Kafka Producer
Real-time streaming of preprocessed Edge-IIoT data to Kafka

Usage:
    python kafka_producer.py --broker localhost:9092 --topic edge-iiot-stream --rate 10 --source path/to/data
    
Examples:
    # Stream device-specific file
    python scripts/kafka_producer.py --source data/processed/device_0.csv --rate 10
    
    # Stream merged data
    python scripts/kafka_producer.py --source data/processed/merged_data.csv --rate 10
    
    # Auto-discover and stream all devices
    python scripts/kafka_producer.py --source data/processed --rate 5 --mode all-devices
"""

import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Generator, Optional
import sys

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


class EdgeIIoTProducer:
    """Kafka producer for Edge-IIoT streaming data"""
    
    def __init__(self, 
                 bootstrap_servers: str = 'localhost:9092',
                 topic: str = 'edge-iiot-stream',
                 rows_per_second: int = 10,
                 repeat: bool = False):
        """
        Initialize Kafka producer
        
        Args:
            bootstrap_servers: Kafka broker address
            topic: Target topic name
            rows_per_second: Streaming rate
            repeat: Loop and restart from beginning when finished
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.rows_per_second = rows_per_second
        self.interval = 1.0 / rows_per_second
        self.producer = None
        self.messages_sent = 0
        self.errors = 0
        self.start_time = None
        self.repeat = repeat
        self.cycle_count = 0
        
    def connect(self):
        """Connect to Kafka broker"""
        try:
            logger.info(f"Attempting to connect to Kafka broker: {self.bootstrap_servers}...")
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=5,
                max_in_flight_requests_per_connection=1,
                request_timeout_ms=60000
            )
            logger.info(f"Successfully connected to Kafka broker: {self.bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            logger.error(f"Make sure Docker Kafka is running on {self.bootstrap_servers}")
            logger.error(f"Run: docker-compose up -d")
            raise
    
    def stream_from_csv(self, csv_file: str) -> Generator:
        """
        Stream data from CSV file (device-specific or merged)
        Repeats from beginning if repeat is enabled
        
        Args:
            csv_file: Path to CSV file
            
        Yields:
            Kafka messages
        """
        try:
            csv_path = Path(csv_file)
            if not csv_path.exists():
                logger.error(f"✗ File not found: {csv_file}")
                return
            
            df = pd.read_csv(csv_file)
            total_rows = len(df)
            
            cycle = 1
            while True:
                if cycle > 1:
                    logger.info(f"\n{'='*70}")
                    logger.info(f"✓ Restarting cycle {cycle}")
                    logger.info(f"{'='*70}\n")
                    self.cycle_count = cycle
                
                if cycle == 1:
                    logger.info(f"✓ Loaded {total_rows} records from {csv_path.name}")
                    logger.info(f"  Columns: {list(df.columns)}")
                
                for idx, row in df.iterrows():
                    record = row.to_dict()
                    
                    # Convert to JSON-serializable types
                    for key, value in list(record.items()):
                        if pd.isna(value):
                            record[key] = None
                        elif isinstance(value, (np.integer, np.floating)):
                            record[key] = float(value)
                        elif isinstance(value, np.bool_):
                            record[key] = bool(value)
                    
                    # Extract device_id or use default
                    device_id = str(record.get('device_id', 'unknown'))
                    
                    # Calculate a meaningful metric from the data
                    # Use tcp.ack as the primary metric (it's commonly present)
                    metric_value = record.get('tcp.ack', 0.0)
                    if metric_value is None or metric_value == 0.0:
                        # Fallback to other common numeric fields
                        metric_value = record.get('tcp.seq', record.get('tcp.srcport', 0.0))
                    
                    message = {
                        'device_id': device_id,
                        'timestamp': datetime.now().isoformat(),
                        'data': float(metric_value) if metric_value is not None else 0.0,
                        'raw_features': record  # Keep full record for advanced analytics
                    }
                    
                    yield message
                
                # If repeat is disabled, exit after one pass
                if not self.repeat:
                    break
                
                cycle += 1
                
        except Exception as e:
            logger.error(f"✗ Error reading CSV file: {e}")
            raise
    
    def discover_device_files(self, directory: str) -> List[str]:
        """
        Discover all device_*.csv files in directory
        
        Args:
            directory: Path to directory
            
        Returns:
            List of device file paths
        """
        data_dir = Path(directory)
        device_files = sorted(data_dir.glob('device_*.csv'))
        
        if not device_files:
            logger.warning(f"⚠ No device files found in {directory}")
            # Try merged_data.csv as fallback
            merged_file = data_dir / 'merged_data.csv'
            if merged_file.exists():
                logger.info(f"✓ Using merged_data.csv instead")
                return [str(merged_file)]
            return []
        
        logger.info(f"✓ Discovered {len(device_files)} device files:")
        for file in device_files:
            logger.info(f"  - {file.name}")
        
        return [str(f) for f in device_files]
    
    def stream_from_directory(self, directory: str) -> Generator:
        """
        Stream data from all device files in directory
        Repeats from beginning if repeat is enabled
        
        Args:
            directory: Path to directory containing device_*.csv files
            
        Yields:
            Kafka messages
        """
        device_files = self.discover_device_files(directory)
        
        if not device_files:
            logger.error(f"✗ No CSV files found in {directory}")
            return
        
        cycle = 1
        while True:
            if cycle > 1:
                logger.info(f"\n{'='*70}")
                logger.info(f"✓ Restarting cycle {cycle}")
                logger.info(f"✓ Streaming from {len(device_files)} device file(s)")
                logger.info(f"{'='*70}\n")
                self.cycle_count = cycle
            else:
                logger.info(f"✓ Streaming from {len(device_files)} device file(s)")
            
            for device_file in device_files:
                if cycle == 1:
                    logger.info(f"✓ Starting stream from {Path(device_file).name}")
                
                for message in self.stream_from_csv(device_file):
                    yield message
            
            # If repeat is disabled, exit after one pass
            if not self.repeat:
                break
            
            cycle += 1
    
    def send_message(self, message: Dict):
        """Send message to Kafka topic"""
        try:
            future = self.producer.send(self.topic, value=message)
            
            # Wait for send to complete
            future.get(timeout=10)
            
            self.messages_sent += 1
            
            if self.messages_sent % 50 == 1:
                elapsed = time.time() - self.start_time
                rate = self.messages_sent / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {self.messages_sent} msgs sent | "
                           f"Device: {message.get('device_id')} | "
                           f"Actual rate: {rate:.2f} msgs/sec")
            
        except KafkaError as e:
            logger.error(f"✗ Failed to send message: {e}")
            self.errors += 1
    
    def run(self, data_source: str, mode: str = 'single', duration: Optional[int] = None):
        """
        Run streaming producer
        
        Args:
            data_source: CSV file path or directory
            mode: 'single' or 'all-devices'
            duration: Maximum duration in seconds (None = infinite)
        """
        try:
            self.connect()
            
            logger.info("=" * 70)
            logger.info("✓ Edge-IIoT Kafka Producer Started")
            logger.info("=" * 70)
            logger.info(f"  Broker: {self.bootstrap_servers}")
            logger.info(f"  Topic: {self.topic}")
            logger.info(f"  Rate: {self.rows_per_second} rows/second")
            logger.info(f"  Mode: {mode}")
            logger.info(f"  Repeat: {'ON (infinite loop)' if self.repeat else 'OFF (one pass)'}")
            logger.info(f"  Duration: {duration or 'infinite'} seconds")
            logger.info(f"  Source: {data_source}")
            logger.info("=" * 70)
            
            self.start_time = time.time()
            
            # Determine source type and get stream generator
            source_path = Path(data_source)
            
            if source_path.is_dir():
                logger.info(f"✓ Source is directory")
                stream_generator = self.stream_from_directory(data_source)
            elif source_path.is_file() and data_source.endswith('.csv'):
                logger.info(f"✓ Source is CSV file")
                stream_generator = self.stream_from_csv(data_source)
            else:
                logger.error(f"✗ Invalid source: {data_source}")
                logger.error(f"  Must be a CSV file or directory containing CSV files")
                return
            
            # Stream data
            for message in stream_generator:
                self.send_message(message)
                time.sleep(self.interval)
                
                # Check duration limit
                if duration and (time.time() - self.start_time) > duration:
                    logger.info(f"✓ Duration limit reached ({duration}s)")
                    break
            
        except KeyboardInterrupt:
            logger.info("\n⚠ Stream interrupted by user (Ctrl+C)")
        except Exception as e:
            logger.error(f"✗ Error in stream producer: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.close()
    
    def close(self):
        """Close producer and report statistics"""
        if self.producer:
            self.producer.close()
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        success_rate = ((self.messages_sent - self.errors) / self.messages_sent * 100) if self.messages_sent > 0 else 0
        actual_rate = self.messages_sent / elapsed if elapsed > 0 else 0
        
        logger.info("=" * 70)
        logger.info("✓ Stream Producer Closed")
        logger.info("=" * 70)
        logger.info(f"Total messages sent: {self.messages_sent:,}")
        logger.info(f"Errors encountered: {self.errors}")
        logger.info(f"Success rate: {success_rate:.2f}%")
        logger.info(f"Actual rate: {actual_rate:.2f} msgs/sec")
        logger.info(f"Total time: {elapsed:.2f}s")
        if self.cycle_count > 1:
            logger.info(f"Cycles completed: {self.cycle_count}")
        logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Edge-IIoT Kafka Producer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream single device file (one pass)
  python scripts/kafka_producer.py --source notebooks/edge_iiot_processed/device_0.csv --rate 10
  
  # Stream single device file (infinite loop)
  python scripts/kafka_producer.py --source notebooks/edge_iiot_processed/device_0.csv --rate 10 --repeat
  
  # Stream all devices from directory (one pass)
  python scripts/kafka_producer.py --source notebooks/edge_iiot_processed --mode all-devices --rate 10
  
  # Stream all devices (infinite loop) - RECOMMENDED
  python scripts/kafka_producer.py --source notebooks/edge_iiot_processed --mode all-devices --rate 10 --repeat
  
  # Stream merged data with custom broker
  python scripts/kafka_producer.py --source notebooks/edge_iiot_processed/merged_data.csv \\
                                   --broker localhost:9092 --rate 5 --repeat
        """
    )
    
    parser.add_argument('--source', 
                       required=True,
                       help='CSV file path or directory containing device_*.csv files')
    parser.add_argument('--broker', 
                       default='localhost:9092',
                       help='Kafka broker address (default: localhost:9092 - use this for Docker)')
    parser.add_argument('--topic', 
                       default='edge-iiot-stream',
                       help='Target Kafka topic (default: edge-iiot-stream)')
    parser.add_argument('--rate', 
                       type=int, 
                       default=10,
                       help='Messages per second (default: 10)')
    parser.add_argument('--mode',
                       choices=['single', 'all-devices'],
                       default='single',
                       help='Streaming mode (default: single)')
    parser.add_argument('--duration', 
                       type=int,
                       help='Duration in seconds (optional)')
    parser.add_argument('--repeat',
                       action='store_true',
                       help='Loop and restart from beginning when finished (infinite loop)')
    
    args = parser.parse_args()
    
    # Validate source exists
    source_path = Path(args.source)
    if not source_path.exists():
        logger.error(f"✗ Source not found: {args.source}")
        sys.exit(1)
    
    # Create and run producer
    producer = EdgeIIoTProducer(
        bootstrap_servers=args.broker,
        topic=args.topic,
        rows_per_second=args.rate,
        repeat=args.repeat
    )
    
    producer.run(args.source, mode=args.mode, duration=args.duration)


if __name__ == '__main__':
    main()

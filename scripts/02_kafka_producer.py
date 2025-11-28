"""
Single-Broker Kafka Producer for Edge-IIoT
Streams 2400 IoT devices into a single Kafka broker (kafka-broker-1:9092).

Usage:
    python scripts/02_kafka_producer.py --source data/processed --rate 10
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

# -----------------------------------------------------
# LOGGING
# -----------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SingleBrokerProducer:
    """Kafka producer streaming data to a single broker."""

    _IS_DOCKER = os.path.exists("/.dockerenv")

    # Allow override via environment (keeps everything aligned with Dockerfile/compose)
    ENV_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

    if ENV_BOOTSTRAP:
        BROKER_BOOTSTRAP_SERVERS = ENV_BOOTSTRAP
        logger.info(f"Using KAFKA_BOOTSTRAP_SERVERS from environment: {BROKER_BOOTSTRAP_SERVERS}")
    else:
        if _IS_DOCKER:
            BROKER_BOOTSTRAP_SERVERS = "kafka-broker-1:9092"
        else:
            BROKER_BOOTSTRAP_SERVERS = "localhost:9092"

    TOTAL_DEVICES = 2400

    def __init__(
        self,
        topic: str = "edge-iiot-stream",
        rows_per_second: int = 10,
        repeat: bool = True,
    ):
        self.topic = topic
        self.rows_per_second = rows_per_second
        self.interval = 1.0 / rows_per_second
        self.repeat = repeat

        self.producer: Optional[KafkaProducer] = None
        self.messages_sent = 0
        self.errors = 0
        self.start_time: Optional[float] = None

        self.device_to_broker: Dict[str, int] = {}

        logger.info("Single-Broker Producer initialized:")
        logger.info(f"  Brokers bootstrap: {self.BROKER_BOOTSTRAP_SERVERS}")
        logger.info(f"  Topic: {self.topic}")
        logger.info("  Device distribution: All devices to Broker 1")

    # -------------------------------------------------
    # DEVICE → BROKER MAPPING
    # -------------------------------------------------
    def get_broker_for_device(self, device_id: str) -> int:
        """Map device_id (e.g. device_0) to broker index 0 (Single Broker)."""
        return 0

    # -------------------------------------------------
    # KAFKA CONNECTION
    # -------------------------------------------------
    def connect(self, max_retries: int = 30, retry_delay: int = 5) -> None:
        """Connect to Kafka with retry logic (more patient for startup)."""
        retry_count = 0
        last_error: Optional[Exception] = None

        while retry_count < max_retries:
            try:
                logger.info("Connecting to Kafka cluster...")
                logger.info(f"Bootstrap servers: {self.BROKER_BOOTSTRAP_SERVERS}")

                self.producer = KafkaProducer(
                    bootstrap_servers=self.BROKER_BOOTSTRAP_SERVERS.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all",
                    retries=5,
                    max_in_flight_requests_per_connection=1,
                    request_timeout_ms=60000,
                    connections_max_idle_ms=30000,
                    reconnect_backoff_ms=5000,
                )
                logger.info("Successfully connected to Kafka")
                return
            except Exception as e:
                retry_count += 1
                last_error = e
                if retry_count < max_retries:
                    logger.warning(
                        "Producer connection attempt %d/%d failed: %s. "
                        "Retrying in %ds...",
                        retry_count,
                        max_retries,
                        e,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "Producer failed to connect after %d attempts: %s",
                        max_retries,
                        last_error,
                    )
                    raise


    # -------------------------------------------------
    # DATA LOADING & DISTRIBUTION
    # -------------------------------------------------
    def discover_device_files(self, directory: str) -> List[str]:
        data_dir = Path(directory)
        device_files = sorted(
            data_dir.glob("device_*.csv"),
            key=lambda x: int(x.stem.split("_")[-1]),
        )

        if not device_files:
            logger.warning(f"No device_*.csv files found in {directory}")
            return []

        logger.info(f"Discovered {len(device_files)} device files")
        return [str(f) for f in device_files]

    def load_and_distribute_devices(
        self, directory: str
    ) -> Dict[int, List[Tuple[str, pd.DataFrame]]]:
        device_files = self.discover_device_files(directory)
        if not device_files:
            logger.error(f"No CSV files found in {directory}")
            return {}

        broker_devices: Dict[int, List[Tuple[str, pd.DataFrame]]] = {
            0: [],
        }

        for device_file in device_files:
            device_path = Path(device_file)
            device_id = device_path.stem  # "device_123"
            try:
                df = pd.read_csv(device_file, nrows=100)
                broker_idx = 0
                broker_devices[broker_idx].append((device_id, df))
                self.device_to_broker[device_id] = broker_idx
                logger.info(
                    f"Loaded {device_id}: {len(df)} rows → Broker {broker_idx + 1}"
                )
            except Exception as e:
                logger.error(f"Failed to load {device_path.name}: {e}")

        logger.info("\n" + "=" * 70)
        logger.info("Device Distribution Summary:")
        for broker_idx in range(1):
            devices = broker_devices[broker_idx]
            num_devices = len(devices)
            if num_devices:
                device_ids = [d for d, _ in devices]
                logger.info(
                    f"Broker {broker_idx + 1}: {num_devices} devices "
                    f"({device_ids[0]} … {device_ids[-1]})"
                )
            else:
                logger.info(f"Broker {broker_idx + 1}: no devices")
        logger.info("=" * 70 + "\n")

        return broker_devices

    # -------------------------------------------------
    # STREAM GENERATOR
    # -------------------------------------------------
    def stream_from_broker_devices(
        self, broker_devices: Dict[int, List[Tuple[str, pd.DataFrame]]]
    ) -> Generator[Tuple[dict, str, int], None, None]:
        all_records: List[dict] = []

        for broker_idx in range(1):
            for device_id, df in broker_devices[broker_idx]:
                for _, row in df.iterrows():
                    record = row.to_dict()
                    for key, value in list(record.items()):
                        if pd.isna(value):
                            record[key] = None
                        elif isinstance(value, (np.integer, np.floating)):
                            record[key] = float(value)
                        elif isinstance(value, np.bool_):
                            record[key] = bool(value)

                    all_records.append(
                        {
                            "device_id": device_id,
                            "broker_idx": broker_idx,
                            "record": record,
                        }
                    )

        # Sort by timestamp to simulate real-time playback
        # Use 0 if 'ts' is missing to avoid crash
        all_records.sort(key=lambda x: x["record"].get("ts", 0))

        for item in all_records:
            yield item["record"], item["device_id"], item["broker_idx"]

    # -------------------------------------------------
    # MAIN RUN LOOP
    # -------------------------------------------------
    def run(self, directory: str) -> None:
        """Main loop: load data, connect, and stream."""
        self.connect()
        
        broker_devices = self.load_and_distribute_devices(directory)
        if not broker_devices or not broker_devices[0]:
            logger.error("No devices loaded. Exiting.")
            return

        logger.info(f"Starting stream at {self.rows_per_second} rows/sec...")
        self.start_time = time.time()

        try:
            while True:
                stream = self.stream_from_broker_devices(broker_devices)
                
                for record, device_id, broker_idx in stream:
                    # Send to Kafka
                    # We don't specify partition, let the partitioner decide (or round-robin)
                    self.producer.send(
                        self.topic,
                        value=record
                    )
                    
                    self.messages_sent += 1
                    
                    if self.messages_sent % 500 == 0:
                        elapsed = time.time() - self.start_time
                        rate = self.messages_sent / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"Sent {self.messages_sent} msgs | "
                            f"Last: {device_id} | "
                            f"Rate: {rate:.2f} msg/s"
                        )
                    
                    time.sleep(self.interval)

                if not self.repeat:
                    break
                
                logger.info("Finished one pass through data. Repeating...")

        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        except Exception as e:
            logger.error(f"Error in producer loop: {e}")
        finally:
            if self.producer:
                self.producer.flush()
                self.producer.close()
            logger.info("Producer closed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/processed", help="Data directory")
    parser.add_argument("--rate", type=int, default=10, help="Rows per second")
    parser.add_argument("--topic", default="edge-iiot-stream", help="Kafka topic")
    args = parser.parse_args()

    producer = SingleBrokerProducer(
        topic=args.topic,
        rows_per_second=args.rate
    )
    producer.run(args.source)


if __name__ == "__main__":
    main()
"""
Multi-Broker Kafka Producer for Edge-IIoT
Distributes 2400 IoT devices across 4 Kafka brokers (600 devices per broker).

Broker mapping:
- Broker 1: devices 0–599
- Broker 2: devices 600–1199
- Broker 3: devices 1200–1799
- Broker 4: devices 1800–2399

Usage:
    python scripts/02_kafka_producer_multi_broker.py --source data/processed --rate 10
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


class MultiBrokerProducer:
    """Kafka producer distributing data across 4 brokers."""

    _IS_DOCKER = os.path.exists("/.dockerenv")

    # Allow override via environment (keeps everything aligned with Dockerfile/compose)
    ENV_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

    if ENV_BOOTSTRAP:
        # Respect explicit env variable completely
        BROKER_BOOTSTRAP_SERVERS = ENV_BOOTSTRAP
        logger.info(f"Using KAFKA_BOOTSTRAP_SERVERS from environment: {BROKER_BOOTSTRAP_SERVERS}")
        BROKERS = {}  # Not used directly, kept for completeness
    else:
        if _IS_DOCKER:
            # Inside Docker network -> use internal PLAINTEXT listener ports (9092)
            BROKERS = {
                "broker_1": "kafka-broker-1:9092",
                "broker_2": "kafka-broker-2:9092",
                "broker_3": "kafka-broker-3:9092",
                "broker_4": "kafka-broker-4:9092",
            }
            BROKER_BOOTSTRAP_SERVERS = (
                "kafka-broker-1:9092,"
                "kafka-broker-2:9092,"
                "kafka-broker-3:9092,"
                "kafka-broker-4:9092"
            )
        else:
            # From host -> use mapped host ports 9092–9095
            BROKERS = {
                "broker_1": "localhost:9092",
                "broker_2": "localhost:9093",
                "broker_3": "localhost:9094",
                "broker_4": "localhost:9095",
            }
            BROKER_BOOTSTRAP_SERVERS = (
                "localhost:9092,"
                "localhost:9093,"
                "localhost:9094,"
                "localhost:9095"
            )

    DEVICES_PER_BROKER = 600
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

        logger.info("Multi-Broker Producer initialized:")
        logger.info(f"  Brokers bootstrap: {self.BROKER_BOOTSTRAP_SERVERS}")
        logger.info(f"  Topic: {self.topic}")
        logger.info("  Device distribution: 600 devices per broker")
        logger.info("  Broker 1: device_0–device_599")
        logger.info("  Broker 2: device_600–device_1199")
        logger.info("  Broker 3: device_1200–device_1799")
        logger.info("  Broker 4: device_1800–device_2399")

    # -------------------------------------------------
    # DEVICE → BROKER MAPPING
    # -------------------------------------------------
    def get_broker_for_device(self, device_id: str) -> int:
        """Map device_id (e.g. device_0) to broker index 0–3."""
        try:
            device_num = int(device_id.split("_")[-1])
        except (ValueError, IndexError):
            device_num = hash(device_id) % self.TOTAL_DEVICES

        broker_idx = (device_num // self.DEVICES_PER_BROKER) % 4
        return broker_idx

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
            1: [],
            2: [],
            3: [],
        }

        for device_file in device_files:
            device_path = Path(device_file)
            device_id = device_path.stem  # "device_123"
            try:
                df = pd.read_csv(device_file, nrows=100)
                broker_idx = self.get_broker_for_device(device_id)
                broker_devices[broker_idx].append((device_id, df))
                self.device_to_broker[device_id] = broker_idx
                logger.info(
                    f"Loaded {device_id}: {len(df)} rows → Broker {broker_idx + 1}"
                )
            except Exception as e:
                logger.error(f"Failed to load {device_path.name}: {e}")

        logger.info("\n" + "=" * 70)
        logger.info("Device Distribution Summary:")
        for broker_idx in range(4):
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

        for broker_idx in range(4):
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

        if not all_records:
            logger.error("No device data loaded")
            return

        logger.info(f"Ready to stream {len(all_records)} records")

        while True:
            selected = random.choice(all_records)
            device_id = selected["device_id"]
            broker_idx = selected["broker_idx"]
            record = selected["record"]

            metric_value = record.get("tcp.ack", record.get("tcp.seq", 0.0)) or 0.0

            message = {
                "device_id": device_id,
                "broker": f"broker_{broker_idx + 1}",
                "timestamp": datetime.now().isoformat(),
                "data": float(metric_value),
                "raw_features": record,
            }

            yield message, device_id, broker_idx

    # -------------------------------------------------
    # MAIN SEND LOOP
    # -------------------------------------------------
    def send_messages(
        self, broker_devices: Dict[int, List[Tuple[str, pd.DataFrame]]]
    ) -> None:
        if not self.producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        self.start_time = time.time()
        generator = self.stream_from_broker_devices(broker_devices)

        logger.info("\n" + "=" * 70)
        logger.info(f"Starting message stream at {self.rows_per_second} msgs/sec")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 70 + "\n")

        try:
            for message, device_id, broker_idx in generator:
                try:
                    future = self.producer.send(
                        self.topic,
                        value=message,
                        key=device_id.encode("utf-8"),
                    )
                    future.get(timeout=10)

                    self.messages_sent += 1

                    if self.messages_sent % 100 == 0:
                        elapsed = time.time() - self.start_time
                        rate = self.messages_sent / elapsed if elapsed > 0 else 0.0
                        logger.info(
                            f"Sent {self.messages_sent} msgs | "
                            f"{device_id} → broker {broker_idx + 1} | "
                            f"rate={rate:.2f} msg/s"
                        )

                    time.sleep(self.interval)

                except KafkaError as e:
                    logger.error(f"Kafka error: {e}")
                    self.errors += 1
                    if self.errors > 10:
                        logger.error("Too many errors, stopping producer.")
                        break

        except KeyboardInterrupt:
            logger.info("Shutdown requested (Ctrl+C)")
        finally:
            self.shutdown()

    # -------------------------------------------------
    # CLEANUP
    # -------------------------------------------------
    def shutdown(self) -> None:
        if self.producer:
            self.producer.flush()
            self.producer.close()

        elapsed = time.time() - self.start_time if self.start_time else 0.0
        logger.info("\n" + "=" * 70)
        logger.info("PRODUCER SHUTDOWN")
        logger.info(f"Total messages sent: {self.messages_sent}")
        logger.info(f"Total errors: {self.errors}")
        logger.info(f"Elapsed time: {elapsed:.2f} s")
        if elapsed > 0:
            logger.info(
                f"Average rate: {self.messages_sent / elapsed:.2f} msgs/sec"
            )
        logger.info("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Broker Edge-IIoT Kafka Producer"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="data/processed",
        help="Path to device CSV files or directory",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=10,
        help="Messages per second",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="edge-iiot-stream",
        help="Kafka topic name",
    )

    args = parser.parse_args()

    producer = MultiBrokerProducer(
        topic=args.topic,
        rows_per_second=args.rate,
    )

    try:
        producer.connect()
        broker_devices = producer.load_and_distribute_devices(args.source)
        if broker_devices:
            producer.send_messages(broker_devices)
        else:
            logger.error("No device data loaded, exiting.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

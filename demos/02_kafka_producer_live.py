"""
LIVE Kafka Producer for Edge-IIoT
Generates REAL-TIME synthetic sensor data with random anomalies.

This demonstrates TRUE STREAMING behavior:
- Data is generated in real-time (not from files)
- Anomalies are injected randomly (not predetermined)
- Each run produces DIFFERENT anomaly patterns

Usage:
    python scripts/02_kafka_producer_live.py --devices 100 --rate 10 --anomaly-rate 0.05
"""

import json
import time
import argparse
import random
import os
import sys
import math
from datetime import datetime
from typing import Dict, Optional

from kafka import KafkaProducer
import logging

# -----------------------------------------------------
# LOGGING
# -----------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveStreamingProducer:
    """
    Generates LIVE sensor data with realistic patterns and random anomalies.
    
    Each device simulates:
    - Base signal: sinusoidal pattern (different frequency per device)
    - Noise: Gaussian noise overlay
    - Drift: slow trend changes
    - Anomalies: random spikes/drops/pattern breaks
    """

    _IS_DOCKER = os.path.exists("/.dockerenv")
    ENV_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

    if ENV_BOOTSTRAP:
        BROKER = ENV_BOOTSTRAP
    else:
        BROKER = "kafka-broker-1:9092" if _IS_DOCKER else "localhost:9092"

    def __init__(
        self,
        topic: str = "edge-iiot-stream",
        num_devices: int = 100,
        rows_per_second: int = 10,
        anomaly_rate: float = 0.05,  # 5% chance of anomaly
    ):
        self.topic = topic
        self.num_devices = num_devices
        self.rows_per_second = rows_per_second
        self.interval = 1.0 / rows_per_second
        self.anomaly_rate = anomaly_rate

        self.producer: Optional[KafkaProducer] = None
        self.messages_sent = 0
        self.anomalies_injected = 0
        self.start_time: Optional[float] = None

        # Device state (for generating realistic patterns)
        self.device_state: Dict[str, dict] = {}
        for i in range(num_devices):
            device_id = f"device_{i}"
            self.device_state[device_id] = {
                "base_value": random.uniform(20, 80),  # Base sensor value
                "frequency": random.uniform(0.01, 0.1),  # Oscillation frequency
                "phase": random.uniform(0, 2 * math.pi),  # Phase offset
                "noise_level": random.uniform(0.5, 3.0),  # Noise amplitude
                "drift": 0.0,  # Current drift
                "drift_speed": random.uniform(-0.01, 0.01),  # Drift rate
                "tick": 0,  # Time counter
            }

        logger.info("=" * 70)
        logger.info("🚀 LIVE STREAMING PRODUCER")
        logger.info("=" * 70)
        logger.info(f"  Broker: {self.BROKER}")
        logger.info(f"  Topic: {self.topic}")
        logger.info(f"  Devices: {self.num_devices}")
        logger.info(f"  Rate: {self.rows_per_second} msg/sec")
        logger.info(f"  Anomaly Rate: {self.anomaly_rate * 100:.1f}%")
        logger.info("=" * 70)

    def connect(self, max_retries: int = 30, retry_delay: int = 5) -> None:
        """Connect to Kafka with retry logic."""
        retry_count = 0
        while retry_count < max_retries:
            try:
                logger.info(f"Connecting to Kafka: {self.BROKER}...")
                self.producer = KafkaProducer(
                    bootstrap_servers=self.BROKER.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all",
                    retries=5,
                )
                logger.info("✅ Connected to Kafka!")
                return
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"Connection attempt {retry_count}/{max_retries} failed: {e}")
                    time.sleep(retry_delay)
                else:
                    raise

    def generate_value(self, device_id: str) -> tuple:
        """
        Generate a realistic sensor value for a device.
        Returns: (value, is_anomaly, anomaly_type)
        """
        state = self.device_state[device_id]
        state["tick"] += 1
        tick = state["tick"]

        # Base sinusoidal pattern
        base = state["base_value"]
        freq = state["frequency"]
        phase = state["phase"]
        signal = base + 10 * math.sin(freq * tick + phase)

        # Add drift (slow trend)
        state["drift"] += state["drift_speed"]
        if abs(state["drift"]) > 10:
            state["drift_speed"] *= -1  # Reverse drift direction
        signal += state["drift"]

        # Add noise
        noise = random.gauss(0, state["noise_level"])
        signal += noise

        # Check for anomaly
        is_anomaly = False
        anomaly_type = None

        if random.random() < self.anomaly_rate:
            is_anomaly = True
            anomaly_type = random.choice([
                "spike_up",      # Sudden high value
                "spike_down",    # Sudden low value
                "noise_burst",   # High noise
                "flatline",      # Stuck value
                "pattern_break", # Phase jump
            ])

            if anomaly_type == "spike_up":
                signal += random.uniform(30, 80)
            elif anomaly_type == "spike_down":
                signal -= random.uniform(30, 80)
            elif anomaly_type == "noise_burst":
                signal += random.gauss(0, 20)
            elif anomaly_type == "flatline":
                signal = state["base_value"]  # Suddenly flat
            elif anomaly_type == "pattern_break":
                state["phase"] += random.uniform(1, 3)  # Jump phase
                signal = base + 10 * math.sin(freq * tick + state["phase"])

            self.anomalies_injected += 1

        return signal, is_anomaly, anomaly_type

    def run(self) -> None:
        """Main streaming loop - generates data in real-time."""
        self.connect()
        self.start_time = time.time()

        logger.info("\n🔴 STREAMING LIVE DATA (Ctrl+C to stop)\n")
        logger.info("Watch for 🚨 anomaly injections!\n")

        device_ids = list(self.device_state.keys())
        device_index = 0

        try:
            while True:
                # Round-robin through devices
                device_id = device_ids[device_index]
                device_index = (device_index + 1) % len(device_ids)

                # Generate live value
                value, is_anomaly, anomaly_type = self.generate_value(device_id)

                # Create record
                record = {
                    "device_id": device_id,
                    "data": round(value, 4),
                    "ts": datetime.now().isoformat(),
                    "injected_anomaly": is_anomaly,  # For debugging/verification
                    "anomaly_type": anomaly_type,
                }

                # Send to Kafka
                self.producer.send(self.topic, value=record)
                self.messages_sent += 1

                # Log anomalies
                if is_anomaly:
                    logger.info(
                        f"🚨 INJECTED [{anomaly_type}] {device_id} = {value:.2f}"
                    )

                # Progress logging
                if self.messages_sent % 500 == 0:
                    elapsed = time.time() - self.start_time
                    rate = self.messages_sent / elapsed if elapsed > 0 else 0
                    anomaly_pct = (self.anomalies_injected / self.messages_sent) * 100
                    logger.info(
                        f"📊 Sent: {self.messages_sent} | "
                        f"Rate: {rate:.1f}/s | "
                        f"Anomalies: {self.anomalies_injected} ({anomaly_pct:.1f}%)"
                    )

                time.sleep(self.interval)

        except KeyboardInterrupt:
            logger.info("\n\n⏹️  Stopped by user")
        finally:
            if self.producer:
                self.producer.flush()
                self.producer.close()

            elapsed = time.time() - self.start_time if self.start_time else 0
            logger.info("\n" + "=" * 70)
            logger.info("📈 FINAL STATISTICS")
            logger.info("=" * 70)
            logger.info(f"  Total Messages: {self.messages_sent}")
            logger.info(f"  Total Anomalies Injected: {self.anomalies_injected}")
            logger.info(f"  Anomaly Rate: {(self.anomalies_injected / max(1, self.messages_sent)) * 100:.2f}%")
            logger.info(f"  Runtime: {elapsed:.1f}s")
            logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Live Streaming Kafka Producer")
    parser.add_argument("--devices", type=int, default=100, help="Number of devices")
    parser.add_argument("--rate", type=int, default=10, help="Messages per second")
    parser.add_argument("--topic", default="edge-iiot-stream", help="Kafka topic")
    parser.add_argument(
        "--anomaly-rate", type=float, default=0.05,
        help="Probability of anomaly (0.0-1.0)"
    )
    args = parser.parse_args()

    producer = LiveStreamingProducer(
        topic=args.topic,
        num_devices=args.devices,
        rows_per_second=args.rate,
        anomaly_rate=args.anomaly_rate,
    )
    producer.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Flink Kafka Heartbeat - Keeps flink-training consumer group visible in Kafka UI

This script maintains a lightweight Kafka consumer connection that registers
with the same consumer group as Flink. It doesn't consume any messages (Flink does),
it just keeps the group showing as "STABLE" in Kafka UI.

Run this alongside the Flink job:
  python scripts/flink_kafka_heartbeat.py

Or in Docker:
  docker exec -d flink-jobmanager python /opt/flink/scripts/flink_kafka_heartbeat.py
"""

import os
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker-1:9092")
TOPIC = "edge-iiot-stream"
GROUP_ID = "flink-training"


def main():
    """Keep the flink-training consumer group visible in Kafka UI"""
    try:
        from kafka import KafkaConsumer
    except ImportError:
        logger.error("kafka-python not installed. Run: pip install kafka-python")
        return

    logger.info(f"Starting Kafka heartbeat for group '{GROUP_ID}'")
    logger.info(f"Broker: {KAFKA_BROKER}, Topic: {TOPIC}")

    while True:
        try:
            # Create consumer - this registers with the consumer group
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                group_id=GROUP_ID,
                enable_auto_commit=False,  # Don't commit - let Flink manage offsets
                auto_offset_reset="latest",
                consumer_timeout_ms=-1,  # Never timeout
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
            )
            
            logger.info(f"✓ Connected to Kafka, group '{GROUP_ID}' now visible in Kafka UI")
            
            # Keep polling to maintain group membership
            # We don't actually process messages - Flink does that
            while True:
                # Poll but don't process - just maintain heartbeat
                consumer.poll(timeout_ms=5000)
                time.sleep(5)
                
        except Exception as e:
            logger.warning(f"Connection lost: {e}. Reconnecting in 10s...")
            time.sleep(10)


if __name__ == "__main__":
    main()

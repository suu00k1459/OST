"""
Federated Learning Aggregation Service
Aggregates local model updates from edge devices into a global model
Implements Federated Averaging (FedAvg) algorithm

Subscribes to: local-model-updates topic
Publishes to: global-model-updates topic
Stores to: TimescaleDB (federated_models & local_models tables)

Automatically detects if running inside Docker or locally
"""
from kafka.errors import NoBrokersAvailable

import json
import logging
import os
import sys
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import pickle
import time

import numpy as np
from kafka import KafkaConsumer, KafkaProducer
import psycopg2

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# CONFIG LOADER (shared helper)
# ---------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from config_loader import get_db_config, get_kafka_config  # noqa: E402

# Kafka configuration - auto-detect Docker vs local
kafka_config = get_kafka_config()

_raw_bootstrap = kafka_config["bootstrap_servers"]
if isinstance(_raw_bootstrap, str):
    KAFKA_BOOTSTRAP_SERVERS: List[str] = [
        s.strip() for s in _raw_bootstrap.split(",") if s.strip()
    ]
else:
    # Allow config_loader to return list already
    KAFKA_BOOTSTRAP_SERVERS = list(_raw_bootstrap)

INPUT_TOPIC = "local-model-updates"
OUTPUT_TOPIC = "global-model-updates"
CONSUMER_GROUP = "federated-aggregation"

# TimescaleDB configuration - auto-detect Docker vs local
db_config = get_db_config()
DB_HOST = db_config["host"]
DB_PORT = db_config["port"]
DB_NAME = db_config["database"]
DB_USER = db_config["user"]
DB_PASSWORD = db_config["password"]

logger.info(f"Kafka Brokers: {', '.join(KAFKA_BOOTSTRAP_SERVERS)}")
logger.info(
    f"Database Config: host={DB_HOST}, "
    f"port={DB_PORT}, database={DB_NAME}, user={DB_USER}"
)

# ---------------------------------------------------------------------
# MODEL STORAGE
# ---------------------------------------------------------------------
MODELS_DIR = Path("models")
LOCAL_MODELS_DIR = MODELS_DIR / "local"
GLOBAL_MODELS_DIR = MODELS_DIR / "global"

for d in [MODELS_DIR, LOCAL_MODELS_DIR, GLOBAL_MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# AGGREGATION SETTINGS
# ---------------------------------------------------------------------
AGGREGATION_WINDOW = 20          # Aggregate every 20 local model updates
MIN_DEVICES_FOR_AGGREGATION = 2  # Minimum devices needed
FEDAVG_LEARNING_RATE = 0.1       # (placeholder, not used for numeric weights here)


class GlobalModel:
    """Global model in federated learning"""

    def __init__(self, version: int = 0):
        self.version = version
        self.weights = None  # Placeholder for real weight tensors if used later
        self.accuracy = 0.0
        self.created_at = datetime.now()
        self.num_devices_aggregated = 0
        self.aggregation_round = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert model metadata to dictionary"""
        return {
            "version": self.version,
            "accuracy": self.accuracy,
            "created_at": self.created_at.isoformat(),
            "num_devices_aggregated": self.num_devices_aggregated,
            "aggregation_round": self.aggregation_round,
        }

    def save(self, path: Path) -> None:
        """Save model to disk"""
        try:
            with open(path, "wb") as f:
                pickle.dump(self, f)
            logger.info(f"✓ Global model v{self.version} saved to {path}")
        except Exception as e:
            logger.error(f"✗ Error saving model: {e}")

    @staticmethod
    def load(path: Path) -> "GlobalModel | None":
        """Load model from disk"""
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"✗ Error loading model: {e}")
            return None


class FederatedAggregator:
    """Federated learning aggregator using FedAvg algorithm"""

    def __init__(self, producer: KafkaProducer):
        self.global_model = GlobalModel(version=0)
        self.local_model_buffer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.update_count = 0
        self.aggregation_round = 0
        self.db_connection: psycopg2.extensions.connection | None = None
        self.producer = producer

        self._init_database()

    # -----------------------------------------------------------------
    # DATABASE
    # -----------------------------------------------------------------
    def _init_database(self) -> None:
        """Initialize database connection and ensure tables exist.

        NOTE: In your architecture, database-init.py already creates the
        full schema with hypertables. This block is a *fallback* so the
        service is still usable if database-init was not run.
        """
        try:
            self.db_connection = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
            logger.info("✓ Connected to TimescaleDB")

            with self.db_connection.cursor() as cursor:
                # Fallback table creation (IF NOT EXISTS – won't override existing schema)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS federated_models (
                        id SERIAL PRIMARY KEY,
                        global_version INT NOT NULL,
                        aggregation_round INT NOT NULL,
                        num_devices INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS local_models (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        model_version INT NOT NULL,
                        global_version INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        samples_processed INT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # Try to make them hypertables (no-op if already done)
                try:
                    cursor.execute(
                        "SELECT create_hypertable('federated_models', 'created_at', if_not_exists => TRUE)"
                    )
                except Exception:
                    pass

                try:
                    cursor.execute(
                        "SELECT create_hypertable('local_models', 'created_at', if_not_exists => TRUE)"
                    )
                except Exception:
                    pass

                self.db_connection.commit()
                logger.info("✓ Database tables ready (or already existed)")

        except Exception as e:
            logger.error(f"✗ Database connection error: {e}")
            raise

    # -----------------------------------------------------------------
    # LOCAL MODEL HANDLING
    # -----------------------------------------------------------------
    def process_local_model_update(self, record: Dict[str, Any]) -> None:
        """Process incoming local model update from Kafka"""
        try:
            device_id = record.get("device_id")
            model_version = record.get("model_version")
            accuracy = float(record.get("accuracy", 0.0))
            samples_processed = int(record.get("samples_processed", 0))

            logger.info(
                "Received local model from %s: v%s, accuracy=%.2f%%, samples=%d",
                device_id,
                model_version,
                accuracy * 100.0,
                samples_processed,
            )

            model_info = {
                "device_id": device_id,
                "model_version": model_version,
                "accuracy": accuracy,
                "samples_processed": samples_processed,
                "timestamp": record.get("timestamp", datetime.now().isoformat()),
            }

            self.local_model_buffer[device_id].append(model_info)
            self.update_count += 1

            self._save_local_model_to_db(
                device_id, model_version, accuracy, samples_processed
            )

            # Trigger aggregation if enough updates accumulated
            if self.update_count >= AGGREGATION_WINDOW:
                global_update = self.aggregate()
                self.update_count = 0
                if global_update is not None:
                    self._publish_global_update(global_update)

        except Exception as e:
            logger.error(f"Error processing local model update: {e}", exc_info=True)

    def _save_local_model_to_db(
        self, device_id: str, model_version: int, accuracy: float, samples_processed: int
    ) -> None:
        """Persist local model metadata to TimescaleDB"""
        if not self.db_connection:
            return

        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO local_models
                        (device_id, model_version, global_version, accuracy, samples_processed)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        device_id,
                        model_version,
                        self.global_model.version,
                        accuracy,
                        samples_processed,
                    ),
                )
                self.db_connection.commit()
        except Exception as e:
            self.db_connection.rollback()
            logger.warning(f"Error saving local model to DB: {e}")

    # -----------------------------------------------------------------
    # FEDERATED AGGREGATION (FedAvg-style)
    # -----------------------------------------------------------------
    def aggregate(self) -> Dict[str, Any] | None:
        """
        Aggregate local models using a simple FedAvg-style accuracy merge.

        Aggregation:
          - GlobalAccuracy = Σ(accuracy_i × samples_i) / Σ(samples_i)
          - Devices contribute proportionally to their samples_processed
        """
        try:
            num_devices = len(self.local_model_buffer)
            if num_devices < MIN_DEVICES_FOR_AGGREGATION:
                logger.warning(
                    "⚠ Not enough devices for aggregation: %d/%d",
                    num_devices,
                    MIN_DEVICES_FOR_AGGREGATION,
                )
                return None

            logger.info("\n%s", "=" * 70)
            logger.info("Federated Aggregation Round %d", self.aggregation_round + 1)
            logger.info("%s", "=" * 70)
            logger.info("Number of devices: %d", num_devices)

            total_samples = 0
            weighted_accuracy = 0.0
            device_accuracies: List[Dict[str, Any]] = []

            for device_id, updates in self.local_model_buffer.items():
                if not updates:
                    continue

                latest_update = updates[-1]
                accuracy = float(latest_update["accuracy"])
                samples = int(latest_update["samples_processed"])

                device_accuracies.append(
                    {
                        "device_id": device_id,
                        "accuracy": accuracy,
                        "samples": samples,
                    }
                )

                weighted_accuracy += accuracy * samples
                total_samples += samples

                logger.info(
                    "  Device %s: accuracy=%.2f%%, samples=%d",
                    device_id,
                    accuracy * 100.0,
                    samples,
                )

            global_accuracy = (
                weighted_accuracy / total_samples if total_samples > 0 else 0.0
            )

            # Update global model state
            self.global_model.version += 1
            self.global_model.accuracy = global_accuracy
            self.global_model.num_devices_aggregated = num_devices
            self.aggregation_round += 1
            self.global_model.aggregation_round = self.aggregation_round

            logger.info("\n  Global Model v%d:", self.global_model.version)
            logger.info("  Weighted Average Accuracy: %.2f%%", global_accuracy * 100.0)
            logger.info("  Total Samples Processed: %d", total_samples)
            logger.info("  Aggregation Round: %d", self.aggregation_round)

            # Persist model snapshot
            model_path = GLOBAL_MODELS_DIR / f"global_model_v{self.global_model.version}.pkl"
            self.global_model.save(model_path)

            # Save summary to DB
            self._save_global_model_to_db(global_accuracy, num_devices)

            # Reset buffer for next round
            self.local_model_buffer.clear()

            global_update = {
                "version": self.global_model.version,
                "aggregation_round": self.aggregation_round,
                "global_accuracy": global_accuracy,
                "num_devices": num_devices,
                "device_accuracies": device_accuracies,
                "timestamp": datetime.now().isoformat(),
                "total_samples": total_samples,
            }

            logger.info("%s\n", "=" * 70)
            return global_update

        except Exception as e:
            logger.error(f"Error in aggregation: {e}", exc_info=True)
            return None

    def _save_global_model_to_db(self, accuracy: float, num_devices: int) -> None:
        """Persist global model metadata to TimescaleDB"""
        if not self.db_connection:
            return

        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO federated_models
                        (global_version, aggregation_round, num_devices, accuracy)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        self.global_model.version,
                        self.aggregation_round,
                        num_devices,
                        accuracy,
                    ),
                )
                self.db_connection.commit()
                logger.info(
                    "✓ Global model v%d saved to database", self.global_model.version
                )
        except Exception as e:
            self.db_connection.rollback()
            logger.warning(f"Error saving global model to DB: {e}")

    # -----------------------------------------------------------------
    # KAFKA PUBLISH
    # -----------------------------------------------------------------
    def _publish_global_update(self, update: Dict[str, Any]) -> None:
        """Publish the aggregated global update to Kafka"""
        try:
            self.producer.send(OUTPUT_TOPIC, value=update)
            # Aggregation is relatively infrequent, flush here is fine
            self.producer.flush()
            logger.info(
                "✓ Published global model update v%d to topic '%s'",
                update.get("version"),
                OUTPUT_TOPIC,
            )
        except Exception as e:
            logger.error(f"Error publishing global model update: {e}", exc_info=True)


# ---------------------------------------------------------------------
# KAFKA HELPERS
# ---------------------------------------------------------------------
def create_kafka_producer(max_retries: int = 30, delay: float = 5.0) -> KafkaProducer:
    """Create Kafka producer for global model updates with retries."""
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=5,
            )
            logger.info("✓ Aggregator Kafka producer connected (attempt %d)", attempt)
            return producer
        except NoBrokersAvailable as e:
            last_err = e
            logger.warning(
                "Kafka not ready yet for aggregator producer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)
        except Exception as e:
            last_err = e
            logger.warning(
                "Error creating aggregator producer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)

    logger.error(
        "Aggregator producer failed to connect after %d attempts: %s",
        max_retries,
        last_err,
    )
    raise last_err or RuntimeError("Unable to create Kafka producer")


def create_kafka_consumer(
    max_retries: int = 30, delay: float = 5.0
) -> KafkaConsumer:
    """Create Kafka consumer for local model updates with retries."""
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            consumer = KafkaConsumer(
                INPUT_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            logger.info("✓ Aggregator Kafka consumer connected (attempt %d)", attempt)
            return consumer
        except NoBrokersAvailable as e:
            last_err = e
            logger.warning(
                "Kafka not ready yet for aggregator consumer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)
        except Exception as e:
            last_err = e
            logger.warning(
                "Error creating aggregator consumer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)

    logger.error(
        "Aggregator consumer failed to connect after %d attempts: %s",
        max_retries,
        last_err,
    )
    raise last_err or RuntimeError("Unable to create Kafka consumer")



# ---------------------------------------------------------------------
# MAIN SERVICE LOOP
# ---------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 70)
    logger.info("Federated Learning Aggregation Service")
    logger.info("=" * 70)
    logger.info("Input Topic:  %s", INPUT_TOPIC)
    logger.info("Output Topic: %s", OUTPUT_TOPIC)
    logger.info("Kafka:        %s", ", ".join(KAFKA_BOOTSTRAP_SERVERS))
    logger.info("TimescaleDB:  %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
    logger.info("Aggregation Window: %d updates", AGGREGATION_WINDOW)
    logger.info("Min Devices:       %d", MIN_DEVICES_FOR_AGGREGATION)
    logger.info("=" * 70)

    consumer: KafkaConsumer | None = None
    producer: KafkaProducer | None = None
    aggregator: FederatedAggregator | None = None

    try:
        producer = create_kafka_producer()
        aggregator = FederatedAggregator(producer=producer)
        consumer = create_kafka_consumer()

        logger.info("Waiting for local model updates... (Ctrl+C to stop)\n")

        for message in consumer:
            local_model_record = message.value
            aggregator.process_local_model_update(local_model_record)

    except KeyboardInterrupt:
        logger.info("\n⚠ Service interrupted by user")
    except Exception as e:
        logger.error(f"Error in aggregation service: {e}", exc_info=True)
    finally:
        logger.info("Shutting down federated aggregation service...")
        try:
            if consumer is not None:
                consumer.close()
        except Exception:
            pass

        try:
            if producer is not None:
                producer.flush()
                producer.close()
        except Exception:
            pass

        try:
            if aggregator is not None and aggregator.db_connection is not None:
                aggregator.db_connection.close()
        except Exception:
            pass

        logger.info("✓ Service stopped cleanly")


if __name__ == "__main__":
    main()
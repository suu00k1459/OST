"""
Flink Local Model Training Job
Real-time streaming anomaly detection and local model training per device

NOTE: This script runs INSIDE the Flink Docker container, not on the host machine.
The Docker image (flink:1.18-java11) contains all necessary Java/Flink dependencies.

To submit this job to Flink:
  docker exec flink-jobmanager flink run -py /opt/flink/scripts/03_flink_local_training.py

For development/testing, see: scripts/flink_local_training_simulator.py
"""

import json
import logging
from typing import Dict, Any
from datetime import datetime
import numpy as np
from collections import defaultdict
import sys
import pickle
from pathlib import Path
import os  # for env + paths

# Try to import Flink (will be available in Docker container)
try:
    from pyflink.datastream import StreamExecutionEnvironment
    from pyflink.datastream.functions import MapFunction
    from pyflink.common.serialization import SimpleStringSchema
    from pyflink.datastream.connectors.kafka import (
        KafkaSource,
        KafkaOffsetsInitializer,
        KafkaSink,
        KafkaRecordSerializationSchema,
    )
    from pyflink.common.typeinfo import Types
    from pyflink.common import WatermarkStrategy
    FLINK_AVAILABLE = True
except ImportError:
    FLINK_AVAILABLE = False
    print("ERROR: Flink not available. This script MUST run inside Flink Docker container.")
    print("       This is NOT a host-executable script.")
    print("")
    print("To run this job, submit it to Flink:")
    print("  docker exec flink-jobmanager flink run -py /opt/flink/scripts/03_flink_local_training.py")
    print("")
    print("For local testing/simulation, use: scripts/flink_local_training_simulator.py")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Kafka configuration
# -------------------------------------------------------------------
# Prefer env var (so Docker compose can control it), else sane defaults
ENV_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS")

if ENV_BOOTSTRAP:
    KAFKA_BROKER = ENV_BOOTSTRAP
    logger.info(f"KAFKA_BOOTSTRAP_SERVERS from env: {KAFKA_BROKER}")
else:
    # INSIDE DOCKER NETWORK: use PLAINTEXT ports (9092) on each broker
    # Host mapping to 9092/9093/9094/9095 is only for clients on the host.
    KAFKA_BROKER = (
        "kafka-broker-1:9092,"
        "kafka-broker-2:9092,"
        "kafka-broker-3:9092,"
        "kafka-broker-4:9092"
    )
    logger.info(f"Using default internal Kafka bootstrap: {KAFKA_BROKER}")

INPUT_TOPIC = "edge-iiot-stream"
ANOMALY_OUTPUT_TOPIC = "anomalies"
MODEL_UPDATE_TOPIC = "local-model-updates"

WINDOW_SIZE_SECONDS = 30
ANOMALY_THRESHOLD = 2.5
MODEL_TRAINING_INTERVAL_ROWS = 50   # Train model every 50 rows per device
MODEL_TRAINING_INTERVAL_SECONDS = 60  # OR every 60 seconds (1 minute)

# -------------------------------------------------------------------
# SGD Configuration
# -------------------------------------------------------------------
# Use a writable directory inside Flink container
MODEL_DIR = Path(os.getenv("LOCAL_MODEL_DIR", "/opt/flink/models/local"))

LEARNING_RATE = 0.001  # Reduced from 0.01
BATCH_SIZE = 50


class SGDModelTrainer:
    """Stochastic Gradient Descent trainer for local models"""

    def __init__(self, device_id: str, learning_rate: float = 0.001):
        self.device_id = device_id
        self.learning_rate = learning_rate  # 0.001 to prevent saturation
        # SMALLER INITIALIZATION: Start closer to 0 to avoid early saturation
        self.weights = np.random.normal(0, 0.01, 3)  # 3 features: mean, std, z_score
        self.bias = 0.0
        self.loss_history = []
        self.n_updates = 0
        self.predictions_history = []  # Track predictions for smoother accuracy

    def predict(self, features: np.ndarray) -> float:
        """Make prediction: sigmoid(w·x + b)"""
        z = np.dot(self.weights, features) + self.bias
        z_clipped = np.clip(z, -10, 10)
        return 1 / (1 + np.exp(-z_clipped))  # Sigmoid

    def train_batch(self, X_batch: np.ndarray, y_batch: np.ndarray) -> float:
        """
        Train on batch using gradient descent
        X_batch: shape (batch_size, n_features)
        y_batch: shape (batch_size,) - binary labels (0 or 1)
        Returns: average loss
        """
        if len(X_batch) == 0:
            return 0.0

        batch_loss = 0.0
        self.predictions_history = []

        for X_sample, y_sample in zip(X_batch, y_batch):
            # Forward pass
            prediction = self.predict(X_sample)
            self.predictions_history.append(prediction)

            # Binary cross-entropy loss
            loss = -y_sample * np.log(np.clip(prediction, 1e-7, 1)) - \
                   (1 - y_sample) * np.log(np.clip(1 - prediction, 1e-7, 1))
            batch_loss += loss

            # Backward pass (gradient computation)
            error = prediction - y_sample

            grad_w = error * X_sample
            grad_b = error

            # L2 regularization to prevent overfitting
            self.weights -= self.learning_rate * (grad_w + 0.01 * self.weights)
            self.bias -= self.learning_rate * grad_b

            self.n_updates += 1

        avg_loss = batch_loss / len(X_batch)
        self.loss_history.append(avg_loss)

        return avg_loss

    def calculate_accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        """
        Soft accuracy:
          label 1 → accuracy = prediction
          label 0 → accuracy = 1 - prediction
        """
        if len(X) == 0:
            return 0.5

        predictions = np.array([self.predict(x) for x in X])

        soft_accuracy = np.mean([
            pred if label == 1 else (1 - pred)
            for pred, label in zip(predictions, y)
        ])

        return float(np.clip(soft_accuracy, 0.0, 1.0))

    def save_model(self, version: int):
        """Save model to disk"""
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            model_path = MODEL_DIR / f"device_{self.device_id}_v{version}.pkl"

            model_data = {
                "device_id": self.device_id,
                "version": version,
                "weights": self.weights,
                "bias": self.bias,
                "learning_rate": self.learning_rate,
                "n_updates": self.n_updates,
                "loss_history": self.loss_history,
            }

            with open(model_path, "wb") as f:
                pickle.dump(model_data, f)

            logger.info(f"✓ Saved model for {self.device_id} v{version} at {model_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving model for {self.device_id}: {e}")
            return False


class AnomalyDetectionFunction(MapFunction):
    """Flink MapFunction for real-time anomaly detection and local model training"""

    def __init__(self):
        super().__init__()
        self.device_stats = defaultdict(
            lambda: {
                "values": [],
                "mean": 0.0,
                "std": 1.0,
                "samples": 0,
                "last_training_time": datetime.now().timestamp(),
            }
        )
        self.model_versions = defaultdict(lambda: {"version": 0, "samples": 0})
        # SGD trainer per device
        self.sgd_trainers = defaultdict(
            lambda: SGDModelTrainer("unknown", learning_rate=LEARNING_RATE)
        )

    def should_train_model(self, device_id: str) -> bool:
        """
        Train if:
        - 50 new rows since last training OR
        - 60 seconds elapsed since last training
        """
        stats = self.device_stats[device_id]
        current_time = datetime.now().timestamp()
        time_elapsed = current_time - stats["last_training_time"]

        if stats["samples"] >= MODEL_TRAINING_INTERVAL_ROWS:
            return True
        if time_elapsed >= MODEL_TRAINING_INTERVAL_SECONDS:
            return True
        return False

    def map(self, element):
        """Process incoming IoT data and train local models"""
        try:
            data = json.loads(element)
            device_id = data.get("device_id", "unknown")
            value = data.get("data", 0.0)  # Single numeric metric

            results = {"anomalies": [], "models": []}

            # Update device statistics
            stats = self.device_stats[device_id]
            stats["values"].append(value)
            stats["samples"] += 1

            # Keep rolling window of 100 values
            if len(stats["values"]) > 100:
                stats["values"].pop(0)

            # Update mean / std
            if len(stats["values"]) > 1:
                stats["mean"] = float(np.mean(stats["values"]))
                stats["std"] = float(np.std(stats["values"]))

            # Z-score anomaly detection
            if stats["std"] > 0:
                z_score = abs((value - stats["mean"]) / stats["std"])

                if z_score > ANOMALY_THRESHOLD:
                    severity = "critical" if z_score > ANOMALY_THRESHOLD * 2 else "warning"
                    anomaly = {
                        "device_id": device_id,
                        "value": value,
                        "z_score": float(z_score),
                        "severity": severity,
                        "timestamp": datetime.now().isoformat(),
                    }
                    results["anomalies"].append(json.dumps(anomaly))

            # Model training trigger
            if self.should_train_model(device_id):
                model = self.model_versions[device_id]
                model["version"] += 1

                # Reset counters
                stats["samples"] = 0
                stats["last_training_time"] = datetime.now().timestamp()

                if len(stats["values"]) >= 2:
                    X_train = []
                    y_train = []

                    for v in stats["values"]:
                        z_score = abs((v - stats["mean"]) / stats["std"]) if stats["std"] > 0 else 0

                        # Features: [mean, std, z_score]
                        features = np.array([stats["mean"], stats["std"], z_score])
                        X_train.append(features)

                        # Label: 1 if anomaly (z > threshold), else 0
                        label = 1 if z_score > ANOMALY_THRESHOLD else 0
                        y_train.append(label)

                    X_train = np.array(X_train)
                    y_train = np.array(y_train)

                    trainer = self.sgd_trainers[device_id]
                    trainer.device_id = device_id

                    loss = trainer.train_batch(X_train, y_train)
                    accuracy = trainer.calculate_accuracy(X_train, y_train)

                    trainer.save_model(model["version"])

                    logger.info(
                        f"Device {device_id}: v{model['version']} "
                        f"- Accuracy: {accuracy:.2%}, Loss: {loss:.4f}, "
                        f"Updates: {trainer.n_updates}"
                    )
                else:
                    accuracy = 0.5
                    loss = 0.0

                model_update = {
                    "device_id": device_id,
                    "model_version": model["version"],
                    "accuracy": float(accuracy),
                    "loss": float(loss),
                    "samples_processed": len(stats["values"]),
                    "mean": float(stats["mean"]),
                    "std": float(stats["std"]),
                    "timestamp": datetime.now().isoformat(),
                }
                results["models"].append(json.dumps(model_update))

            return json.dumps(results)

        except Exception as e:
            logger.error(f"Error in AnomalyDetectionFunction: {e}")
            return json.dumps({"anomalies": [], "models": []})


def main():
    """Main Flink job"""
    if not FLINK_AVAILABLE:
        logger.error("ERROR: Flink not available. This script must run in Flink Docker container.")
        logger.error("Run inside Docker with: docker exec flink-jobmanager flink run -py ...")
        return

    logger.info("Starting Flink Local Training Job")
    logger.info(f"Using Kafka bootstrap servers: {KAFKA_BROKER}")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1) #Safe for single task manager

    # ---- Make sure Kafka connector + client jars are on the JVM classpath ----
    jar_base = "/opt/flink/usrlib"
    kafka_connector_jar = f"file://{jar_base}/flink-connector-kafka-3.1.0-1.18.jar"
    kafka_clients_jar   = f"file://{jar_base}/kafka-clients-3.1.0.jar"

    logger.info("Adding Kafka jars to pipeline:")
    logger.info("  %s", kafka_connector_jar)
    logger.info("  %s", kafka_clients_jar)

    env.add_jars(kafka_connector_jar, kafka_clients_jar)
    env.add_classpaths(kafka_connector_jar, kafka_clients_jar)
    # --------------------------------------------------------------------------

    # Kafka Source (Flink 1.18+)
    kafka_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_topics(INPUT_TOPIC)
        .set_group_id("flink-training")
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        "kafka-source",
    )

    processed = stream.map(AnomalyDetectionFunction(), output_type=Types.STRING())

    # Extract anomalies / models as separate streams
    def extract_anomalies(element: str) -> str:
        data = json.loads(element)
        return "\n".join(data.get("anomalies", []))

    def extract_models(element: str) -> str:
        data = json.loads(element)
        return "\n".join(data.get("models", []))

    anomalies = processed.map(extract_anomalies, output_type=Types.STRING()).filter(
        lambda x: len(x) > 0
    )
    models = processed.map(extract_models, output_type=Types.STRING()).filter(
        lambda x: len(x) > 0
    )

    # Kafka Sinks (Flink 1.18+)
    anomaly_sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(ANOMALY_OUTPUT_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    model_sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(MODEL_UPDATE_TOPIC)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )

    anomalies.sink_to(anomaly_sink)
    models.sink_to(model_sink)

    env.execute("Local Training Job")


if __name__ == "__main__":
    main()

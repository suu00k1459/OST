"""
Flink Local Model Training Job
Real-time streaming anomaly detection and local model training per device

NOTE: This script runs INSIDE the Flink Docker container, not on the host machine.
The Docker image (flink:1.18-java11) contains all necessary Java/Flink dependencies.

To submit this job to Flink:
  docker exec flink-jobmanager flink run -py /path/to/flink_local_training.py

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

# --- NEW: Isolation Forest for anomaly detection ---
from sklearn.ensemble import IsolationForest

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
    print("       ")
    print("To run this job, submit it to Flink:")
    print("  docker exec flink-jobmanager flink run -py /path/to/03_flink_local_training.py")
    print("       ")
    print("For local testing/simulation, use: scripts/flink_local_training_simulator.py")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BROKER = 'kafka-broker-1:29092,kafka-broker-2:29093,kafka-broker-3:29094,kafka-broker-4:29095'  # Docker internal network with all 4 brokers
INPUT_TOPIC = 'edge-iiot-stream'
ANOMALY_OUTPUT_TOPIC = 'anomalies'
MODEL_UPDATE_TOPIC = 'local-model-updates'

WINDOW_SIZE_SECONDS = 30
ANOMALY_THRESHOLD = 2.5  # still used as a fallback threshold in cold-start
MODEL_TRAINING_INTERVAL_ROWS = 50  # Train model every 50 rows per device
MODEL_TRAINING_INTERVAL_SECONDS = 60  # OR every 60 seconds (1 minute)

# Isolation Forest configuration
IF_MIN_SAMPLES = 30          # minimum samples before training IF per device
IF_RETRAIN_DELTA = 30        # retrain IF after this many new samples
IF_CONTAMINATION = 0.05      # expected anomaly fraction
IF_N_ESTIMATORS = 100

# SGD Configuration
MODEL_DIR = Path('/app/models/local')
LEARNING_RATE = 0.001  # Reduced from 0.01 to prevent quick saturation
BATCH_SIZE = 50


class SGDModelTrainer:
    """Stochastic Gradient Descent trainer for local models"""

    def __init__(self, device_id: str, learning_rate: float = 0.001):
        self.device_id = device_id
        self.learning_rate = learning_rate  # REDUCED: 0.01 → 0.001 to prevent saturation
        # SMALLER INITIALIZATION: Start closer to 0 to avoid early saturation
        # 3 features: mean, std, anomaly_score (or z_score as fallback)
        self.weights = np.random.normal(0, 0.01, 3)
        self.bias = 0.0
        self.loss_history = []
        self.n_updates = 0
        self.predictions_history = []  # Track predictions for smoother accuracy

    def predict(self, features: np.ndarray) -> float:
        """Make prediction: sigmoid(w·x + b)"""
        z = np.dot(self.weights, features) + self.bias
        # Clip z to prevent overflow, but allow more gradual predictions
        z_clipped = np.clip(z, -10, 10)
        return 1 / (1 + np.exp(-z_clipped))  # Sigmoid

    def train_batch(self, X_batch: np.ndarray, y_batch: np.ndarray) -> float:
        """
        Train on batch using gradient descent with momentum
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

            # Gradient descent with adaptive learning rate
            grad_w = error * X_sample
            grad_b = error

            # L2 regularization to prevent overfitting on small batches
            self.weights -= self.learning_rate * (grad_w + 0.01 * self.weights)
            self.bias -= self.learning_rate * grad_b

            self.n_updates += 1

        avg_loss = batch_loss / len(X_batch)
        self.loss_history.append(avg_loss)

        return avg_loss

    def calculate_accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        """
        Calculate accuracy using soft predictions (don't threshold at 0.5)
        Uses Mean Absolute Error similarity instead of hard classification
        """
        if len(X) == 0:
            return 0.5  # Default neutral accuracy

        predictions = np.array([self.predict(x) for x in X])

        # Instead of hard 0/1 classification, use soft accuracy:
        # For label 1: accuracy = prediction
        # For label 0: accuracy = 1 - prediction
        # This gives smoother accuracy that varies 0.0-1.0
        soft_accuracy = np.mean([pred if yy == 1 else (1 - pred)
                                 for pred, yy in zip(predictions, y)])

        return float(np.clip(soft_accuracy, 0.0, 1.0))

    def save_model(self, version: int):
        """Save model to disk"""
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            model_path = MODEL_DIR / f"device_{self.device_id}_v{version}.pkl"

            model_data = {
                'device_id': self.device_id,
                'version': version,
                'weights': self.weights,
                'bias': self.bias,
                'learning_rate': self.learning_rate,
                'n_updates': self.n_updates,
                'loss_history': self.loss_history,
            }

            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)

            logger.info(f"✓ Saved model for {self.device_id} v{version}")
            return True
        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return False


class AnomalyDetectionFunction(MapFunction):
    """Flink MapFunction for real-time anomaly detection and local model training"""

    def __init__(self):
        super().__init__()
        self.device_stats = defaultdict(
            lambda: {
                'values': [],
                'mean': 0.0,
                'std': 1.0,
                'samples': 0,
                'last_training_time': datetime.now().timestamp(),
                'last_if_train_size': 0,  # track how many samples used to train IF
            }
        )
        self.model_versions = defaultdict(lambda: {'version': 0, 'samples': 0})
        # SGD trainer per device
        self.sgd_trainers = defaultdict(
            lambda device_id=None: SGDModelTrainer(
                device_id if device_id else 'unknown',
                learning_rate=LEARNING_RATE,
            )
        )
        # Isolation Forest models per device
        self.if_models: Dict[str, IsolationForest] = {}

    def should_train_model(self, device_id: str) -> bool:
        """
        Determine if model should be trained based on:
        1. 50 new rows received since last training, OR
        2. 1 minute elapsed since last training
        """
        stats = self.device_stats[device_id]
        current_time = datetime.now().timestamp()
        time_elapsed = current_time - stats['last_training_time']

        # Train if 50 rows accumulated OR 60 seconds passed
        if stats['samples'] >= MODEL_TRAINING_INTERVAL_ROWS:
            return True
        if time_elapsed >= MODEL_TRAINING_INTERVAL_SECONDS:
            return True
        return False

    def _maybe_train_if_model(self, device_id: str):
        """
        Train or retrain Isolation Forest for this device
        using the current rolling values window.
        """
        stats = self.device_stats[device_id]
        values = stats['values']

        if len(values) < IF_MIN_SAMPLES:
            return  # not enough data yet

        last_size = stats.get('last_if_train_size', 0)
        if device_id in self.if_models and len(values) - last_size < IF_RETRAIN_DELTA:
            # not enough new points since last training
            return

        X = np.array(values, dtype=float).reshape(-1, 1)
        try:
            if_model = IsolationForest(
                n_estimators=IF_N_ESTIMATORS,
                contamination=IF_CONTAMINATION,
                random_state=42,
            )
            if_model.fit(X)
            self.if_models[device_id] = if_model
            stats['last_if_train_size'] = len(values)
            logger.info(
                f"Trained IsolationForest for device {device_id} on {len(values)} samples"
            )
        except Exception as e:
            logger.error(f"Error training IsolationForest for {device_id}: {e}")

    def _compute_features_and_label(
        self, device_id: str, value: float, stats: Dict[str, Any]
    ):
        """
        Compute feature vector and anomaly label for a given value.
        If an Isolation Forest exists for this device, use it.
        Otherwise, fall back to z-score based labeling.
        Returns:
          features (np.array of shape (3,)),
          label (int: 0/1),
          anomaly_score (float),
          method (str)
        """
        mean = stats['mean']
        std = stats['std']

        if device_id in self.if_models:
            # Isolation Forest based anomaly detection
            if_model = self.if_models[device_id]
            sample = np.array([[value]], dtype=float)
            try:
                pred = int(if_model.predict(sample)[0])  # 1=normal, -1=anomaly
                score = float(-if_model.score_samples(sample)[0])  # higher = more anomalous
            except Exception as e:
                logger.error(f"IsolationForest prediction error for {device_id}: {e}")
                # Fallback to non-anomalous
                pred = 1
                score = 0.0

            label = 1 if pred == -1 else 0
            features = np.array([mean, std, score], dtype=float)
            method = 'isolation_forest'
            return features, label, score, method
        else:
            # Fallback: z-score anomaly detection (cold start before IF is available)
            if std > 0:
                z_score = abs((value - mean) / std)
            else:
                z_score = 0.0

            label = 1 if z_score > ANOMALY_THRESHOLD else 0
            features = np.array([mean, std, z_score], dtype=float)
            method = 'z_score'
            return features, label, float(z_score), method

    def map(self, element):
        """Process incoming IoT data and train local models"""
        try:
            data = json.loads(element)
            device_id = data.get('device_id', 'unknown')
            value = data.get('data', 0.0)  # Single numeric metric

            results = {'anomalies': [], 'models': []}

            # Update device statistics
            stats = self.device_stats[device_id]
            stats['values'].append(value)
            stats['samples'] += 1

            # Keep rolling window of 100 values
            if len(stats['values']) > 100:
                stats['values'].pop(0)

            # Update statistics
            if len(stats['values']) > 1:
                stats['mean'] = float(np.mean(stats['values']))
                stats['std'] = float(np.std(stats['values']))

            # Train / retrain Isolation Forest if enough data
            self._maybe_train_if_model(device_id)

            # --- Anomaly detection (Isolation Forest first, z-score as fallback) ---
            features, label, anomaly_score, method = self._compute_features_and_label(
                device_id, value, stats
            )

            if label == 1:
                # anomaly detected
                severity = 'critical' if anomaly_score > 2 * ANOMALY_THRESHOLD else 'warning'
                anomaly_event = {
                    'device_id': device_id,
                    'value': float(value),
                    # "z_score" kept for backward compatibility; now carries the anomaly score
                    'z_score': float(anomaly_score),
                    'method': method,
                    'severity': severity,
                    'timestamp': datetime.now().isoformat(),
                }
                results['anomalies'].append(json.dumps(anomaly_event))

            # --- Local model training (same cadence as before) ---
            if self.should_train_model(device_id):
                model = self.model_versions[device_id]
                model['version'] += 1

                # Reset training counters
                stats['samples'] = 0
                stats['last_training_time'] = datetime.now().timestamp()

                # SGD Training on accumulated values
                if len(stats['values']) >= 2:
                    X_train = []
                    y_train = []

                    for v in stats['values']:
                        f_vec, lbl, _, _ = self._compute_features_and_label(
                            device_id, v, stats
                        )
                        X_train.append(f_vec)
                        y_train.append(lbl)

                    X_train = np.array(X_train, dtype=float)
                    y_train = np.array(y_train, dtype=int)

                    # Get trainer for this device
                    trainer = self.sgd_trainers[device_id]
                    trainer.device_id = device_id  # Ensure device_id is set

                    # Train on batch
                    loss = trainer.train_batch(X_train, y_train)

                    # Calculate accuracy on training data
                    accuracy = trainer.calculate_accuracy(X_train, y_train)

                    # Save model to disk
                    trainer.save_model(model['version'])

                    logger.info(
                        f"Device {device_id}: v{model['version']} - "
                        f"Accuracy: {accuracy:.2%}, Loss: {loss:.4f}, Updates: {trainer.n_updates}"
                    )
                else:
                    accuracy = 0.5  # Random guess if not enough data
                    loss = 0.0

                # Create model update message with REAL accuracy
                model_update = {
                    'device_id': device_id,
                    'model_version': model['version'],
                    'accuracy': float(accuracy),  # REAL accuracy from SGD!
                    'loss': float(loss),
                    'samples_processed': len(stats['values']),
                    'mean': float(stats['mean']),
                    'std': float(stats['std']),
                    'timestamp': datetime.now().isoformat(),
                }
                results['models'].append(json.dumps(model_update))

            return json.dumps(results)

        except Exception as e:
            logger.error(f"Error in map(): {e}")
            return json.dumps({'anomalies': [], 'models': []})


def main():
    """Main Flink job"""
    if not FLINK_AVAILABLE:
        logger.error("ERROR: Flink not available. This script must run in Flink Docker container.")
        logger.error("Run inside Docker with: docker exec flink-jobmanager flink run -py ...")
        return

    logger.info("Starting Flink Local Training Job with Isolation Forest anomaly detection")

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(4)

    # Kafka Source (new API for Flink 1.18+)
    kafka_source = KafkaSource.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_topics(INPUT_TOPIC) \
        .set_group_id('flink-training') \
        .set_starting_offsets(KafkaOffsetsInitializer.latest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    # Process stream with WatermarkStrategy
    stream = env.from_source(
        kafka_source,
        WatermarkStrategy.no_watermarks(),
        "kafka-source"
    )
    processed = stream.map(AnomalyDetectionFunction(), output_type=Types.STRING())

    # Parse results and split streams
    def extract_anomalies(element):
        data = json.loads(element)
        return '\n'.join(data.get('anomalies', []))

    def extract_models(element):
        data = json.loads(element)
        return '\n'.join(data.get('models', []))

    anomalies = processed.map(
        extract_anomalies, output_type=Types.STRING()
    ).filter(lambda x: len(x) > 0)
    models = processed.map(
        extract_models, output_type=Types.STRING()
    ).filter(lambda x: len(x) > 0)

    # Kafka Sinks (new API for Flink 1.18+)
    anomaly_sink = KafkaSink.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
                .set_topic(ANOMALY_OUTPUT_TOPIC)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
        ) \
        .build()

    model_sink = KafkaSink.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
                .set_topic(MODEL_UPDATE_TOPIC)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
        ) \
        .build()

    anomalies.sink_to(anomaly_sink)
    models.sink_to(model_sink)

    env.execute("Local Training Job (Isolation Forest)")


if __name__ == '__main__':
    main()

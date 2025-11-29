"""
Flink Local Model Training Job
Real-time streaming anomaly detection and local model training per device

Anomaly Detection Method: Random Cut Forest (RCF)
- Streaming-friendly unsupervised anomaly detection
- No need for pre-defined thresholds based on distribution assumptions
- Automatically adapts to data patterns

NOTE: This script runs INSIDE the Flink Docker container, not on the host machine.
The Docker image (flink:1.18-java11) contains all necessary Java/Flink dependencies.

To submit this job to Flink:
  docker exec flink-jobmanager flink run -py /opt/flink/scripts/03_flink_local_training.py

For development/testing, see: scripts/flink_local_training_simulator.py
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import numpy as np
from collections import defaultdict
import sys
import pickle
from pathlib import Path
import os  # for env + paths
import random

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
    # Host mapping to 9092 is only for clients on the host.
    KAFKA_BROKER = "kafka-broker-1:9092"
    logger.info(f"Using default internal Kafka bootstrap: {KAFKA_BROKER}")

INPUT_TOPIC = "edge-iiot-stream"
ANOMALY_OUTPUT_TOPIC = "anomalies"
MODEL_UPDATE_TOPIC = "local-model-updates"

WINDOW_SIZE_SECONDS = 30
# RCF anomaly score threshold (0-1 scale, higher = more anomalous)
# 0.5 is a good default, lower = more sensitive
ANOMALY_SCORE_THRESHOLD = 0.4
MODEL_TRAINING_INTERVAL_ROWS = 30   # Train model every 30 rows per device (optimized from 50)
MODEL_TRAINING_INTERVAL_SECONDS = 45  # OR every 45 seconds (optimized from 60)

# -------------------------------------------------------------------
# Random Cut Forest Configuration
# -------------------------------------------------------------------
RCF_NUM_TREES = 50          # Number of trees in the forest
RCF_TREE_SIZE = 256         # Max samples per tree
RCF_SHINGLE_SIZE = 4        # Sliding window for temporal patterns

# -------------------------------------------------------------------
# SGD Configuration
# -------------------------------------------------------------------
# Use a writable directory inside Flink container
MODEL_DIR = Path(os.getenv("LOCAL_MODEL_DIR", "/opt/flink/models/local"))

LEARNING_RATE = 0.001  # Reduced from 0.01
BATCH_SIZE = 50


# -------------------------------------------------------------------
# Random Cut Forest Implementation
# -------------------------------------------------------------------
class RandomCutTree:
    """A single Random Cut Tree for anomaly detection"""
    
    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self.points: List[np.ndarray] = []
        self.bounding_box: Optional[Tuple[np.ndarray, np.ndarray]] = None
    
    def insert(self, point: np.ndarray) -> None:
        """Insert a point into the tree"""
        self.points.append(point.copy())
        
        # Update bounding box
        if self.bounding_box is None:
            self.bounding_box = (point.copy(), point.copy())
        else:
            self.bounding_box = (
                np.minimum(self.bounding_box[0], point),
                np.maximum(self.bounding_box[1], point)
            )
        
        # Remove oldest point if tree is full
        if len(self.points) > self.max_size:
            self.points.pop(0)
            self._rebuild_bounding_box()
    
    def _rebuild_bounding_box(self) -> None:
        """Rebuild bounding box from all points"""
        if not self.points:
            self.bounding_box = None
            return
        points_array = np.array(self.points)
        self.bounding_box = (
            np.min(points_array, axis=0),
            np.max(points_array, axis=0)
        )
    
    def displacement(self, point: np.ndarray) -> float:
        """
        Calculate the displacement score for a point.
        Higher displacement = more anomalous.
        """
        if len(self.points) < 2 or self.bounding_box is None:
            return 0.0
        
        # Calculate how much the bounding box would change
        new_min = np.minimum(self.bounding_box[0], point)
        new_max = np.maximum(self.bounding_box[1], point)
        
        old_span = self.bounding_box[1] - self.bounding_box[0]
        new_span = new_max - new_min
        
        # Avoid division by zero
        old_span = np.where(old_span < 1e-10, 1e-10, old_span)
        
        # Displacement is the relative increase in bounding box
        displacement = np.sum(np.abs(new_span - old_span) / old_span)
        
        return float(displacement)
    
    def collusive_displacement(self, point: np.ndarray) -> float:
        """
        Calculate CoDisp (Collusive Displacement) - the key RCF metric.
        This measures how the point affects the model complexity.
        """
        if len(self.points) < 5:
            return 0.0
        
        # Calculate distance to nearest neighbors
        points_array = np.array(self.points)
        distances = np.linalg.norm(points_array - point, axis=1)
        
        # Get average distance to 5 nearest neighbors
        k = min(5, len(distances))
        nearest_distances = np.partition(distances, k-1)[:k]
        avg_neighbor_dist = np.mean(nearest_distances)
        
        # Get average distance between all points
        if len(self.points) > 1:
            all_distances = []
            for i, p in enumerate(self.points[:min(20, len(self.points))]):
                for q in self.points[i+1:min(20, len(self.points))]:
                    all_distances.append(np.linalg.norm(p - q))
            avg_all_dist = np.mean(all_distances) if all_distances else 1.0
        else:
            avg_all_dist = 1.0
        
        # Avoid division by zero
        if avg_all_dist < 1e-10:
            avg_all_dist = 1e-10
        
        # CoDisp score: ratio of point's isolation to average density
        codisp = avg_neighbor_dist / avg_all_dist
        
        return float(codisp)


class RandomCutForest:
    """
    Random Cut Forest for streaming anomaly detection.
    
    RCF is an unsupervised algorithm that:
    - Maintains a forest of random trees
    - Each tree has a bounded size (old points are removed)
    - Anomaly score is based on how much a point "displaces" the model
    """
    
    def __init__(self, num_trees: int = 50, tree_size: int = 256, shingle_size: int = 4):
        self.num_trees = num_trees
        self.tree_size = tree_size
        self.shingle_size = shingle_size
        self.trees = [RandomCutTree(max_size=tree_size) for _ in range(num_trees)]
        self.shingle_buffer: List[float] = []
        self.points_seen = 0
        self.score_history: List[float] = []
    
    def _create_shingle(self, value: float) -> Optional[np.ndarray]:
        """Create a shingle (sliding window) from the value stream"""
        self.shingle_buffer.append(value)
        
        if len(self.shingle_buffer) > self.shingle_size * 2:
            self.shingle_buffer = self.shingle_buffer[-self.shingle_size * 2:]
        
        if len(self.shingle_buffer) < self.shingle_size:
            return None
        
        # Create shingle from last N values
        shingle = np.array(self.shingle_buffer[-self.shingle_size:])
        return shingle
    
    def update(self, value: float) -> float:
        """
        Update the forest with a new value and return anomaly score.
        
        Returns:
            Anomaly score between 0 and 1 (higher = more anomalous)
        """
        shingle = self._create_shingle(value)
        
        if shingle is None:
            return 0.0
        
        self.points_seen += 1
        
        # Calculate anomaly score across all trees
        scores = []
        for tree in self.trees:
            # Use combination of displacement and collusive displacement
            disp = tree.displacement(shingle)
            codisp = tree.collusive_displacement(shingle)
            
            # Combined score
            score = 0.3 * disp + 0.7 * codisp
            scores.append(score)
            
            # Update tree with new point
            tree.insert(shingle)
        
        # Average score across trees
        raw_score = np.mean(scores)
        
        # Track score history for normalization
        self.score_history.append(raw_score)
        if len(self.score_history) > 1000:
            self.score_history = self.score_history[-500:]
        
        # Normalize score to 0-1 range based on history
        if len(self.score_history) > 10:
            score_mean = np.mean(self.score_history)
            score_std = np.std(self.score_history)
            if score_std > 0:
                # Convert to percentile-like score
                normalized = (raw_score - score_mean) / (score_std * 3) + 0.5
                normalized = np.clip(normalized, 0, 1)
            else:
                normalized = 0.5
        else:
            # Not enough history, use raw score
            normalized = min(raw_score, 1.0)
        
        return float(normalized)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get forest statistics"""
        return {
            "num_trees": self.num_trees,
            "tree_size": self.tree_size,
            "shingle_size": self.shingle_size,
            "points_seen": self.points_seen,
            "avg_tree_size": np.mean([len(t.points) for t in self.trees]),
        }


class SGDModelTrainer:
    """Stochastic Gradient Descent trainer for local models"""

    def __init__(self, device_id: str, learning_rate: float = 0.001):
        self.device_id = device_id
        self.learning_rate = learning_rate  # 0.001 to prevent saturation
        # SMALLER INITIALIZATION: Start closer to 0 to avoid early saturation
        self.weights = np.random.normal(0, 0.01, 3)  # 3 features: mean, std, normalized_value
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
    """
    Flink MapFunction for real-time anomaly detection using Random Cut Forest
    and local model training using SGD.
    """

    def __init__(self):
        super().__init__()
        self.device_stats = defaultdict(
            lambda: {
                "values": [],
                "mean": 0.0,
                "std": 1.0,
                "samples": 0,
                "last_training_time": datetime.now().timestamp(),
                "anomaly_scores": [],
            }
        )
        self.model_versions = defaultdict(lambda: {"version": 0, "samples": 0})
        # SGD trainer per device
        self.sgd_trainers = defaultdict(
            lambda: SGDModelTrainer("unknown", learning_rate=LEARNING_RATE)
        )
        # Random Cut Forest per device
        self.rcf_models = defaultdict(
            lambda: RandomCutForest(
                num_trees=RCF_NUM_TREES,
                tree_size=RCF_TREE_SIZE,
                shingle_size=RCF_SHINGLE_SIZE
            )
        )
        self.anomaly_count = 0

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
        """Process incoming IoT data using RCF for anomaly detection"""
        try:
            data = json.loads(element)
            device_id = data.get("device_id", "unknown")
            value = float(data.get("data", 0.0))  # Single numeric metric

            results = {"anomalies": [], "models": []}

            # Update device statistics
            stats = self.device_stats[device_id]
            stats["values"].append(value)
            stats["samples"] += 1

            # Keep rolling window of 100 values
            if len(stats["values"]) > 100:
                stats["values"].pop(0)

            # Update mean / std for features
            if len(stats["values"]) > 1:
                stats["mean"] = float(np.mean(stats["values"]))
                stats["std"] = float(np.std(stats["values"]))

            # ============================================================
            # Random Cut Forest Anomaly Detection
            # ============================================================
            rcf = self.rcf_models[device_id]
            anomaly_score = rcf.update(value)
            
            # Track anomaly scores for this device
            stats["anomaly_scores"].append(anomaly_score)
            if len(stats["anomaly_scores"]) > 100:
                stats["anomaly_scores"].pop(0)

            # Check if anomaly (score > threshold)
            if anomaly_score > ANOMALY_SCORE_THRESHOLD:
                self.anomaly_count += 1
                
                # Determine severity based on score
                if anomaly_score > 0.8:
                    severity = "critical"
                elif anomaly_score > 0.6:
                    severity = "warning"
                else:
                    severity = "info"
                
                anomaly = {
                    "device_id": device_id,
                    "value": value,
                    "anomaly_score": float(anomaly_score),
                    "severity": severity,
                    "detection_method": "random_cut_forest",
                    "timestamp": datetime.now().isoformat(),
                }
                results["anomalies"].append(json.dumps(anomaly))
                
                logger.info(
                    f"🚨 ANOMALY [{severity.upper()}] device={device_id} "
                    f"value={value:.2f} score={anomaly_score:.3f}"
                )

            # ============================================================
            # Model Training (SGD)
            # ============================================================
            if self.should_train_model(device_id):
                model = self.model_versions[device_id]
                model["version"] += 1

                # Reset counters
                stats["samples"] = 0
                stats["last_training_time"] = datetime.now().timestamp()

                if len(stats["values"]) >= 2:
                    X_train = []
                    y_train = []

                    for i, v in enumerate(stats["values"]):
                        # Use anomaly scores as labels (threshold-based)
                        if i < len(stats["anomaly_scores"]):
                            score = stats["anomaly_scores"][i]
                        else:
                            score = 0.0

                        # Features: [mean, std, normalized_value]
                        norm_val = (v - stats["mean"]) / stats["std"] if stats["std"] > 0 else 0
                        features = np.array([stats["mean"], stats["std"], norm_val])
                        X_train.append(features)

                        # Label: 1 if anomaly score was high, else 0
                        label = 1 if score > ANOMALY_SCORE_THRESHOLD else 0
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
    """Main Flink job with parallelism optimization"""
    if not FLINK_AVAILABLE:
        logger.error("ERROR: Flink not available. This script must run in Flink Docker container.")
        logger.error("Run inside Docker with: docker exec flink-jobmanager flink run -py ...")
        return

    logger.info("Starting Flink Local Training Job (with parallelism)")
    logger.info(f"Using Kafka bootstrap servers: {KAFKA_BROKER}")

    env = StreamExecutionEnvironment.get_execution_environment()
    
    # Enable parallelism - use available task slots (default 2-4 for better throughput)
    # This will be limited by taskmanager.numberOfTaskSlots in flink-conf.yaml
    PARALLELISM = int(os.getenv("FLINK_PARALLELISM", "2"))
    env.set_parallelism(PARALLELISM)
    logger.info(f"Parallelism set to: {PARALLELISM}")
    
    # Enable checkpointing for fault tolerance (every 60 seconds)
    env.enable_checkpointing(60000)
    
    # Optimize buffer timeout for lower latency
    env.set_buffer_timeout(100)  # 100ms buffer timeout

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
    
    # ============================================================
    # KEY BY DEVICE_ID for proper parallelism
    # This ensures all data for a device goes to the same parallel task
    # ============================================================
    def extract_device_id(element: str) -> str:
        """Extract device_id for keying"""
        try:
            data = json.loads(element)
            return data.get("device_id", "unknown")
        except:
            return "unknown"
    
    # Key by device_id, then process with stateful function
    keyed_stream = stream.key_by(extract_device_id)
    
    processed = keyed_stream.map(AnomalyDetectionFunction(), output_type=Types.STRING())

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

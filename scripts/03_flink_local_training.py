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

# Try to import Flink (will be available in Docker container)
try:
    from pyflink.datastream import StreamExecutionEnvironment
    from pyflink.datastream.functions import MapFunction
    from pyflink.common.serialization import SimpleStringSchema
    from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer, KafkaSink, KafkaRecordSerializationSchema
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
ANOMALY_THRESHOLD = 2.5
MODEL_TRAINING_INTERVAL_ROWS = 50  # Train model every 50 rows per device
MODEL_TRAINING_INTERVAL_SECONDS = 60  # OR every 60 seconds (1 minute)

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
        self.weights = np.random.normal(0, 0.01, 3)  # 3 features: mean, std, z_score
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
        soft_accuracy = np.mean([pred if y == 1 else (1 - pred) 
                                 for pred, y in zip(predictions, y)])
        
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
                'loss_history': self.loss_history
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
        self.device_stats = defaultdict(lambda: {
            'values': [], 
            'mean': 0.0, 
            'std': 1.0,
            'samples': 0,
            'last_training_time': datetime.now().timestamp()
        })
        self.model_versions = defaultdict(lambda: {'version': 0, 'samples': 0})
        # SGD trainer per device
        self.sgd_trainers = defaultdict(lambda device_id=None: SGDModelTrainer(
            device_id if device_id else 'unknown',
            learning_rate=LEARNING_RATE
        ))
    
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
                stats['mean'] = np.mean(stats['values'])
                stats['std'] = np.std(stats['values'])
            
            # Z-score anomaly detection
            if stats['std'] > 0:
                z_score = abs((value - stats['mean']) / stats['std'])
                
                if z_score > ANOMALY_THRESHOLD:
                    severity = 'critical' if z_score > ANOMALY_THRESHOLD * 2 else 'warning'
                    anomaly = {
                        'device_id': device_id,
                        'value': value,
                        'z_score': float(z_score),
                        'severity': severity,
                        'timestamp': datetime.now().isoformat()
                    }
                    results['anomalies'].append(json.dumps(anomaly))
            
            # Check if model training is needed (every 50 rows OR 60 seconds)
            if self.should_train_model(device_id):
                model = self.model_versions[device_id]
                model['version'] += 1
                
                # Reset training counters
                stats['samples'] = 0
                stats['last_training_time'] = datetime.now().timestamp()
                
                # SGD Training on accumulated values
                if len(stats['values']) >= 2:
                    # Create training data from stats
                    X_train = []
                    y_train = []
                    
                    for v in stats['values']:
                        z_score = abs((v - stats['mean']) / stats['std']) if stats['std'] > 0 else 0
                        
                        # Features: [mean, std, z_score]
                        features = np.array([stats['mean'], stats['std'], z_score])
                        X_train.append(features)
                        
                        # Label: 1 if anomaly (z > threshold), 0 otherwise
                        label = 1 if z_score > ANOMALY_THRESHOLD else 0
                        y_train.append(label)
                    
                    X_train = np.array(X_train)
                    y_train = np.array(y_train)
                    
                    # Get trainer for this device
                    trainer = self.sgd_trainers[device_id]
                    trainer.device_id = device_id  # Ensure device_id is set
                    
                    # Train on batch
                    loss = trainer.train_batch(X_train, y_train)
                    
                    # Calculate accuracy on training data
                    accuracy = trainer.calculate_accuracy(X_train, y_train)
                    
                    # Save model to disk
                    trainer.save_model(model['version'])
                    
                    logger.info(f"Device {device_id}: v{model['version']} - Accuracy: {accuracy:.2%}, Loss: {loss:.4f}, Updates: {trainer.n_updates}")
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
                    'timestamp': datetime.now().isoformat()
                }
                results['models'].append(json.dumps(model_update))
            
            return json.dumps(results)
        
        except Exception as e:
            logger.error(f"Error: {e}")
            return json.dumps({'anomalies': [], 'models': []})


def main():
    """Main Flink job"""
    if not FLINK_AVAILABLE:
        logger.error("ERROR: Flink not available. This script must run in Flink Docker container.")
        logger.error("Run inside Docker with: docker exec flink-jobmanager flink run -py ...")
        return
    
    logger.info("Starting Flink Local Training Job")
    
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(4)
    
    # Kafka connector JARs are pre-installed in Docker image at /opt/flink/lib/
    # No need to add them explicitly - Flink automatically loads JARs from lib directory
    
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
    
    anomalies = processed.map(extract_anomalies, output_type=Types.STRING()).filter(lambda x: len(x) > 0)
    models = processed.map(extract_models, output_type=Types.STRING()).filter(lambda x: len(x) > 0)
    
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
    
    env.execute("Local Training Job")


if __name__ == '__main__':
    main()


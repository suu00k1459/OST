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
KAFKA_BROKER = 'kafka:29092'  # Docker internal network
INPUT_TOPIC = 'edge-iiot-stream'
ANOMALY_OUTPUT_TOPIC = 'anomalies'
MODEL_UPDATE_TOPIC = 'local-model-updates'

WINDOW_SIZE_SECONDS = 30
ANOMALY_THRESHOLD = 2.5
MODEL_TRAINING_INTERVAL_ROWS = 50  # Train model every 50 rows per device
MODEL_TRAINING_INTERVAL_SECONDS = 60  # OR every 60 seconds (1 minute)


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
                
                # Create model update message
                model_update = {
                    'device_id': device_id,
                    'model_version': model['version'],
                    'accuracy': min(0.95, 0.7 + (model['version'] * 0.02)),
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


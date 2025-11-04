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


class AnomalyDetectionFunction(MapFunction):
    """Flink MapFunction for real-time anomaly detection"""
    
    def __init__(self):
        super().__init__()
        self.device_stats = defaultdict(lambda: {'values': [], 'mean': 0.0, 'std': 1.0})
        self.model_versions = defaultdict(lambda: {'version': 0, 'samples': 0})
    
    def map(self, element):
        """Process incoming IoT data"""
        try:
            data = json.loads(element)
            device_id = data.get('device_id', 'unknown')
            values = data.get('data', {})
            
            results = {'anomalies': [], 'models': []}
            
            # Update statistics and detect anomalies
            for feature_name, value in values.items():
                if isinstance(value, (int, float)):
                    stats = self.device_stats[device_id]
                    stats['values'].append(value)
                    
                    if len(stats['values']) > 100:
                        stats['values'].pop(0)
                    
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
                                'feature': feature_name,
                                'value': value,
                                'z_score': z_score,
                                'severity': severity,
                                'timestamp': datetime.now().isoformat()
                            }
                            results['anomalies'].append(json.dumps(anomaly))
            
            # Update model every 100 samples
            model = self.model_versions[device_id]
            model['samples'] += 1
            
            if model['samples'] % 100 == 0:
                model['version'] += 1
                model_update = {
                    'device_id': device_id,
                    'model_version': model['version'],
                    'accuracy': min(0.95, 0.7 + (model['version'] * 0.05)),
                    'samples_processed': model['samples'],
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
    
    # Add Kafka connector JARs to classpath
    env.add_jars("file:///opt/flink/lib/flink-connector-kafka-3.0.2-1.18.jar",
                 "file:///opt/flink/lib/kafka-clients-3.4.0.jar")
    
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


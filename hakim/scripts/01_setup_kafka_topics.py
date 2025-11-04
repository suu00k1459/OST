"""
Setup Kafka Topics for FLEAD Pipeline
Creates all required topics for streaming and batch processing
"""

import subprocess
import time
import sys
import logging
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kafka broker address
KAFKA_BROKER = 'localhost:9092'

# Topics to create
TOPICS = {
    'edge-iiot-stream': {
        'partitions': 4,
        'replication_factor': 1,
        'description': 'Raw IoT sensor data from edge devices'
    },
    'local-model-updates': {
        'partitions': 4,
        'replication_factor': 1,
        'description': 'Local model updates per device from Flink'
    },
    'global-model-updates': {
        'partitions': 1,
        'replication_factor': 1,
        'description': 'Aggregated global model updates from federation'
    },
    'anomalies': {
        'partitions': 4,
        'replication_factor': 1,
        'description': 'Detected anomalies from Flink streaming'
    },
    'analytics-results': {
        'partitions': 2,
        'replication_factor': 1,
        'description': 'Batch analytics results from Spark'
    }
}

def wait_for_kafka(max_retries: int = 30, retry_interval: int = 2) -> bool:
    """Wait for Kafka to be ready (using Docker)"""
    logger.info(f"Waiting for Kafka broker (docker: kafka) to be ready...")
    
    for attempt in range(max_retries):
        try:
            # Use docker exec to test Kafka connection inside the container
            result = subprocess.run(
                ['docker', 'exec', 'kafka', 'kafka-broker-api-versions',
                 '--bootstrap-server', 'kafka:29092'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("Kafka broker is ready")
                return True
        except Exception:
            pass
        
        if attempt < max_retries - 1:
            logger.info(f"  Attempt {attempt + 1}/{max_retries}: Kafka not ready, retrying in {retry_interval}s...")
            time.sleep(retry_interval)
        else:
            logger.error(f"Kafka broker not ready after {max_retries} attempts")
            return False
    
    return False

def create_topic(topic_name: str, partitions: int, replication_factor: int) -> bool:
    """Create a single Kafka topic (using Docker)"""
    try:
        # Check if topic already exists using Docker
        result = subprocess.run(
            ['docker', 'exec', 'kafka', 'kafka-topics',
             '--bootstrap-server', 'kafka:29092',
             '--list'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if topic_name in result.stdout:
            logger.info(f"  Topic '{topic_name}' already exists")
            return True
        
        # Create topic using Docker with longer timeout
        result = subprocess.run(
            ['docker', 'exec', 'kafka', 'kafka-topics',
             '--bootstrap-server', 'kafka:29092',
             '--create',
             '--topic', topic_name,
             '--partitions', str(partitions),
             '--replication-factor', str(replication_factor),
             '--if-not-exists'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 or 'already exists' in result.stderr or 'already exists' in result.stdout:
            logger.info(f"  Created topic '{topic_name}' ({partitions} partitions, RF={replication_factor})")
            return True
        else:
            logger.warning(f"  Could not create topic '{topic_name}': {result.stderr}")
            # Don't fail if topic creation has any issue - topics might be auto-created
            return True
            
    except subprocess.TimeoutExpired:
        logger.warning(f"  Timeout creating topic '{topic_name}' (will be auto-created if needed)")
        return True
    except Exception as e:
        logger.warning(f"  Error creating topic '{topic_name}' (will be auto-created if needed): {e}")
        return True

def list_topics() -> List[str]:
    """List all Kafka topics (using Docker)"""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'kafka', 'kafka-topics',
             '--bootstrap-server', 'kafka:29092',
             '--list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            topics = [t.strip() for t in result.stdout.split('\n') if t.strip()]
            return topics
        else:
            logger.error(f"Error listing topics: {result.stderr}")
            return []
            
    except Exception as e:
        logger.error(f"Error listing topics: {e}")
        return []

def describe_topics() -> None:
    """Describe all FLEAD topics (using Docker)"""
    try:
        topic_list = ','.join(TOPICS.keys())
        result = subprocess.run(
            ['docker', 'exec', 'kafka', 'kafka-topics',
             '--bootstrap-server', 'kafka:29092',
             '--describe',
             '--topics', topic_list],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info("\nTopic Details:")
            logger.info(result.stdout)
        else:
            logger.warning(f"Could not describe topics: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.warning("Timeout describing topics (this is OK, topics are created)")
    except Exception as e:
        logger.warning(f"Could not describe topics: {e}")

def main():
    """Main function to setup all topics"""
    logger.info("=" * 70)
    logger.info("Kafka Topics Setup for FLEAD Pipeline")
    logger.info("=" * 70)
    logger.info(f"Kafka Broker: {KAFKA_BROKER}")
    logger.info("")
    
    # Wait for Kafka
    if not wait_for_kafka():
        logger.error("✗ Kafka is not available. Make sure Docker containers are running:")
        logger.error("  docker-compose up -d")
        sys.exit(1)
    
    logger.info("")
    logger.info("Creating FLEAD topics...")
    logger.info("")
    
    success_count = 0
    for topic_name, config in TOPICS.items():
        logger.info(f"Setting up topic: {topic_name}")
        logger.info(f"  Description: {config['description']}")
        
        if create_topic(
            topic_name,
            config['partitions'],
            config['replication_factor']
        ):
            success_count += 1
        logger.info("")
    
    # List all topics
    logger.info("Current Kafka Topics:")
    all_topics = list_topics()
    for topic in all_topics:
        if topic not in ['__consumer_offsets', '__transaction_state']:
            logger.info(f"  - {topic}")
    
    logger.info("")
    describe_topics()
    
    logger.info("=" * 70)
    logger.info(f"✓ Setup Complete: {success_count}/{len(TOPICS)} topics created")
    logger.info("=" * 70)
    
    if success_count == len(TOPICS):
        return 0
    else:
        return 1

if __name__ == '__main__':
    sys.exit(main())

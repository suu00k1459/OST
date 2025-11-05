"""
FLEAD Pipeline Orchestrator
Complete startup and coordination of all pipeline components:
1. Kafka Producer → streams raw IoT data
2. Flink Local Training → detects anomalies per device, trains local models
3. Federated Aggregation → aggregates models to create global model
4. Spark Batch Analytics → long-term trend analysis and maintenance signals
5. Device Viewer Website → web interface for device exploration
"""

import subprocess
import time
import logging
import sys
import os
import signal
import threading
import webbrowser
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR = SCRIPTS_DIR.parent
LOG_DIR = ROOT_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Kafka configuration
KAFKA_BROKER = 'localhost:9092'

# Component timeouts (seconds)
COMPONENT_STARTUP_TIMEOUT = 30
HEALTH_CHECK_INTERVAL = 5
MAX_HEALTH_CHECK_RETRIES = 10

# Service configurations
SERVICES = {
    'kafka_topics': {
        'description': 'Setup Kafka Topics',
        'command': ['python', str(SCRIPTS_DIR / '01_setup_kafka_topics.py')],
        'log_file': 'kafka_topics.log',
        'critical': True
    },
    'kafka_producer': {
        'description': 'Kafka Producer (Stream IoT Data)',
        'command': ['python', str(SCRIPTS_DIR / '02_kafka_producer.py'),
                   '--source', str(ROOT_DIR / 'data' / 'processed'),
                   '--mode', 'all-devices',
                   '--rate', '5',
                   '--repeat'],
        'log_file': 'kafka_producer.log',
        'critical': True,
        'background': True,
        'startup_delay': 5
    },
    'flink_training': {
        'description': 'Flink Local Model Training (Real-time Streaming)',
        'command': [
            'docker', 'exec', 'flink-jobmanager',
            'bash', '-c',
            # Check if job already running - fixed integer comparison
            'RUNNING_JOBS=$(flink list 2>/dev/null | grep -c RUNNING || echo "0"); '
            'if [ $RUNNING_JOBS -eq 0 ]; then '
            'cd /opt/flink && flink run -py /opt/flink/scripts/03_flink_local_training.py -d; '
            'else '
            'echo "Flink job already running ($RUNNING_JOBS jobs), skipping submission"; '
            'fi'
        ],
        'log_file': 'flink_training.log',
        'critical': True,
        'background': False,
        'startup_delay': 5,
        'requires_docker': True
    },
    'federated_aggregation': {
        'description': 'Federated Aggregation (Global Model)',
        'command': ['python', str(SCRIPTS_DIR / '04_federated_aggregation.py')],
        'log_file': 'federated_aggregation.log',
        'critical': True,
        'background': True,
        'startup_delay': 10
    },
    'spark_analytics': {
        'description': 'Spark Analytics (Batch + Stream + Model Evaluation)',
        'command': [
            'docker', 'exec', '-u', 'root', 'spark-master',
            'bash', '-c',
            'mkdir -p /home/spark/.ivy2/cache && '
            'chown -R spark:spark /home/spark/.ivy2 && '
            'chmod -R 755 /home/spark/.ivy2 && '
            'su spark -c "'
            '/opt/spark/bin/spark-submit '
            '--master spark://spark-master:7077 '
            '--deploy-mode client '
            '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 '
            '/opt/spark/scripts/05_spark_analytics.py'
            '"'
        ],
        'log_file': 'spark_analytics.log',
        'critical': True,
        'background': True,
        'startup_delay': 20,
        'requires_docker': True
    },
    'device_viewer': {
        'description': 'Device Viewer Website (Flask Web Interface)',
        'command': ['python', str(ROOT_DIR / 'website' / 'app.py')],
        'log_file': 'device_viewer.log',
        'critical': False,  # Not critical for core pipeline
        'background': True,
        'startup_delay': 3
    },
    'grafana_setup': {
        'description': 'Grafana Dashboard Configuration (Automated Setup)',
        'command': ['python', str(SCRIPTS_DIR / '06_setup_grafana.py')],
        'log_file': 'grafana_setup.log',
        'critical': False,  # Nice to have but not blocking
        'background': False,  # Foreground - completes quickly
        'startup_delay': 5
    }
}

# Running processes for cleanup
RUNNING_PROCESSES: Dict[str, subprocess.Popen] = {}


class PipelineOrchestrator:
    """Orchestrate the complete FLEAD pipeline"""
    
    def __init__(self):
        self.running_services = {}
        self.failed_services = []
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("\nShutdown signal received, stopping services...")
        self.cleanup()
        sys.exit(0)
    
    def check_docker_services(self) -> bool:
        """Check if Docker services are running"""
        logger.info("Checking Docker services...")
        required_services = ['kafka', 'timescaledb', 'flink-jobmanager', 'spark-master']
        
        try:
            result = subprocess.run(
                ['docker-compose', 'ps', '--services', '--filter', 'status=running'],
                capture_output=True,
                text=True,
                cwd=ROOT_DIR,
                timeout=10
            )
            
            running_services = set(result.stdout.strip().split('\n'))
            
            missing = [s for s in required_services if s not in running_services]
            
            if missing:
                logger.error(f"Missing Docker services: {missing}")
                logger.error("Start services with: docker-compose up -d")
                return False
            
            logger.info(f"All required Docker services running: {', '.join(required_services)}")
            return True
        
        except Exception as e:
            logger.error(f"Error checking Docker services: {e}")
            return False
    
    def check_kafka_topics(self) -> bool:
        """Verify Kafka topics are created"""
        logger.info("Checking Kafka topics...")
        required_topics = [
            'edge-iiot-stream',
            'local-model-updates',
            'global-model-updates',
            'anomalies',
            'analytics-results'
        ]
        
        try:
            result = subprocess.run(
                ['docker', 'exec', 'kafka', 'kafka-topics',
                 '--bootstrap-server', 'localhost:29092', '--list'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            existing_topics = set(result.stdout.strip().split('\n'))
            missing = [t for t in required_topics if t not in existing_topics]
            
            if missing:
                logger.info(f"Missing topics will be created: {missing}")
                return False
            
            logger.info(f"All Kafka topics exist")
            return True
        
        except Exception as e:
            logger.warning(f"Could not verify topics: {e}")
            return False
    
    def start_service(self, service_name: str, config: Dict) -> bool:
        """Start a single service"""
        logger.info(f"\n{'='*70}")
        logger.info(f"Starting: {config['description']}")
        logger.info(f"{'='*70}")
        
        log_file = LOG_DIR / config['log_file']
        
        try:
            with open(log_file, 'w') as log_f:
                process = subprocess.Popen(
                    config['command'],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=ROOT_DIR,
                    text=True
                )
            
            self.running_services[service_name] = process
            RUNNING_PROCESSES[service_name] = process
            
            # Wait for startup if background service
            if config.get('background'):
                startup_delay = config.get('startup_delay', 3)
                logger.info(f"  Starting service (startup delay: {startup_delay}s)...")
                time.sleep(startup_delay)
                
                # Check if process is still running
                if process.poll() is not None:
                    logger.error(f"Service crashed on startup")
                    logger.error(f"  Check logs: {log_file}")
                    return False
                
                logger.info(f"Service running (PID: {process.pid})")
                logger.info(f"  Logs: {log_file}")
            else:
                # Wait for foreground service to complete
                logger.info(f"  Waiting for service to complete...")
                return_code = process.wait()
                
                if return_code != 0:
                    logger.error(f"Service failed with exit code {return_code}")
                    logger.error(f"  Check logs: {log_file}")
                    return False
                
                logger.info(f"Service completed successfully")
            
            return True
        
        except Exception as e:
            logger.error(f"Error starting service: {e}")
            return False
    
    def start_all_services(self) -> bool:
        """Start all pipeline services in order"""
        logger.info("=" * 70)
        logger.info("FLEAD COMPLETE PIPELINE STARTUP")
        logger.info("=" * 70)
        logger.info(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Kafka Broker: {KAFKA_BROKER}")
        logger.info("=" * 70)
        
        # Check prerequisites
        if not self.check_docker_services():
            logger.error("\nDocker services not ready")
            logger.error("Start Docker services first:")
            logger.error("  docker-compose up -d")
            return False
        
        # Start services in order
        startup_order = [
            'kafka_topics',           # Stage 1: Create Kafka topics (HOST)
            'kafka_producer',         # Stage 2: Stream data (HOST)
            'flink_training',         # Stage 3: Real-time ML (Docker: Flink)
            'federated_aggregation',  # Stage 4: Model aggregation (HOST with Docker network)
            'spark_analytics',        # Stage 5: Batch analytics (Docker: Spark)
            'device_viewer',          # Stage 6: Web interface (HOST)
            'grafana_setup'           # Stage 7: Configure Grafana dashboards (HOST)
        ]
        
        # NOTE: Services now properly submitted to Docker containers
        # - kafka_topics/producer: Run on HOST (can connect to localhost:9092)
        # - flink_training: Submitted to flink-jobmanager container via docker exec
        # - spark_analytics: Submitted to spark-master container via docker exec
        # - federated_aggregation: Runs on HOST but needs Docker network (to be fixed)
        
        success_count = 0
        
        for service_name in startup_order:
            if service_name not in SERVICES:
                continue
            
            config = SERVICES[service_name]
            
            # ALL SERVICES ARE REQUIRED - DO NOT SKIP
            # Continue starting all services even if one fails
            # This allows us to see all errors at once
            
            if self.start_service(service_name, config):
                success_count += 1
            else:
                self.failed_services.append(service_name)
                logger.error(f"Service failed but continuing with remaining services...")
        
        # Report overall status
        if len(self.failed_services) > 0:
            logger.error(f"\n{'='*70}")
            logger.error(f"PIPELINE STARTUP INCOMPLETE")
            logger.error(f"{'='*70}")
            logger.error(f"Failed services: {', '.join(self.failed_services)}")
            logger.error(f"Successful services: {success_count}/{len(startup_order)}")
            return False
        
        return True
    
    def show_pipeline_status(self):
        """Display pipeline status"""
        logger.info("\n" + "=" * 70)
        logger.info("PIPELINE STATUS")
        logger.info("=" * 70)
        
        # Check running processes
        active_services = []
        for service_name, process in self.running_services.items():
            if process.poll() is None:  # Still running
                config = SERVICES.get(service_name, {})
                active_services.append(service_name)
                logger.info(f"{config.get('description', service_name)} (PID: {process.pid})")
        
        if not active_services:
            logger.warning("No services currently running")
        
        # Display access points
        logger.info("\n" + "=" * 70)
        logger.info("ACCESS POINTS")
        logger.info("=" * 70)
        logger.info("Grafana Dashboard:        http://localhost:3001 (admin/admin)")
        logger.info("Kafka UI:                 http://localhost:8081")
        logger.info("Device Viewer Website:    http://localhost:8082")
        logger.info("Flink Dashboard:          http://localhost:8161")
        logger.info("Spark Master:             http://localhost:8086")
        logger.info("TimescaleDB:              localhost:5432")
        
        # Display pipeline flow
        logger.info("\n" + "=" * 70)
        logger.info("PIPELINE FLOW")
        logger.info("=" * 70)
        logger.info("IoT Devices (CSV files)")
        logger.info("    ↓")
        logger.info("Kafka Producer")
        logger.info("    ↓")
        logger.info("edge-iiot-stream (Kafka Topic)")
        logger.info("    ├→ Flink (Real-time Local Training)")
        logger.info("    │  ├→ anomalies topic")
        logger.info("    │  └→ local-model-updates topic")
        logger.info("    │")
        logger.info("    └→ TimescaleDB (via aggregation service)")
        logger.info("        ↓")
        logger.info("Federated Aggregation Service")
        logger.info("    ↓")
        logger.info("global-model-updates topic")
        logger.info("    ↓")
        logger.info("Global Model")
        logger.info("    ↓")
        logger.info("Spark Batch Analytics (Historical Trends)")
        logger.info("    ↓")
        logger.info("Grafana Dashboards + Analytics Tables")
        
        logger.info("\n" + "=" * 70)
        logger.info("MONITORING")
        logger.info("=" * 70)
        logger.info(f"Log files location: {LOG_DIR}")
        logger.info("View logs:")
        for service_name in SERVICES:
            log_file = LOG_DIR / SERVICES[service_name]['log_file']
            logger.info(f"  tail -f {log_file}")
        
        logger.info("\n" + "=" * 70)
    
    def cleanup(self):
        """Cleanup and stop all services"""
        logger.info("\n" + "=" * 70)
        logger.info("CLEANUP - Stopping Services")
        logger.info("=" * 70)
        
        for service_name, process in self.running_services.items():
            if process.poll() is None:  # Still running
                try:
                    logger.info(f"Stopping {service_name} (PID: {process.pid})...")
                    process.terminate()
                    
                    # Wait for graceful shutdown
                    try:
                        process.wait(timeout=5)
                        logger.info(f"Stopped {service_name}")
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing {service_name}...")
                        process.kill()
                        process.wait()
                except Exception as e:
                    logger.warning(f"Error stopping {service_name}: {e}")
        
        logger.info("Cleanup complete")


def launch_web_interfaces():
    """Launch web browsers for all UI interfaces"""
    logger.info("\n" + "=" * 70)
    logger.info("LAUNCHING WEB INTERFACES")
    logger.info("=" * 70)
    
    # Wait a moment to ensure services are ready
    time.sleep(2)
    
    # URLs to open
    urls = [
        ('Device Viewer Website', 'http://localhost:8082'),
        ('Kafka UI', 'http://localhost:8081'),
        ('Grafana Dashboard', 'http://localhost:3001'),
        ('Flink Dashboard', 'http://localhost:8161')
    ]
    
    for name, url in urls:
        try:
            logger.info(f"Opening {name}: {url}")
            webbrowser.open(url, new=2)  # new=2 opens in a new tab if possible
            time.sleep(1)  # Small delay between launches
        except Exception as e:
            logger.warning(f"Could not open {name}: {e}")
    
    logger.info("=" * 70)


def main():
    """Main orchestrator"""
    orchestrator = PipelineOrchestrator()
    
    try:
        # Start all services
        if orchestrator.start_all_services():
            # Show status and keep running
            orchestrator.show_pipeline_status()
            
            logger.info("\nPipeline started successfully!")
            
            # Launch web interfaces in browser
            launch_web_interfaces()
            
            logger.info("\nPress Ctrl+C to stop\n")
            
            # Keep orchestrator running
            while True:
                time.sleep(1)
        else:
            logger.error("\nPipeline startup failed")
            sys.exit(1)
    
    except KeyboardInterrupt:
        orchestrator.cleanup()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        orchestrator.cleanup()
        sys.exit(1)


if __name__ == '__main__':
    main()

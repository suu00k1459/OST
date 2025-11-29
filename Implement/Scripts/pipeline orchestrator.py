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
KAFKA_BROKER = 'localhost:9092,localhost:9093,localhost:9094,localhost:9095'

# Component timeouts (seconds)
COMPONENT_STARTUP_TIMEOUT = 30
HEALTH_CHECK_INTERVAL = 5
MAX_HEALTH_CHECK_RETRIES = 10

# Service configurations
SERVICES = {
    'database_init': {
        'description': 'Initialize TimescaleDB Schema',
        # Use the `database-init` Docker service
        'command': ['docker-compose', 'run', '--rm', 'database-init'],
        'log_file': 'database_init.log',
        'critical': True,
        'background': False,
        'startup_delay': 0
    },
    'kafka_topics': {
        'description': 'Setup Kafka Topics',
        'command': ['python', str(SCRIPTS_DIR / '01_setup_kafka_topics.py')],
        'log_file': 'kafka_topics.log',
        'critical': True
    },
    'kafka_producer': {
        'description': 'Kafka Producer (Stream IoT Data)',
        'command': ['python', str(SCRIPTS_DIR / '02_kafka_producer_multi_broker.py'),
                    '--source', str(ROOT_DIR / 'data' / 'processed'),
                    '--rate', '5'],
        'log_file': 'kafka_producer.log',
        'critical': True,
        'background': True,
        'startup_delay': 30
    },
    'flink_training': {
        'description': 'Flink Local Model Training (Real-time Streaming)',
        'command': [
            'docker', 'exec', 'flink-jobmanager',
            'bash', '-c',
            # Check if job already running - robust version
            'RUNNING_JOBS=$(flink list 2>/dev/null | grep -c "RUNNING" || true); '
            'RUNNING_JOBS=$(echo "$RUNNING_JOBS" | tr -d "\\n" | tr -d " "); '
            'if [ "$RUNNING_JOBS" = "0" ] || [ -z "$RUNNING_JOBS" ]; then '
            'echo "No Flink jobs running, submitting job..."; '
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
        # Use the `federated-aggregator` Docker service
        'command': ['docker-compose', 'run', '--rm', 'federated-aggregator'],
        'log_file': 'federated_aggregation.log',
        'critical': True,
        'background': True,
        'startup_delay': 10
    },
    'monitoring_dashboard': {
        'description': 'Pipeline Monitoring Dashboard',
        # Use the containerized monitoring-dashboard service (Flask inside Docker)
        'command': ['docker-compose', 'up', '-d', 'monitoring-dashboard'],
        'log_file': 'monitoring_dashboard.log',
        'critical': False,
        'background': False,   # up -d returns quickly
        'startup_delay': 0
    },
    'spark_analytics': {
        'description': 'Spark Analytics (Batch + Stream + Model Evaluation)',
        'command': [
            'docker', 'exec', '-u', 'root', 'spark-master',
            'bash', '-c',
            'mkdir -p /home/spark/.ivy2/cache && '
            'chown -R spark:spark /home/spark/.ivy2 && '
            'chmod -R 755 /home/spark/.ivy2 && '
            'su spark -c "'  # enter spark user
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
    'xgboost_forecasting': {
        'description': 'XGBoost Forecasting Service (TimescaleDB)',
        # Run the Dockerized forecasting service, not host Python
        'command': ['docker-compose', 'up', '-d', 'xgboost-forecasting'],
        'log_file': 'xgboost_forecasting.log',
        'critical': False,   # nice-to-have; can flip to True later if you want
        'background': False,  # up -d returns immediately
        'startup_delay': 0
    },
    'device_viewer': {
        'description': 'Device Viewer Website (Flask Web Interface)',
        # Use the containerized device-viewer service
        'command': ['docker-compose', 'up', '-d', 'device-viewer'],
        'log_file': 'device_viewer.log',
        'critical': False,  # Not critical for core pipeline
        'background': False,   # up -d returns immediately
        'startup_delay': 0
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
        required_services = [
            'kafka-broker-1',
            'kafka-broker-2',
            'kafka-broker-3',
            'kafka-broker-4',
            'timescaledb',
            'flink-jobmanager',
            'spark-master'
        ]

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
                # Foreground services: wait for completion (docker-compose up -d, init scripts, etc.)
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
            'database_init',          # Stage 0: Initialize database schema (Docker)
            'kafka_topics',           # Stage 1: Create Kafka topics (HOST)
            'flink_training',         # Stage 2: Real-time ML training (Docker: Flink)
            'federated_aggregation',  # Stage 3: Model aggregation (Docker)
            'spark_analytics',        # Stage 4: Batch analytics (Docker: Spark)
            'xgboost_forecasting',    # Stage 5: Forecasting (Docker via xgboost-forecasting)
            'monitoring_dashboard',   # Stage 6: Live monitoring dashboard (Docker)
            'device_viewer',          # Stage 7: Web interface (Docker)
            'grafana_setup'           # Stage 8: Configure Grafana dashboards (HOST)
        ]

        success_count = 0

        for service_name in startup_order:
            if service_name not in SERVICES:
                continue

            config = SERVICES[service_name]

            # Start all services, even if one fails, so we see all errors
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

        active_services = []
        for service_name, process in self.running_services.items():
            if process.poll() is None:  # Still running
                config = SERVICES.get(service_name, {})
                active_services.append(service_name)
                logger.info(f"{config.get('description', service_name)} (PID: {process.pid})")

        if not active_services:
            logger.warning("No services currently running")

        logger.info("\n" + "=" * 70)
        logger.info("ACCESS POINTS")
        logger.info("=" * 70)
        logger.info("Grafana Dashboard:        http://localhost:3001 (admin/admin)")
        logger.info("Kafka UI:                 http://localhost:8081")
        logger.info("Device Viewer Website:    http://localhost:8082")
        logger.info("Flink Dashboard:          http://localhost:8161")
        logger.info("Spark Master:             http://localhost:8086")
        logger.info("TimescaleDB:              localhost:5432")

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
        logger.info("XGBoost Forecasts → Forecast table")
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

    time.sleep(2)

    urls = [
        ('Device Viewer Website', 'http://localhost:8082'),
        ('Kafka UI', 'http://localhost:8081'),
        ('Grafana Dashboard', 'http://localhost:3001'),
        ('Flink Dashboard', 'http://localhost:8161'),
        ('Spark Master UI', 'http://localhost:8086'),
        ('Spark Worker UI', 'http://localhost:8087'),
        ('Live Monitoring', 'http://localhost:5001'),
    ]

    for name, url in urls:
        try:
            logger.info(f"Opening {name}: {url}")
            webbrowser.open(url, new=2)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not open {name}: {e}")

    logger.info("=" * 70)

def main():
    """Main orchestrator"""
    orchestrator = PipelineOrchestrator()

    try:
        if orchestrator.start_all_services():
            orchestrator.show_pipeline_status()
            logger.info("\nPipeline started successfully!")
            launch_web_interfaces()
            logger.info("\nPress Ctrl+C to stop\n")
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

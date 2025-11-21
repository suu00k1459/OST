#!/usr/bin/env python3
"""
FLEAD Pipeline Live Monitor
Real-time visualization of the entire federated learning pipeline
Shows data flow: Kafka → Flink → Federated Aggregation → TimescaleDB → Grafana
"""

from flask import Flask, render_template, jsonify
import psycopg2
import subprocess
import time
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'timescaledb',
    'port': 5432,
    'database': 'flead',
    'user': 'flead',
    'password': 'password'  # Fixed: matches docker-compose.yml
}

def get_db_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except:
        return None

def check_docker_service(service_name):
    """Check if Docker service is running"""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={service_name}', '--format', '{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        status = result.stdout.strip()
        if 'Up' in status:
            if 'healthy' in status:
                return 'healthy'
            return 'running'
        return 'stopped'
    except:
        return 'unknown'

def get_kafka_message_count(topic):
    """Get Kafka topic message count"""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'kafka', 'kafka-run-class', 
             'kafka.tools.GetOffsetShell', '--broker-list', 'kafka:29092', 
             '--topic', topic, '--time', '-1'],
            capture_output=True,
            text=True,
            timeout=10
        )
        total = 0
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                total += int(line.split(':')[-1])
        return total
    except:
        return 0

def get_flink_jobs():
    """Get Flink job status"""
    try:
        result = subprocess.run(
            ['docker', 'exec', 'flink-jobmanager', 'flink', 'list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        jobs = []
        for line in result.stdout.split('\n'):
            if 'RUNNING' in line or 'FINISHED' in line:
                jobs.append({
                    'status': 'RUNNING' if 'RUNNING' in line else 'FINISHED',
                    'name': line.split(':')[-1].strip() if ':' in line else 'Unknown'
                })
        return jobs
    except:
        return []

def get_database_stats():
    """Get database statistics"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            # Get table counts
            cur.execute("""
                SELECT 
                    'local_models' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute') as last_minute,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes') as last_5min,
                    MAX(created_at) as latest_record
                FROM local_models
                UNION ALL
                SELECT 
                    'federated_models',
                    COUNT(*),
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute'),
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes'),
                    MAX(created_at)
                FROM federated_models
                UNION ALL
                SELECT 
                    'dashboard_metrics',
                    COUNT(*),
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute'),
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes'),
                    MAX(created_at)
                FROM dashboard_metrics;
            """)
            
            results = cur.fetchall()
            stats = {}
            for row in results:
                stats[row[0]] = {
                    'total': row[1],
                    'last_minute': row[2],
                    'last_5min': row[3],
                    'latest': row[4].isoformat() if row[4] else None
                }
            
            return stats
    except Exception as e:
        print(f"Database error: {e}")
        return None
    finally:
        conn.close()

def get_recent_models():
    """Get recent model training activity"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    device_id,
                    model_version,
                    global_version,
                    accuracy,
                    samples_processed,
                    created_at
                FROM local_models
                ORDER BY created_at DESC
                LIMIT 10;
            """)
            
            models = []
            for row in cur.fetchall():
                models.append({
                    'device_id': row[0],
                    'model_version': row[1],
                    'global_version': row[2],
                    'accuracy': float(row[3]),
                    'samples': row[4],
                    'timestamp': row[5].isoformat()
                })
            return models
    except:
        return []
    finally:
        conn.close()

def get_python_processes():
    """Get running Python pipeline processes"""
    try:
        result = subprocess.run(
            ['powershell', '-Command', 
             "Get-Process python | Select-Object Id, @{Name='CommandLine';Expression={(Get-WmiObject Win32_Process -Filter \"ProcessId=$($_.Id)\").CommandLine}} | Where-Object { $_.CommandLine -like '*scripts*' } | ConvertTo-Json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.stdout.strip():
            processes_raw = json.loads(result.stdout)
            # Handle single process (returns object) vs multiple (returns array)
            if isinstance(processes_raw, dict):
                processes_raw = [processes_raw]
            
            processes = []
            for proc in processes_raw:
                cmd = proc.get('CommandLine', '')
                if 'kafka_producer' in cmd:
                    processes.append({'name': 'Kafka Producer', 'pid': proc['Id'], 'status': 'running'})
                elif 'federated_aggregation' in cmd:
                    processes.append({'name': 'Federated Aggregation', 'pid': proc['Id'], 'status': 'running'})
                elif 'spark_analytics' in cmd:
                    processes.append({'name': 'Spark Analytics', 'pid': proc['Id'], 'status': 'running'})
            return processes
        return []
    except Exception as e:
        print(f"Process check error: {e}")
        return []

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('pipeline_monitor.html')

@app.route('/api/status')
def get_status():
    """Get complete pipeline status"""
    
    # Check all Docker services
    docker_services = {
        'kafka': check_docker_service('kafka'),
        'timescaledb': check_docker_service('timescaledb'),
        'flink-jobmanager': check_docker_service('flink-jobmanager'),
        'flink-taskmanager': check_docker_service('flink-taskmanager'),
        'spark-master': check_docker_service('spark-master'),
        'spark-worker': check_docker_service('spark-worker'),
        'grafana': check_docker_service('grafana'),
    }
    
    # Get Kafka stats
    kafka_stats = {
        'edge-iiot-stream': get_kafka_message_count('edge-iiot-stream'),
        'local-model-updates': get_kafka_message_count('local-model-updates'),
        'global-model-updates': get_kafka_message_count('global-model-updates'),
    }
    
    # Get Flink jobs
    flink_jobs = get_flink_jobs()
    
    # Get database stats
    db_stats = get_database_stats()
    
    # Get recent models
    recent_models = get_recent_models()
    
    # Get Python processes
    python_processes = get_python_processes()
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'docker_services': docker_services,
        'kafka': kafka_stats,
        'flink': flink_jobs,
        'database': db_stats,
        'recent_models': recent_models,
        'python_processes': python_processes,
        'pipeline_health': 'healthy' if all(s in ['healthy', 'running'] for s in docker_services.values()) else 'degraded'
    })

@app.route('/api/health')
def health_check():
    """Quick health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    print("=" * 70)
    print(" FLEAD Pipeline Monitor Starting...")
    print("=" * 70)
    print("[DASHBOARD] http://localhost:5001")
    print("[UPDATE] Real-time updates every 2 seconds")
    print("[MONITORING] Kafka -> Flink -> Database -> Grafana")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5001, debug=False)

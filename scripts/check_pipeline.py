#!/usr/bin/env python3
"""
Quick Pipeline Status Checker
Run this to see if everything is working!
"""

import subprocess
import psycopg2
import sys
from datetime import datetime

# Colors for terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'flead',
    'user': 'flead',
    'password': 'password'  # Fixed: matches docker-compose.yml
}

def print_header(text):
    print(f"\n{CYAN}{BOLD}{'='*70}")
    print(f"{text:^70}")
    print(f"{'='*70}{RESET}\n")

def print_status(service, status):
    if status in ['healthy', 'running', True]:
        icon = f"{GREEN}✓{RESET}"
        status_text = f"{GREEN}RUNNING{RESET}"
    else:
        icon = f"{RED}✗{RESET}"
        status_text = f"{RED}STOPPED{RESET}"
    print(f"  {icon} {service:30} {status_text}")

def check_docker():
    """Check Docker services"""
    print_header("DOCKER SERVICES")
    
    services = [
        'kafka', 'timescaledb', 'flink-jobmanager', 
        'flink-taskmanager', 'spark-master', 'grafana'
    ]
    
    healthy_count = 0
    for service in services:
        try:
            result = subprocess.run(
                ['docker', 'ps', '--filter', f'name={service}', '--format', '{{.Status}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = result.stdout.strip()
            is_running = 'Up' in status
            if is_running:
                healthy_count += 1
            print_status(service, is_running)
        except:
            print_status(service, False)
    
    print(f"\n  {YELLOW}Status: {healthy_count}/{len(services)} services running{RESET}")
    return healthy_count == len(services)

def check_kafka():
    """Check Kafka messages"""
    print_header("KAFKA DATA FLOW")
    
    topics = [
        ('edge-iiot-stream', 'IoT Sensor Data'),
        ('local-model-updates', 'Local Model Updates'),
        ('global-model-updates', 'Global Model Updates')
    ]
    
    total_messages = 0
    for topic, description in topics:
        try:
            result = subprocess.run(
                ['docker', 'exec', 'kafka', 'kafka-run-class', 
                 'kafka.tools.GetOffsetShell', '--broker-list', 'kafka:29092', 
                 '--topic', topic, '--time', '-1'],
                capture_output=True,
                text=True,
                timeout=10
            )
            count = 0
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    count += int(line.split(':')[-1])
            total_messages += count
            print(f"  {GREEN}✓{RESET} {description:30} {BOLD}{count:,}{RESET} messages")
        except:
            print(f"  {RED}✗{RESET} {description:30} {RED}ERROR{RESET}")
    
    print(f"\n  {YELLOW}Total: {total_messages:,} messages flowing through Kafka{RESET}")
    return total_messages > 0

def check_flink():
    """Check Flink jobs"""
    print_header("FLINK PROCESSING")
    
    try:
        result = subprocess.run(
            ['docker', 'exec', 'flink-jobmanager', 'flink', 'list'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        running_jobs = []
        for line in result.stdout.split('\n'):
            if 'RUNNING' in line:
                job_name = line.split(':')[-1].strip() if ':' in line else 'Unknown Job'
                running_jobs.append(job_name)
                print(f"  {GREEN}✓{RESET} {job_name}")
        
        if running_jobs:
            print(f"\n  {YELLOW}Status: {len(running_jobs)} Flink job(s) processing data{RESET}")
            return True
        else:
            print(f"  {RED}✗ No Flink jobs running{RESET}")
            return False
    except:
        print(f"  {RED}✗ Could not check Flink status{RESET}")
        return False

def check_database():
    """Check database activity"""
    print_header("DATABASE ACTIVITY")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Get recent activity
            cur.execute("""
                SELECT 
                    'Local Models' as type,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute') as last_minute
                FROM local_models
                UNION ALL
                SELECT 
                    'Federated Models',
                    COUNT(*),
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute')
                FROM federated_models;
            """)
            
            results = cur.fetchall()
            has_activity = False
            
            for row in results:
                type_name, total, last_minute = row
                print(f"  {GREEN}✓{RESET} {type_name:30} Total: {BOLD}{total:,}{RESET}, Last min: {BOLD}{last_minute}{RESET}")
                if last_minute > 0:
                    has_activity = True
            
            if has_activity:
                print(f"\n  {YELLOW}Status: Database receiving LIVE data ⚡{RESET}")
            else:
                print(f"\n  {YELLOW}Status: Database connected, waiting for data{RESET}")
            
            conn.close()
            return True
    except Exception as e:
        print(f"  {RED}✗ Database connection failed: {e}{RESET}")
        return False

def check_python_services():
    """Check Python processes"""
    print_header("PYTHON SERVICES")
    
    try:
        # Get all Python processes with their command lines
        result = subprocess.run(
            ['powershell', '-Command', 
             "Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, @{Name='CommandLine';Expression={(Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.Id)\" -ErrorAction SilentlyContinue).CommandLine}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Count processes
        services = [
            ('Kafka Producer', '02_kafka_producer'),
            ('Federated Aggregation', '04_federated_aggregation'),
            ('Spark Analytics', '05_spark_analytics'),
            ('Pipeline Monitor', 'pipeline_monitor'),
        ]
        
        running = []
        for service_name, script_name in services:
            # Check if script name appears in any command line
            count = result.stdout.lower().count(script_name.lower())
            if count > 0:
                running.append(service_name)
                print_status(service_name, True)
            else:
                print_status(service_name, False)
        
        if running:
            print(f"\n  {YELLOW}Status: {len(running)} Python service(s) active{RESET}")
        return len(running) > 0
    except Exception as e:
        print(f"  {RED}✗ Could not check Python processes: {e}{RESET}")
        return False

def main():
    """Run all checks"""
    print(f"\n{BOLD}{CYAN}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║          FLEAD PIPELINE STATUS - Quick Health Check               ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{RESET}")
    
    checks = {
        'Docker Services': check_docker(),
        'Kafka Data Flow': check_kafka(),
        'Flink Processing': check_flink(),
        'Database Activity': check_database(),
        'Python Services': check_python_services(),
    }
    
    # Summary
    print_header("OVERALL STATUS")
    
    all_good = all(checks.values())
    passed = sum(checks.values())
    total = len(checks)
    
    for component, status in checks.items():
        print_status(component, status)
    
    print(f"\n{BOLD}")
    if all_good:
        print(f"  {GREEN} ALL SYSTEMS OPERATIONAL! Pipeline is working perfectly!{RESET}")
    elif passed >= 3:
        print(f"  {YELLOW}⚠️  PARTIAL: {passed}/{total} components working. Some services may need attention.{RESET}")
    else:
        print(f"  {RED} ISSUES DETECTED: Only {passed}/{total} components working.{RESET}")
    
    print(f"\n{CYAN}{BOLD}{'='*70}")
    print(f"  Access Points:")
    print(f"    • Live Dashboard: http://localhost:5001")
    print(f"    • Grafana: http://localhost:3001 (admin/admin)")
    print(f"    • Kafka UI: http://localhost:8080")
    print(f"{'='*70}{RESET}\n")
    
    return 0 if all_good else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Check interrupted by user{RESET}\n")
        sys.exit(130)

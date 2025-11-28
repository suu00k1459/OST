#!/usr/bin/env python3
"""
Quick Pipeline Status Checker
Run this on the HOST to see if everything in the FLEAD stack is working.
"""

import subprocess
import psycopg2
import sys

# Colors for terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

# DB config: connect to TimescaleDB via host port 5432 (mapped in docker-compose)
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'flead',
    'user': 'flead',
    'password': 'password',  # matches docker-compose.yml
}


def print_header(text: str) -> None:
    print(f"\n{CYAN}{BOLD}{'=' * 70}")
    print(f"{text:^70}")
    print(f"{'=' * 70}{RESET}\n")


def print_status(service: str, status: bool) -> None:
    if status:
        icon = f"{GREEN}✓{RESET}"
        status_text = f"{GREEN}RUNNING{RESET}"
    else:
        icon = f"{RED}✗{RESET}"
        status_text = f"{RED}STOPPED{RESET}"
    print(f"  {icon} {service:30} {status_text}")


def _is_container_running(name_substring: str) -> bool:
    """
    Return True if any container whose NAME contains `name_substring`
    is currently "Up".
    """
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={name_substring}', '--format', '{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = result.stdout.strip()
        return 'Up' in status
    except Exception:
        return False


def check_docker() -> bool:
    """Check core Docker services (infra layer)."""
    print_header("DOCKER SERVICES (INFRASTRUCTURE)")

    # Core infra from your docker-compose.yml
    services = [
        'kafka-broker-1',
        'timescaledb',
        'flink-jobmanager',
        'flink-taskmanager',
        'spark-master',
        'spark-worker-1',
        'grafana',
        'kafka-ui',
    ]

    healthy_count = 0
    for svc in services:
        running = _is_container_running(svc)
        if running:
            healthy_count += 1
        print_status(svc, running)

    print(f"\n  {YELLOW}Status: {healthy_count}/{len(services)} core services running{RESET}")
    return healthy_count == len(services)


def check_kafka() -> bool:
    """Check Kafka topics have messages (single-broker cluster)."""
    print_header("KAFKA DATA FLOW")

    topics = [
        ('edge-iiot-stream', 'IoT Sensor Data'),
        ('local-model-updates', 'Local Model Updates'),
        ('global-model-updates', 'Global Model Updates'),
    ]

    total_messages = 0

    for topic, description in topics:
        try:
            # Run GetOffsetShell inside kafka-broker-1 container,
            # pointing to all 4 brokers on PLAINTEXT ports (9092).
            result = subprocess.run(
                [
                    'docker', 'exec', 'kafka-broker-1',
                    'kafka-run-class', 'kafka.tools.GetOffsetShell',
                    '--broker-list',
                    'kafka-broker-1:9092',
                    '--topic', topic,
                    '--time', '-1',
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                # Topic may not exist yet or cluster still starting
                print(f"  {RED}✗{RESET} {description:30} {RED}NO DATA / TOPIC ERROR{RESET}")
                continue

            count = 0
            for line in result.stdout.strip().split('\n'):
                # Expected format: edge-iiot-stream:0:12345
                if ':' in line:
                    try:
                        offset = int(line.strip().split(':')[-1])
                        count += offset
                    except ValueError:
                        continue

            total_messages += count
            print(f"  {GREEN}✓{RESET} {description:30} {BOLD}{count:,}{RESET} messages")

        except Exception as e:
            print(f"  {RED}✗{RESET} {description:30} {RED}ERROR ({e}){RESET}")

    print(f"\n  {YELLOW}Total: {total_messages:,} messages observed across Kafka topics{RESET}")
    # We consider Kafka "OK" if there are *some* messages on the main stream
    return total_messages > 0


def check_flink() -> bool:
    """Check Flink jobs running inside flink-jobmanager container."""
    print_header("FLINK PROCESSING")

    try:
        result = subprocess.run(
            ['docker', 'exec', 'flink-jobmanager', 'flink', 'list'],
            capture_output=True,
            text=True,
            timeout=10,
        )

        running_jobs = []
        for line in result.stdout.split('\n'):
            if 'RUNNING' in line:
                # Example line: "JobId : <id> : <name> : RUNNING"
                parts = line.split(':')
                job_name = parts[-2].strip() if len(parts) >= 2 else line.strip()
                running_jobs.append(job_name)
                print(f"  {GREEN}✓{RESET} {job_name}")

        if running_jobs:
            print(f"\n  {YELLOW}Status: {len(running_jobs)} Flink job(s) processing data{RESET}")
            return True
        else:
            print(f"  {RED}✗ No Flink jobs running{RESET}")
            return False

    except Exception as e:
        print(f"  {RED}✗ Could not check Flink status: {e}{RESET}")
        return False


def check_database() -> bool:
    """Check database activity in local_models and federated_models."""
    print_header("DATABASE ACTIVITY (TimescaleDB)")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    'Local Models' AS type,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute') AS last_minute
                FROM local_models
                UNION ALL
                SELECT 
                    'Federated Models',
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 minute') AS last_minute
                FROM federated_models;
                """
            )

            results = cur.fetchall()
            has_activity = False

            for type_name, total, last_minute in results:
                print(
                    f"  {GREEN}✓{RESET} {type_name:30} "
                    f"Total: {BOLD}{total:,}{RESET}, "
                    f"Last min: {BOLD}{last_minute}{RESET}"
                )
                if last_minute and last_minute > 0:
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


def check_python_services() -> bool:
    """
    In the new architecture, the "Python services" are Dockerized.

    Here we check that the key application containers are Up:
      - kafka-producer
      - federated-aggregator
      - monitoring-dashboard
      - device-viewer
      - timescaledb-collector
    """
    print_header("PIPELINE APPS (DOCKERIZED PYTHON SERVICES)")

    app_containers = [
        ('Kafka Producer', 'kafka-producer'),
        ('Federated Aggregator', 'federated-aggregator'),
        ('Monitoring Dashboard', 'monitoring-dashboard'),
        ('Device Viewer', 'device-viewer'),
        ('TimescaleDB Collector', 'timescaledb-collector'),
    ]

    running_count = 0
    for label, name in app_containers:
        running = _is_container_running(name)
        if running:
            running_count += 1
        print_status(label, running)

    if running_count:
        print(f"\n  {YELLOW}Status: {running_count}/{len(app_containers)} app container(s) running{RESET}")
    else:
        print(f"\n  {YELLOW}Status: No app containers detected running{RESET}")

    return running_count > 0


def main() -> int:
    """Run all checks."""
    print(f"\n{BOLD}{CYAN}")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║          FLEAD PIPELINE STATUS - Quick Health Check                ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f"{RESET}")

    checks = {
        'Docker Services': check_docker(),
        'Kafka Data Flow': check_kafka(),
        'Flink Processing': check_flink(),
        'Database Activity': check_database(),
        'Pipeline Apps': check_python_services(),
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
        print(f"  {GREEN}ALL SYSTEMS OPERATIONAL! Pipeline is working perfectly!{RESET}")
    elif passed >= 3:
        print(
            f"  {YELLOW}⚠️  PARTIAL: {passed}/{total} components working. "
            f"Some services may need attention.{RESET}"
        )
    else:
        print(
            f"  {RED}❌ ISSUES DETECTED: Only {passed}/{total} components working.{RESET}"
        )

    print(f"\n{CYAN}{BOLD}{'=' * 70}")
    print("  Access Points:")
    print("    • Monitoring Dashboard: http://localhost:5001")
    print("    • Device Viewer:       http://localhost:8082")
    print("    • Grafana:             http://localhost:3001 (admin / admin)")
    print("    • Kafka UI:            http://localhost:8081")
    print(f"{'=' * 70}{RESET}\n")

    return 0 if all_good else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Check interrupted by user{RESET}\n")
        sys.exit(130)
"""
FLEAD Platform Verification Script
Quick health check for all components
"""

import subprocess
import time
import sys
from pathlib import Path

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"Checking: {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  ✅ {description}: OK")
            return True
        else:
            print(f"  ❌ {description}: FAILED")
            if result.stderr:
                print(f"     Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ {description}: ERROR - {str(e)}")
        return False

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if Path(filepath).exists():
        print(f"  ✅ {description}: EXISTS")
        return True
    else:
        print(f"  ❌ {description}: NOT FOUND")
        return False

def main():
    print_header("FLEAD PLATFORM VERIFICATION")
    
    results = {
        'docker': False,
        'services': False,
        'flink': False,
        'kafka': False,
        'database': False,
        'files': False
    }
    
    # 1. Check Docker
    print_header("1. Docker Environment")
    results['docker'] = run_command(
        "docker --version",
        "Docker installed"
    )
    
    if results['docker']:
        results['services'] = run_command(
            'docker ps --format "{{.Names}}" | findstr /C:"kafka" /C:"flink" /C:"spark" /C:"timescaledb" /C:"grafana"',
            "Docker containers running"
        )
    
    # 2. Check Flink
    print_header("2. Flink Status")
    results['flink'] = run_command(
        "docker exec flink-jobmanager flink list",
        "Flink jobs"
    )
    
    # 3. Check Kafka Topics
    print_header("3. Kafka Topics")
    results['kafka'] = run_command(
        "docker exec kafka kafka-topics --list --bootstrap-server localhost:9092",
        "Kafka topics"
    )
    
    # 4. Check Database
    print_header("4. TimescaleDB")
    results['database'] = run_command(
        'docker exec timescaledb psql -U flead -d flead -c "\\dt"',
        "Database tables"
    )
    
    # 5. Check Required Files
    print_header("5. File Structure")
    print("Checking critical files...")
    
    critical_files = [
        ("scripts/02_kafka_producer.py", "Kafka Producer"),
        ("scripts/03_flink_local_training.py", "Flink Training"),
        ("scripts/04_federated_aggregation.py", "Federated Aggregation"),
        ("scripts/05_spark_analytics.py", "Spark Analytics"),
        ("scripts/pipeline_orchestrator.py", "Pipeline Orchestrator"),
        ("sql/init.sql", "Database Schema"),
        ("docker-compose.yml", "Docker Compose"),
    ]
    
    all_files_exist = True
    for filepath, description in critical_files:
        if not check_file_exists(filepath, description):
            all_files_exist = False
    
    results['files'] = all_files_exist
    
    # Check that deleted file is gone
    print("\nVerifying deleted files...")
    if not Path("scripts/06_python_analytics.py").exists():
        print("  ✅ 06_python_analytics.py: DELETED (correct)")
    else:
        print("  ❌ 06_python_analytics.py: STILL EXISTS (should be deleted)")
        results['files'] = False
    
    # 6. Check Configuration
    print_header("6. Configuration Verification")
    
    # Check Kafka producer has random import
    try:
        with open("scripts/02_kafka_producer.py", 'r') as f:
            content = f.read()
            if "import random" in content and "random.choice" in content:
                print("  ✅ Kafka Producer: Random device selection configured")
            else:
                print("  ❌ Kafka Producer: Random device selection NOT configured")
    except:
        print("  ❌ Kafka Producer: Cannot read file")
    
    # Check Flink has training intervals
    try:
        with open("scripts/03_flink_local_training.py", 'r') as f:
            content = f.read()
            if "MODEL_TRAINING_INTERVAL_ROWS = 50" in content and "MODEL_TRAINING_INTERVAL_SECONDS = 60" in content:
                print("  ✅ Flink Training: 50 rows / 60 seconds trigger configured")
            else:
                print("  ❌ Flink Training: Training intervals NOT configured")
    except:
        print("  ❌ Flink Training: Cannot read file")
    
    # Check Federated aggregation threshold
    try:
        with open("scripts/04_federated_aggregation.py", 'r') as f:
            content = f.read()
            if "AGGREGATION_WINDOW = 20" in content:
                print("  ✅ Federated Aggregation: 20 device threshold configured")
            else:
                print("  ❌ Federated Aggregation: Threshold NOT configured correctly")
    except:
        print("  ❌ Federated Aggregation: Cannot read file")
    
    # 7. Summary
    print_header("VERIFICATION SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"Tests Passed: {passed}/{total}")
    print("")
    
    for category, status in results.items():
        status_icon = "✅" if status else "❌"
        print(f"  {status_icon} {category.upper()}: {'PASS' if status else 'FAIL'}")
    
    print("")
    
    if passed == total:
        print("🎉 ALL CHECKS PASSED! Platform is ready.")
        print("\nNext steps:")
        print("  1. Run: START.bat")
        print("  2. Access Grafana: http://localhost:3001")
        print("  3. Monitor logs: dir logs\\")
        return 0
    else:
        print("⚠️  SOME CHECKS FAILED. Please review errors above.")
        print("\nTroubleshooting:")
        print("  - Check Docker Desktop is running")
        print("  - Run: docker-compose up -d")
        print("  - Check logs for errors")
        return 1

if __name__ == "__main__":
    sys.exit(main())

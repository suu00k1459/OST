#!/usr/bin/env python
"""
FLEAD Platform - Dependency Installation Script
Ensures all Python packages are properly installed
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*70}")
    print(f">>> {description}")
    print(f"{'='*70}")
    try:
        result = subprocess.run(cmd, shell=True, check=False)
        if result.returncode != 0:
            print(f"WARNING: Command returned non-zero exit code: {result.returncode}")
            return False
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def verify_package(package_name, import_name=None):
    """Verify a package is installed"""
    if import_name is None:
        import_name = package_name.replace('-', '_')
    
    try:
        __import__(import_name)
        print(f"✓ {package_name} is installed")
        return True
    except ImportError:
        print(f"✗ {package_name} is NOT installed")
        return False

def main():
    print("\n" + "="*70)
    print("FLEAD PLATFORM - DEPENDENCY INSTALLER")
    print("="*70)
    
    # Upgrade pip
    print("\n[1/4] Upgrading pip...")
    run_command(f"{sys.executable} -m pip install --upgrade pip", "Upgrading pip")
    
    # Install requirements
    print("\n[2/4] Installing requirements.txt...")
    if not run_command(f"{sys.executable} -m pip install -r requirements.txt --no-cache-dir", 
                      "Installing from requirements.txt"):
        print("Retrying without cache...")
        run_command(f"{sys.executable} -m pip install -r requirements.txt", 
                   "Installing from requirements.txt (retry)")
    
    # Verify critical packages
    print("\n[3/4] Verifying critical packages...")
    critical_packages = [
        ('flask', 'flask'),
        ('flask-socketio', 'flask_socketio'),
        ('flask-cors', 'flask_cors'),
        ('python-socketio', 'socketio'),
        ('python-engineio', 'engineio'),
        ('kafka-python', 'kafka'),
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
    ]
    
    missing = []
    for package, import_name in critical_packages:
        if not verify_package(package, import_name):
            missing.append(package)
    
    # Install missing packages
    if missing:
        print(f"\n[4/4] Installing missing packages: {', '.join(missing)}")
        for package in missing:
            run_command(f"{sys.executable} -m pip install {package} --no-cache-dir",
                       f"Installing {package}")
            # Retry once if it fails
            if not verify_package(package):
                print(f"  Retrying {package}...")
                run_command(f"{sys.executable} -m pip install {package} --force-reinstall",
                           f"Force reinstalling {package}")
    else:
        print("\n[4/4] All critical packages verified!")
    
    # Final verification
    print("\n" + "="*70)
    print("FINAL VERIFICATION")
    print("="*70)
    
    all_good = True
    for package, import_name in critical_packages:
        if not verify_package(package, import_name):
            all_good = False
    
    print("\n" + "="*70)
    if all_good:
        print("✓ ALL DEPENDENCIES INSTALLED SUCCESSFULLY!")
        print("="*70)
        return 0
    else:
        print("✗ SOME DEPENDENCIES ARE STILL MISSING!")
        print("="*70)
        return 1

if __name__ == '__main__':
    sys.exit(main())

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
    print(f"\n{'=' * 70}")
    print(f">>> {description}")
    print(f"{'=' * 70}")
    print(f"Command: {cmd}")
    try:
        # shell=True so we can pass a single string with quotes; safe here because cmd is built by us
        result = subprocess.run(cmd, shell=True, check=False)
        if result.returncode != 0:
            print(f"WARNING: Command returned non-zero exit code: {result.returncode}")
            return False
        return True
    except Exception as e:
        print(f"ERROR while running command: {e}")
        return False


def verify_package(package_name, import_name=None):
    """Verify a package is installed by trying to import it"""
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
    print("\n" + "=" * 70)
    print("FLEAD PLATFORM - DEPENDENCY INSTALLER")
    print("=" * 70)

    # Show which Python we're using
    print(f"\nUsing Python executable: {sys.executable}")

    # Resolve requirements.txt relative to this script (works even if run from a different folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    req_path = os.path.join(script_dir, "requirements.txt")

    if not os.path.exists(req_path):
        print(f"\nERROR: requirements.txt not found at:\n  {req_path}")
        print("Make sure this script lives in the same folder as requirements.txt.")
        return 1

    # Quote paths in case they contain spaces (like 'O O')
    python_exe = f'"{sys.executable}"'
    req_path_quoted = f'"{req_path}"'

    # 1) Upgrade pip
    print("\n[1/4] Upgrading pip...")
    run_command(
        f"{python_exe} -m pip install --upgrade pip",
        "Upgrading pip"
    )

    # 2) Install from requirements.txt
    print("\n[2/4] Installing requirements.txt...")
    ok = run_command(
        f"{python_exe} -m pip install -r {req_path_quoted} --no-cache-dir",
        "Installing from requirements.txt"
    )
    if not ok:
        print("Retrying without --no-cache-dir...")
        run_command(
            f"{python_exe} -m pip install -r {req_path_quoted}",
            "Installing from requirements.txt (retry)"
        )

    # 3) Verify critical packages
    print("\n[3/4] Verifying critical packages...")
    critical_packages = [
        ("flask", "flask"),
        ("flask-socketio", "flask_socketio"),
        ("flask-cors", "flask_cors"),
        ("python-socketio", "socketio"),
        ("python-engineio", "engineio"),
        ("kafka-python", "kafka"),
        ("pandas", "pandas"),
        ("numpy", "numpy"),
    ]

    missing = []
    for package, import_name in critical_packages:
        if not verify_package(package, import_name):
            missing.append(package)

    # 4) Install any missing critical packages
    if missing:
        print(f"\n[4/4] Installing missing packages: {', '.join(missing)}")
        for package in missing:
            run_command(
                f"{python_exe} -m pip install {package} --no-cache-dir",
                f"Installing {package}"
            )
            if not verify_package(package):
                print(f"  Retrying {package} with force reinstall...")
                run_command(
                    f"{python_exe} -m pip install {package} --force-reinstall",
                    f"Force reinstalling {package}"
                )
    else:
        print("\n[4/4] All critical packages already installed 🎉")

    # Final verification
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)

    all_good = True
    for package, import_name in critical_packages:
        if not verify_package(package, import_name):
            all_good = False

    print("\n" + "=" * 70)
    if all_good:
        print("✓ ALL DEPENDENCIES INSTALLED SUCCESSFULLY!")
        print("=" * 70)
        return 0
    else:
        print("✗ SOME DEPENDENCIES ARE STILL MISSING!")
        print("  → Check errors above and try re-running this script.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())

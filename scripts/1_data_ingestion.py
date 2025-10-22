import subprocess

print("[INFO] Starting Kafka producer container...")
base_dir = os.path.dirname(os.path.dirname(__file__))  # scripts 상위 = OST
compose_dir = os.path.join(base_dir, "Implementation")

print(f"[INFO] Running Docker Compose in {compose_dir}")

subprocess.run(
    ["docker-compose", "up", "-d", "producer"],
    check=True,
    cwd=compose_dir  # 여기서 실행하게 함
)

print("[INFO] Producer container started successfully!")

logs = subprocess.run(["docker", "logs", "--tail", "10", "implementation-producer-1"], capture_output=True, text=True)
print("\n[PRODUCER LOGS]")
print(logs.stdout)

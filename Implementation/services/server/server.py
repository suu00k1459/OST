import os
import json
import psycopg
import flwr as fl
from kafka import KafkaConsumer, KafkaProducer
from datetime import datetime
import time # <-- Import the time library for the delay

# --- 1. Load Configuration from Environment Variables ---
# Get Kafka's address from docker-compose.
BOOT = os.environ["KAFKA_BOOTSTRAP"]
# The topic where clients send their model updates.
TOPIC_UPDATES = os.environ["TOPIC_UPDATES"]
# The topic where this server sends the new global model.
TOPIC_GLOBAL = os.environ["TOPIC_GLOBAL"]
# The connection string for the TimescaleDB database.
DSN = os.environ["DB_DSN"]


# --- [FIX] Add a startup delay to wait for Kafka and the Database to be ready ---
print("Server starting... waiting 20 seconds for services to initialize...")
# Give it a bit longer (20s) since it depends on two services.
time.sleep(20)
print("...Services should be ready. Initializing connections.")


# --- 2. Initialize Kafka Producer ---
# This producer will be used to send the new global model back to the clients.
producer = KafkaProducer(bootstrap_servers=BOOT, value_serializer=lambda v: json.dumps(v).encode())


# --- 3. Initialize Database Connection and Create Table ---
# Connect to the TimescaleDB to store performance metrics.
conn = psycopg.connect(DSN)
# Create a table to store metrics if it doesn't already exist.
conn.execute("""
CREATE TABLE IF NOT EXISTS federated_metrics(
ts timestamptz NOT NULL,
round int,
metric text,
value double precision
);
""")
conn.commit()


# --- 4. Define Helper Function for Logging Metrics ---
# This function will be called by the Flower strategy to save metrics to the database.
def log_metric(rnd, metric, value):
	with conn.cursor() as cur:
		cur.execute("INSERT INTO federated_metrics VALUES (%s,%s,%s,%s)", (datetime.utcnow(), rnd, metric, float(value)))
	conn.commit()


# --- 5. Define the Federated Learning Strategy ---
# This configures how the server will aggregate model updates from the clients.
# We are using a simple Federated Averaging (FedAvg) strategy provided by Flower.
strategy = fl.server.strategy.FedAvg(
	on_fit_config_fn=lambda rnd: {"round": rnd},
	evaluate_metrics_aggregation_fn=lambda ms: float(sum(v for _, v in ms)/max(len(ms),1)),
)


# --- 6. Start the Flower Server ---
# This is the main entry point that starts the federated learning process.
if __name__ == "__main__":
	print("Starting Flower server...")
	fl.server.start_server(
		server_address="0.0.0.0:8080", # Listen on all network interfaces on port 8080.
		strategy=strategy,
		config=fl.server.ServerConfig(num_rounds=5) # Run for a total of 5 rounds of training.
	)
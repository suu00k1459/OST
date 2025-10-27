import os
import json
import psycopg
import flwr as fl
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
from datetime import datetime
import time

# --- 1. Load Configuration ---
BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPIC_UPDATES = os.environ["TOPIC_UPDATES"]
TOPIC_GLOBAL = os.environ["TOPIC_GLOBAL"]
DSN = os.environ["DB_DSN"]

# --- 2. Initialize Connections with Retry ---
def initialize_connections():
    """
    Connects to Kafka and the Database with a robust retry loop.
    This makes the server resilient to startup race conditions.
    """
    kafka_producer = None
    db_conn = None
    retries = 10
    delay = 15

    for i in range(retries):
        try:
            print(f"SERVER: Attempt {i+1}/{retries}: Initializing connections...")
            
            # --- Connect to Kafka with the correct API version and timeouts ---
            kafka_producer = KafkaProducer(
                bootstrap_servers=BOOT,
                value_serializer=lambda v: json.dumps(v).encode(),
                api_version=(2, 8, 1),
                reconnect_backoff_ms=5000,
                request_timeout_ms=60000
            )
            
            # Test Kafka connection using flush()
            kafka_producer.flush(timeout=30)
            print("SERVER: Successfully connected to Kafka.")
            
            # --- Connect to Database ---
            db_conn = psycopg.connect(DSN)
            
            # Test DB connection with a simple query
            with db_conn.cursor() as cur:
                cur.execute("SELECT 1")
            print("SERVER: Successfully connected to Database.")

            return kafka_producer, db_conn

        except NoBrokersAvailable as e:
             print(f"SERVER: Kafka not ready (NoBrokersAvailable): {e}. Retrying in {delay} seconds...")
             time.sleep(delay)
        except Exception as e:
            print(f"SERVER: A service is not ready: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
            
    print("FATAL: Server could not connect to required services after multiple retries. Exiting.")
    exit(1)


# --- Main execution starts here ---
producer, conn = initialize_connections()

# --- 3. Create Database Table ---
print("SERVER: Ensuring 'federated_metrics' table exists...")
conn.execute("""
CREATE TABLE IF NOT EXISTS federated_metrics(
ts timestamptz NOT NULL,
round int,
metric text,
value double precision
);
""")
conn.commit()
print("SERVER: Database table is ready.")


# --- 4. Define Helper Function for Logging Metrics ---
def log_metric(rnd, metric, value):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO federated_metrics VALUES (%s,%s,%s,%s)", (datetime.utcnow(), rnd, metric, float(value)))
    conn.commit()


# --- 5. Ultra-Safe Strategy that Handles All Edge Cases ---
class UltraSafeFedAvg(fl.server.strategy.FedAvg):
    def aggregate_fit(self, server_round, results, failures):
        """Safe aggregation that handles zero examples."""
        if not results:
            return None, {}
            
        # Filter out results with zero examples and extract num_examples safely
        valid_results = []
        total_examples = 0
        
        for client_proxy, fit_res in results:
            try:
                # Safely get num_examples with fallback
                num_examples = getattr(fit_res, 'num_examples', 0)
                if num_examples and num_examples > 0:
                    valid_results.append((client_proxy, fit_res))
                    total_examples += num_examples
            except Exception as e:
                print(f"SERVER: Error processing fit result: {e}")
                continue
        
        if not valid_results or total_examples == 0:
            print(f"SERVER: No valid fit results in round {server_round}")
            return None, {}
            
        # Use parent class for valid results
        return super().aggregate_fit(server_round, valid_results, failures)
    
    def aggregate_evaluate(self, server_round, results, failures):
        """Safe aggregation that handles empty evaluation results."""
        if not results:
            return None, {}
            
        # Filter out results with zero examples
        valid_results = []
        for client_proxy, evaluate_res in results:
            try:
                num_examples = getattr(evaluate_res, 'num_examples', 0)
                if num_examples and num_examples > 0:
                    valid_results.append((client_proxy, evaluate_res))
            except Exception as e:
                print(f"SERVER: Error processing evaluate result: {e}")
                continue
        
        if not valid_results:
            print(f"SERVER: No valid evaluation results in round {server_round}")
            return None, {"accuracy": 0.0, "loss": 0.0}
            
        # Use parent class for valid results
        return super().aggregate_evaluate(server_round, valid_results, failures)


# --- 6. Define the Federated Learning Strategy ---
strategy = UltraSafeFedAvg(
    on_fit_config_fn=lambda rnd: {"round": rnd}
)


# --- 7. Start the Flower Server ---
if __name__ == "__main__":
    print("Starting Flower server...")
    try:
        fl.server.start_server(
            server_address="0.0.0.0:8080",
            strategy=strategy,
            config=fl.server.ServerConfig(num_rounds=5)
        )
        print("SERVER: Federated learning completed successfully!")
    except Exception as e:
        print(f"SERVER: Error during federated learning: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close connections
        if producer:
            producer.close()
        if conn:
            conn.close()
        print("SERVER: Cleanup completed.")
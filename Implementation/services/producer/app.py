import os
import json
import time
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# --- 1. Load Configuration ---
BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPICS = os.environ["TOPICS"].split(",")
CSV = os.environ["CSV_PATH"]
CHUNK = 1024

# --- 2. Initialize Kafka Producer with Retry ---
def create_producer():
    """Creates the producer, retrying until Kafka is ready."""
    retries = 10
    delay = 15
    for i in range(retries):
        try:
            print(f"PRODUCER: Attempt {i+1}/{retries}: Connecting to Kafka...")
            producer = KafkaProducer(
                bootstrap_servers=BOOT,
                value_serializer=lambda v: json.dumps(v).encode(),
                api_version=(2, 8, 1),
                reconnect_backoff_ms=5000,
                request_timeout_ms=60000
            )
            print("PRODUCER: Successfully connected to Kafka.")
            return producer
        except NoBrokersAvailable as e:
            print(f"PRODUCER: Connection failed (NoBrokersAvailable): {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            print(f"PRODUCER: An unexpected error occurred: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)

    print("FATAL: Producer could not connect to Kafka after multiple retries. Exiting.")
    exit(1)

# --- 3. Main Data Streaming Logic ---
if __name__ == "__main__":
    p = create_producer()
    total_rows_sent = 0

    print("PRODUCER: Reading CSV and starting data stream...")
    try:
        # Process row by row with round-robin topic assignment
        for chunk_idx, chunk in enumerate(pd.read_csv(CSV, chunksize=CHUNK)):
            for row_idx, (_, row) in enumerate(chunk.iterrows()):
                # Round-robin topic assignment
                topic = TOPICS[row_idx % len(TOPICS)]
                
                message_payload = {
                    "cols": list(chunk.columns),
                    "row": row.tolist(),
                    "chunk_id": chunk_idx,
                    "row_id": row_idx
                }
                
                p.send(topic, message_payload)
                total_rows_sent += 1
                
                # Progress reporting
                if total_rows_sent % 500 == 0:
                    print(f"PRODUCER: Sent {total_rows_sent} rows...")
                    p.flush()
            
            # Flush after each chunk
            p.flush()
            print(f"PRODUCER: Completed chunk {chunk_idx} - Total: {total_rows_sent} rows")

    except Exception as e:
        print(f"FATAL: An error occurred during streaming: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("PRODUCER: Finished reading CSV. Flushing all remaining messages...")
        if p:
            p.flush()
            print(f"PRODUCER: Final total rows sent: {total_rows_sent}")
        print("PRODUCER: Script finished.")
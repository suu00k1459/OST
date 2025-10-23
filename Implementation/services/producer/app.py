import os
import json
import time
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# --- 1. Load Configuration from Environment Variables ---
BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPICS = os.environ["TOPICS"].split(",")
CSV = os.environ["CSV_PATH"]
CHUNK = 512 # rows per message


# --- 2. Initialize Kafka Producer with a Retry Loop ---
p = None
retries = 5
delay = 10 # seconds

for i in range(retries):
    try:
        print(f"Attempt {i+1}/{retries}: Initializing Kafka Producer...")
        # Try to create the producer.
        p = KafkaProducer(
            bootstrap_servers=BOOT,
            value_serializer=lambda v: json.dumps(v).encode(),
            request_timeout_ms=10000,
            # [FINAL FIX] Explicitly set the API version to avoid auto-detection errors.
            api_version=(2, 0, 2) 
        )
        print("Successfully connected to Kafka!")
        break # If successful, exit the loop.
    except NoBrokersAvailable:
        print(f"Kafka not available. Retrying in {delay} seconds...")
        time.sleep(delay)
    # Catch the new error as well, though it should be fixed now.
    except Exception as e:
        print(f"An error occurred: {e}. Retrying in {delay} seconds...")
        time.sleep(delay)


# If the producer is still not connected after all retries, exit with an error.
if p is None:
    print("Could not connect to Kafka after multiple retries. Exiting.")
    exit(1)


# --- 3. Read and Send Data in Chunks ---
print("Producer started. Reading CSV and sending data to Kafka...")

try:
    # Read the large CSV in small chunks to avoid using too much memory.
    for chunk in pd.read_csv(CSV, chunksize=CHUNK):
        
        # Loop through our topics (one for each client).
        for i, topic in enumerate(TOPICS):
            
            # Split the chunk of data between the clients.
            sl = chunk.iloc[i::len(TOPICS)]
            
            # Prepare the data in a structured JSON format.
            message_payload = {"cols": list(sl.columns), "rows": sl.values.tolist()}
            
            # Send the data to the current client's topic.
            p.send(topic, message_payload)
            print(f"Sent {len(sl)} rows to topic: {topic}")

        # Ensure all messages in the chunk are sent before proceeding.
        p.flush()
        
        # Pause briefly to simulate a real-time data stream.
        time.sleep(0.2)

finally:
    # Ensure the producer is closed cleanly, even if there's an error.
    if p:
        p.close()
    print("Producer finished and closed.")
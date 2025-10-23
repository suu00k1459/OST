import os
import json
import numpy as np
import pandas as pd
from kafka import KafkaConsumer
import flwr as fl
from common.model import build_model
from services.common.preprocess import fit_transform_first_batch, transform_next_batch
import time # <-- Import the time library for the delay

# --- 1. Load Configuration from Environment Variables ---
# Unique ID for this client, e.g., "client1".
CID = os.environ.get("CLIENT_ID", "client")
# Kafka's address from docker-compose.
BOOT = os.environ["KAFKA_BOOTSTRAP"]
# The specific data topic this client should listen to.
TOPIC = os.environ["TOPIC_DATA"]
# The type of classification task (either "binary" or "multiclass").
TASK_MODE = os.environ.get("TASK_MODE", "binary")
# Optional: override the default label column name.
LABEL_COL = os.environ.get("LABEL_COL")


# --- [FIX] Add a startup delay to wait for Kafka to be ready ---
print(f"Client {CID} starting... waiting 15 seconds for Kafka to initialize...")
time.sleep(15)
print("...Kafka should be ready. Initializing consumer.")


# --- 2. Initialize Kafka Consumer ---
# This consumer will listen for incoming data from its dedicated topic.
# It automatically deserializes the JSON messages from the producer.
consumer = KafkaConsumer(TOPIC, bootstrap_servers=BOOT, value_deserializer=lambda m: json.loads(m.decode()))

# --- 3. Global State Variables ---
# These variables will hold the state of the client between federated learning rounds.
fitted = None         # Holds the fitted preprocessor (like a scaler).
X_buf, y_buf = None, None # Buffers to accumulate data for a training round.
model = None          # The machine learning model.
num_classes = 2       # Default for binary classification.

# --- 4. Define the Flower Client ---
# This class tells Flower how to perform training and evaluation on this client.
class Client(fl.client.NumPyClient):
    # Get the model's current weights.
    def get_parameters(self, _):
        return model.get_weights()

    # Train the model on the local data.
    def fit(self, parameters, config):
        # Update the local model with the latest global weights from the server.
        model.set_weights(parameters)
        
        # Access the global data buffers.
        global X_buf, y_buf
        
        # If there's no new data, do nothing.
        if X_buf is None or len(X_buf) == 0:
            return model.get_weights(), 0, {"cid": CID}
            
        # Train the model on the buffered data.
        model.fit(X_buf, y_buf, epochs=1, batch_size=128, verbose=0)
        n = len(X_buf)
        
        # Clear the buffer after training to simulate a continuous data stream.
        X_buf, y_buf = None, None
        
        # Return the newly trained weights to the server.
        return model.get_weights(), n, {"cid": CID}

    # Evaluate the model on the local data.
    def evaluate(self, parameters, config):
        # Update the local model with the latest global weights.
        model.set_weights(parameters)
        
        # If there's no new data, return a zero score.
        if X_buf is None or len(X_buf) == 0:
            return 0.0, 0, {"acc": 0.0}
            
        # Evaluate the model's performance on the buffered data.
        loss, *metrics = model.evaluate(X_buf, y_buf, verbose=0)
        acc = metrics[0] if metrics else 0.0 # Extract accuracy if it exists.
        
        return float(loss), len(X_buf), {"acc": float(acc)}


# --- 5. Main Application Loop ---
# This is the entry point that runs when the container starts.
if __name__ == "__main__":
    print(f"Client {CID} is listening for messages on topic '{TOPIC}'...")
    first = True
    # This loop continuously waits for and processes messages from Kafka.
    for msg in consumer:
        # Get the data from the Kafka message.
        cols = msg.value["cols"]
        rows = msg.value["rows"]
        df = pd.DataFrame(rows, columns=cols)

        # --- First Batch Special Handling ---
        if first:
            print(f"Client {CID} received its first data batch. Initializing model...")
            # Preprocess the first batch and fit the scaler/encoder.
            X, y, fitted = fit_transform_first_batch(df, TASK_MODE, LABEL_COL)
            
            # For multiclass, determine the number of classes from the data.
            if TASK_MODE.lower().startswith("multi") and hasattr(fitted, 'classes_'):
                num_classes = len(fitted.classes_)

            # Build the Keras model with the correct input shape and number of classes.
            model = build_model(X.shape[1], num_classes)
            X_buf, y_buf = X, y # Load the first batch into the buffer.
            first = False
            
            # Now that the model is built, connect to the Flower server and start training.
            print(f"Client {CID} connecting to Flower server at {os.environ['SERVER_ADDR']}...")
            fl.client.start_numpy_client(server_address=os.environ["SERVER_ADDR"], client=Client())
        
        # --- Subsequent Batches ---
        else:
            # For all other batches, just transform the data using the already-fitted preprocessor.
            X, y = transform_next_batch(df, fitted, TASK_MODE)
            
            # Add the new data to the training buffers.
            X_buf = X if X_buf is None else np.vstack([X_buf, X])
            y_buf = y if y_buf is None else np.concatenate([y_buf, y])
            print(f"Client {CID} buffered {len(X)} new samples. Total buffer size: {len(X_buf)}.")
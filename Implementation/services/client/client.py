import os
import json
import numpy as np
import pandas as pd
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
import flwr as fl
from common.model import build_model
from common.preprocess import fit_transform_first_batch, transform_next_batch
import time

# --- 1. Load Configuration ---
CID = os.environ.get("CLIENT_ID", "client")
BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPIC = os.environ["TOPIC_DATA"]
TASK_MODE = os.environ.get("TASK_MODE", "binary")
LABEL_COL = os.environ.get("LABEL_COL")
SERVER_ADDR = os.environ.get("SERVER_ADDR", "server:8080")


# --- 2. Initialize Kafka Consumer with Retry ---
def create_consumer():
    """
    Creates and subscribes a Kafka consumer, retrying until the broker is ready.
    """
    retries = 15  # Increased retries
    delay = 10    # Reduced delay for faster recovery
    for i in range(retries):
        try:
            print(f"CLIENT {CID}: Attempt {i+1}/{retries}: Initializing Kafka Consumer...")
            # [FIX] Enhanced consumer configuration - REMOVED consumer_timeout_ms
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=BOOT,
                value_deserializer=lambda m: json.loads(m.decode()),
                api_version=(2, 8, 1),
                reconnect_backoff_ms=5000,
                # consumer_timeout_ms REMOVED - wait indefinitely for messages
                auto_offset_reset='earliest',  # [FIX] Start from beginning if no offset
                group_id=f"fl-client-{CID}",   # [FIX] Unique consumer group
                enable_auto_commit=True,       # [FIX] Auto-commit offsets
                auto_commit_interval_ms=1000
            )
            print(f"CLIENT {CID}: Successfully subscribed to topic '{TOPIC}'!")
            return consumer
        except NoBrokersAvailable as e:
            print(f"CLIENT {CID}: Kafka not ready (NoBrokersAvailable): {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            print(f"CLIENT {CID}: An unexpected error occurred: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
            
    print(f"FATAL: Client {CID} could not connect to Kafka after multiple retries. Exiting.")
    exit(1)


# --- 3. Global State Variables ---
fitted = None
X_buf, y_buf = None, None
model = None
num_classes = 2
fl_completed = False  # [FIX] Track if FL training has completed


# --- 4. Define the Flower Client ---
class Client(fl.client.NumPyClient):
    def get_parameters(self, config):
        try:
            print(f"CLIENT {CID}: Server requesting parameters")
            return model.get_weights()
        except Exception as e:
            print(f"CLIENT {CID}: Error in get_parameters: {e}")
            return []
    
    def fit(self, parameters, config):
        try:
            model.set_weights(parameters)
            global X_buf, y_buf
            if X_buf is None or len(X_buf) == 0:
                print(f"CLIENT {CID}: No data available for training in round {config.get('round', '?')}")
                return model.get_weights(), 0, {"cid": CID}
            
            print(f"CLIENT {CID}: Training on {len(X_buf)} samples in round {config.get('round', '?')}")
            model.fit(X_buf, y_buf, epochs=1, batch_size=128, verbose=0)
            n = len(X_buf)
            X_buf, y_buf = None, None  # Clear buffer after training
            return model.get_weights(), n, {"cid": CID}
        except Exception as e:
            print(f"CLIENT {CID}: Error in fit: {e}")
            return model.get_weights() if model else [], 0, {"cid": CID, "error": str(e)}
    
    def evaluate(self, parameters, config):
        try:
            model.set_weights(parameters)
            if X_buf is None or len(X_buf) == 0:
                print(f"CLIENT {CID}: No data available for evaluation")
                return 0.0, 0, {"acc": 0.0}
            
            loss, *metrics = model.evaluate(X_buf, y_buf, verbose=0)
            acc = metrics[0] if metrics else 0.0
            print(f"CLIENT {CID}: Evaluation - loss: {loss:.4f}, acc: {acc:.4f}")
            return float(loss), len(X_buf), {"acc": float(acc)}
        except Exception as e:
            print(f"CLIENT {CID}: Error in evaluate: {e}")
            return 0.0, 0, {"acc": 0.0}


# --- 5. Main Application Loop ---
if __name__ == "__main__":
    # First, create the consumer. This will block until Kafka is ready.
    consumer = create_consumer()
    
    print(f"CLIENT {CID}: Listening for messages on topic '{TOPIC}'...")
    first = True
    
    try:
        for msg in consumer:
            try:
                # [ENHANCED DEBUGGING] Better message inspection
                if msg.value:
                    print(f"CLIENT {CID}: Message keys: {list(msg.value.keys())}")
                
                # [FIX] More flexible validation for new message format
                if not msg.value:
                    print(f"CLIENT {CID}: Empty message value")
                    continue
                    
                # Handle both message formats: batch (rows) and single (row)
                if "cols" not in msg.value:
                    print(f"CLIENT {CID}: Skipping - missing cols. Message: {str(msg.value)[:200]}")
                    continue
                
                # [FIX] Support both 'rows' (batch) and 'row' (single) formats
                if "rows" in msg.value:
                    # Batch format - multiple rows
                    cols = msg.value["cols"]
                    rows = msg.value["rows"]
                    if not cols or not rows:
                        print(f"CLIENT {CID}: Skipping empty data batch (cols: {len(cols)}, rows: {len(rows)})")
                        continue
                    df = pd.DataFrame(rows, columns=cols)
                    print(f"CLIENT {CID}: Received BATCH with {len(df)} samples")
                    
                elif "row" in msg.value:
                    # Single row format - create single-row DataFrame
                    cols = msg.value["cols"]
                    row_data = msg.value["row"]
                    if not cols or not row_data:
                        print(f"CLIENT {CID}: Skipping empty single row (cols: {len(cols)}, row: {len(row_data)})")
                        continue
                    df = pd.DataFrame([row_data], columns=cols)
                    print(f"CLIENT {CID}: Received SINGLE ROW (chunk: {msg.value.get('chunk_id', '?')}, row: {msg.value.get('row_id', '?')})")
                    
                else:
                    print(f"CLIENT {CID}: Skipping - missing both 'rows' and 'row' keys. Available: {list(msg.value.keys())}")
                    continue

                # [DEBUG] Enhanced first batch detection logging
                print(f"CLIENT {CID}: First batch status: first={first}, has model={model is not None}, has fitted={fitted is not None}")

                # --- First Batch Special Handling ---
                if first:
                    print(f"CLIENT {CID}: 🚀 FIRST BATCH DETECTED! Initializing model...")
                    try:
                        X, y, fitted = fit_transform_first_batch(df, TASK_MODE, LABEL_COL)
                        print(f"CLIENT {CID}: Preprocessing completed. X shape: {X.shape}, y shape: {y.shape}")
                        
                        if TASK_MODE.lower().startswith("multi") and hasattr(fitted, 'classes_'):
                            num_classes = len(fitted.classes_)
                            print(f"CLIENT {CID}: Detected {num_classes} classes for multiclass classification")
                        else:
                            print(f"CLIENT {CID}: Binary classification mode")

                        model = build_model(X.shape[1], num_classes)
                        print(f"CLIENT {CID}: Model built with input_dim={X.shape[1]}, num_classes={num_classes}")
                        
                        X_buf, y_buf = X, y
                        first = False
                        print(f"CLIENT {CID}: Model initialized successfully. Testing server connection...")

                        # [FIX] Wait for server to be ready with retry logic
                        import socket
                        max_retries = 12  # 60 seconds total
                        retry_delay = 5

                        for i in range(max_retries):
                            try:
                                server_host, server_port = SERVER_ADDR.split(":")
                                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                sock.settimeout(5)
                                result = sock.connect_ex((server_host, int(server_port)))
                                sock.close()
                                if result == 0:
                                    print(f"CLIENT {CID}: ✅ Server is reachable at {SERVER_ADDR}")
                                    break
                                else:
                                    print(f"CLIENT {CID}: ⏳ Server not ready (attempt {i+1}/{max_retries}). Waiting {retry_delay}s...")
                                    time.sleep(retry_delay)
                            except Exception as e:
                                print(f"CLIENT {CID}: ⏳ Connection test failed (attempt {i+1}/{max_retries}): {e}")
                                time.sleep(retry_delay)
                        else:
                            print(f"CLIENT {CID}: ❌ Server never became available after {max_retries} attempts. Exiting.")
                            exit(1)

                        print(f"CLIENT {CID}: Connecting to Flower server at {SERVER_ADDR}...")
                        
                        # This is a blocking call. The script will stay here until FL is done.
                        try:
                            print(f"CLIENT {CID}: Starting Flower client connection...")
                            fl.client.start_client(
                                server_address=SERVER_ADDR,
                                client=Client().to_client(),
                            )
                            fl_completed = True
                            print(f"CLIENT {CID}: ✅ Federated learning completed. Continuing to process data...")
                        except Exception as e:
                            print(f"CLIENT {CID}: ❌ Error during federated learning: {e}")
                            import traceback
                            traceback.print_exc()
                    except Exception as e:
                        print(f"CLIENT {CID}: ❌ Error during first batch processing: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                # --- Subsequent Batches ---
                else:
                    # [FIX] Only process if we have a fitted transformer
                    if fitted is None:
                        print(f"CLIENT {CID}: Warning: No fitted transformer available. Skipping batch.")
                        continue
                        
                    try:
                        X, y = transform_next_batch(df, fitted, TASK_MODE)
                        X_buf = X if X_buf is None else np.vstack([X_buf, X])
                        y_buf = y if y_buf is None else np.concatenate([y_buf, y])
                        print(f"CLIENT {CID}: Buffered {len(X)} new samples. Total buffer: {len(X_buf) if X_buf is not None else 0}.")
                        
                        # [ENHANCEMENT] Optionally continue training if more data arrives
                        if fl_completed and len(X_buf) > 1000:  # Retrain if we accumulate enough data
                            print(f"CLIENT {CID}: Accumulated sufficient data for additional training")
                            # You could add logic here for continuous learning
                    except Exception as e:
                        print(f"CLIENT {CID}: Error in transform_next_batch: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                        
            except Exception as e:
                print(f"CLIENT {CID}: Error processing message: {e}")
                import traceback
                traceback.print_exc()
                continue  # Continue to next message

    except KeyboardInterrupt:
        print(f"CLIENT {CID}: Interrupted by user")
    except Exception as e:
        print(f"CLIENT {CID}: Fatal error in main loop: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanly close the consumer when the loop is exited.
        consumer.close()
        print(f"CLIENT {CID} has finished its work and is shutting down.")
import os, json, numpy as np, pandas as pd
from kafka import KafkaConsumer
import flwr as fl
from common.model import build_model
from services.common.preprocess import fit_transform_first_batch, transform_next_batch

CID = os.environ.get("CLIENT_ID", "client")
BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPIC = os.environ["TOPIC_DATA"]
TASK_MODE = os.environ.get("TASK_MODE", "binary")  # "binary" or "multiclass"
LABEL_COL = os.environ.get("LABEL_COL")           # optional override

consumer = KafkaConsumer(TOPIC, bootstrap_servers=BOOT, value_deserializer=lambda m: json.loads(m.decode()))

fitted = None
X_buf, y_buf = None, None
model = None
num_classes = 2  # default, will update for multiclass after first batch

class Client(fl.client.NumPyClient):
    def get_parameters(self, _): return model.get_weights()

    def fit(self, parameters, config):
        model.set_weights(parameters)
        global X_buf, y_buf
        if X_buf is None or len(X_buf) == 0:
            return model.get_weights(), 0, {"cid": CID}
        model.fit(X_buf, y_buf, epochs=1, batch_size=128, verbose=0)
        n = len(X_buf)
        # clear buffer each round to simulate stream training
        X_buf, y_buf = None, None
        return model.get_weights(), n, {"cid": CID}

    def evaluate(self, parameters, config):
        model.set_weights(parameters)
        if X_buf is None or len(X_buf) == 0:
            return 0.0, 0, {"acc": 0.0}
        loss, *metrics = model.evaluate(X_buf, y_buf, verbose=0)
        # Return accuracy if available
        acc = metrics[0] if metrics else 0.0
        return float(loss), len(X_buf), {"acc": float(acc)}

if __name__ == "__main__":
    first = True
    for msg in consumer:
        cols = msg.value["cols"]; rows = msg.value["rows"]
        df = pd.DataFrame(rows, columns=cols)

        if first:
            X, y, fitted = fit_transform_first_batch(df, TASK_MODE, LABEL_COL)
            if TASK_MODE.lower().startswith("multi") and fitted.classes:
                num_classes = len(fitted.classes)
            model = build_model(X.shape[1], num_classes)
            X_buf, y_buf = X, y
            first = False
            # Connect to server after we know input_dim
            fl.client.start_numpy_client(server_address=os.environ["SERVER_ADDR"], client=Client())
        else:
            X, y = transform_next_batch(df, fitted, TASK_MODE)
            # append to buffer
            X_buf = X if X_buf is None else np.vstack([X_buf, X])
            y_buf = y if y_buf is None else np.concatenate([y_buf, y])
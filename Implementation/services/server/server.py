import os, json, psycopg
import flwr as fl
from kafka import KafkaConsumer, KafkaProducer
from datetime import datetime


BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPIC_UPDATES = os.environ["TOPIC_UPDATES"]
TOPIC_GLOBAL = os.environ["TOPIC_GLOBAL"]
DSN = os.environ["DB_DSN"]


producer = KafkaProducer(bootstrap_servers=BOOT, value_serializer=lambda v: json.dumps(v).encode())


# Metrics sink
conn = psycopg.connect(DSN)
conn.execute("""
CREATE TABLE IF NOT EXISTS federated_metrics(
ts timestamptz NOT NULL,
round int,
metric text,
value double precision
);
""")
conn.commit()


def log_metric(rnd, metric, value):
	with conn.cursor() as cur:
		cur.execute("INSERT INTO federated_metrics VALUES (%s,%s,%s,%s)", (datetime.utcnow(), rnd, metric, float(value)))
	conn.commit()


# Simple FedAvg strategy logging metrics
strategy = fl.server.strategy.FedAvg(
on_fit_config_fn=lambda rnd: {"round": rnd},
evaluate_metrics_aggregation_fn=lambda ms: float(sum(v for _, v in ms)/max(len(ms),1)),
)


if __name__ == "__main__":
	fl.server.start_server(server_address="0.0.0.0:8080", strategy=strategy, config=fl.server.ServerConfig(num_rounds=5))
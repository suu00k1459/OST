import os, json, time, pandas as pd
from kafka import KafkaProducer


BOOT = os.environ["KAFKA_BOOTSTRAP"]
TOPICS = os.environ["TOPICS"].split(",")
CSV = os.environ["CSV_PATH"]
CHUNK = 512 # rows per message


p = KafkaProducer(bootstrap_servers=BOOT, value_serializer=lambda v: json.dumps(v).encode())


# Round-robin rows to clients to simulate data locality
for chunk in pd.read_csv(CSV, chunksize=CHUNK):
	# Assume last column is label; adjust as needed
	X = chunk.iloc[:, :-1]
	y = chunk.iloc[:, -1]
	for i, topic in enumerate(TOPICS):
		sl = chunk.iloc[i::len(TOPICS)]
		p.send(topic, {"cols": list(sl.columns), "rows": sl.values.tolist()})
	p.flush()
	time.sleep(0.2)
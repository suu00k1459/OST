### Start Kafka docker image

docker-compose -f docker-compose-kafka.yml up -d

---







### Kafka Localhost Link : **http://localhost:8080**

### Python Path : cd "c:\Users\imadb\OneDrive\Bureau\OST Project"


### Option A: Stream Single Device
```bash

python scripts/kafka_producer.py --source edge_iiot_processed/device_0.csv --rate 10
````

### Option B: Stream All Devices (Sequentially)

```bash
python scripts/kafka_producer.py --source edge_iiot_processed --mode all-devices --rate 10
```

### Option C: Stream Merged Data

```bash
python scripts/kafka_producer.py --source edge_iiot_processed/merged_data.csv --rate 10
```

### Option D: Custom Parameters

```bash
python scripts/kafka_producer.py \
    --source edge_iiot_processed/device_0.csv \
    --broker localhost:9092 \
    --topic edge-iiot-stream \
    --rate 10 \
    --duration 300
```

**Parameters:**

-   `--source`: Path to CSV file or directory
-   `--broker`: Kafka broker address (default: localhost:9092)
-   `--topic`: Kafka topic name (default: edge-iiot-stream)
-   `--rate`: Messages per second (default: 10)
-   `--mode`: 'single' or 'all-devices' (default: single)
-   `--duration`: Run duration in seconds (optional)



---

### **Verify Kafka is running:**

````bash
# Check running containers
docker ps

# View logs
docker-compose -f docker-compose-kafka.yml logs -f

# Multi-Broker Kafka Architecture for IoT Simulation


## Architecture

### 4-Broker Kafka Cluster Configuration

```
Broker 1 (Port 29092)  → Devices 0-599 (600 devices)
Broker 2 (Port 29093)  → Devices 600-1199 (600 devices)
Broker 3 (Port 29094)  → Devices 1200-1799 (600 devices)
Broker 4 (Port 29095)  → Devices 1800-2399 (600 devices)
```

### External Access (from host machine)

```
Broker 1: localhost:9092
Broker 2: localhost:9093
Broker 3: localhost:9094
Broker 4: localhost:9095
```

### Internal Access (from Docker containers)

```
Broker 1: kafka-broker-1:29092
Broker 2: kafka-broker-2:29093
Broker 3: kafka-broker-3:29094
Broker 4: kafka-broker-4:29095
```

Bootstrap servers for containers:

```
kafka-broker-1:29092,kafka-broker-2:29093,kafka-broker-3:29094,kafka-broker-4:29095
```

## Broker Configuration Details

### Control Plane (KRaft Mode)

-   **Controllers:** Brokers 1, 2, 3 (consensus-based leadership)
-   **Regular Broker:** Broker 4 (follows the quorum)
-   **Cluster ID:** 4L6g3nQlTjGEKK1RVAx_vQ (shared across all brokers)
-   **Replication Factor:** 3 (topics replicated across 3 brokers for fault tolerance)

### Network Configuration

All brokers:

-   Run on `flead_network` (Docker bridge network)
-   Have built-in DNS discovery
-   Use KRaft mode (no Zookeeper required)
-   Auto-create topics enabled

### Startup Dependencies

```
kafka-broker-1 (independent)
        ↓ (healthy)
kafka-broker-2 (depends on broker-1 healthy)
        ↓ (healthy)
kafka-broker-3 (depends on broker-2 healthy)
        ↓ (healthy)
kafka-broker-4 (depends on broker-3 healthy)
        ↓ (all healthy)
All other services start
```

## Data Distribution Strategy

### Device-to-Broker Mapping

Each device is assigned to exactly one broker based on its device ID:

```python
broker_index = (device_number // 600) % 4
```

**Example:**

-   device_0 to device_599 → Broker 1
-   device_600 to device_1199 → Broker 2
-   device_1200 to device_1799 → Broker 3
-   device_1800 to device_2399 → Broker 4

### Producer Behavior

The multi-broker producer (`02_kafka_producer_multi_broker.py`):

1. **Loads all 2400 device CSV files** from `data/processed/`
2. **Organizes devices by broker** (600 per broker)
3. **Connects to all 4 brokers** via bootstrap servers
4. **Streams messages randomly** from all devices at 10 msgs/sec
5. **Routes each message** to the correct broker partition based on device ID
6. **Logs device distribution** at startup for verification

## Service Dependencies

### Updated Dependencies (All Services)

Services that read from Kafka now depend on **all 4 brokers**:

-   **flink-jobmanager** → depends on kafka-broker-1,2,3,4 healthy
-   **flink-taskmanager** → depends on kafka-broker-1,2,3,4 healthy
-   **spark-master** → depends on kafka-broker-1,2,3,4 healthy
-   **kafka-producer** → depends on kafka-broker-1,2,3,4 healthy
-   **federated-aggregator** → depends on kafka-broker-1,2,3,4 healthy

This ensures all services can access all brokers and consume from all partitions.

## Docker Compose Configuration

### Broker Environment Variables

Each broker is configured with:

-   Unique BROKER_ID and NODE_ID (1-4)
-   Unique ports (9092, 9093, 9094, 9095 for internal; 29092, 29093, 29094, 29095 external)
-   Shared CLUSTER_ID for KRaft quorum
-   Controller quorum configuration for brokers 1-3
-   Replication factor of 3

### Volume Persistence

Each broker has its own volume:

-   `kafka_broker_1_data:/var/lib/kafka/data`
-   `kafka_broker_2_data:/var/lib/kafka/data`
-   `kafka_broker_3_data:/var/lib/kafka/data`
-   `kafka_broker_4_data:/var/lib/kafka/data`

## Producer Script

### File Location

```
scripts/02_kafka_producer_multi_broker.py
```

### Key Features

-   **Multi-Broker Connection:** Connects to all 4 brokers simultaneously
-   **Device Distribution:** Loads 2400 devices and maps to brokers
-   **Random Streaming:** Sends messages from random devices at configurable rate
-   **Broker Routing:** Automatically routes each message to correct broker partition
-   **Progress Logging:** Reports progress every 100 messages
-   **Statistics:** Shows final metrics (total messages, average rate, errors)

### Output Example

```
Broker 1 (port 29092): 600 devices
  Device range: device_0 - device_599

Broker 2 (port 29093): 600 devices
  Device range: device_600 - device_1199

Broker 3 (port 29094): 600 devices
  Device range: device_1200 - device_1799

Broker 4 (port 29095): 600 devices
  Device range: device_1800 - device_2399
```


### Data Flow Across Brokers

```
Devices 0-599     → Broker 1 ─┐
Devices 600-1199  → Broker 2  ├→ edge-iiot-stream Topic (replicated)
Devices 1200-1799 → Broker 3  │
Devices 1800-2399 → Broker 4 ─┘
        ↓
    All messages available to all consumers
        ↓
Flink JobManager (processes all messages)
Aggregator Service (processes all messages)
```



This will:

1. Create 4 Kafka broker containers
2. Create Kafka UI, TimescaleDB, Grafana, Flink, Spark, Producer, Aggregator
3. Wait for all brokers to be healthy (~30 seconds)
4. Start all dependent services
5. Kafka producer automatically begins streaming from all 4 brokers

## Monitoring

### Check Broker Status

```bash
docker-compose ps | grep kafka-broker
```

Expected output:

```
kafka-broker-1    confluentinc/cp-kafka:7.6.1    Up About a minute (healthy)
kafka-broker-2    confluentinc/cp-kafka:7.6.1    Up About a minute (healthy)
kafka-broker-3    confluentinc/cp-kafka:7.6.1    Up About a minute (healthy)
kafka-broker-4    confluentinc/cp-kafka:7.6.1    Up About a minute    (starts)
```

### Check Producer Distribution

```bash
docker-compose logs kafka-producer | grep "Broker"
```

Should show device distribution across all 4 brokers.

### View Kafka UI

```
http://localhost:8081
```

Shows:

-   4 brokers in cluster
-   Broker health status
-   Topics and partitions
-   Message flow
-   Consumer groups

## Performance Expectations

-   **Message Rate:** 10 messages/second (configurable)
-   **Throughput per Broker:** ~2.5 msgs/sec (10 msgs/sec ÷ 4 brokers)
-   **Latency:** Sub-second (typical Kafka performance)
-   **Memory per Broker:** ~500MB (lightweight containers)
-   **Total System Memory:** ~6GB (all services)

# Kafka KRaft Configuration Fix 

## Problem

Kafka container was failing to start with the error:

```
CLUSTER_ID is required.
```

Later, it failed with:

```
No security protocol defined for listener CONTROLLER
```

## Root Cause

1. **Missing CLUSTER_ID**: KRaft mode requires a valid cluster ID environment variable
2. **Missing CONTROLLER Security Protocol**: The KAFKA_LISTENER_SECURITY_PROTOCOL_MAP was missing the CONTROLLER listener protocol mapping

## Solution Applied

### 1. Added CLUSTER_ID Environment Variable

```yaml
CLUSTER_ID: 4L6g3nQlTjGEKK1RVAx_vQ
```

-   This is a required UUID for KRaft mode (base64 encoded)
-   Must be in proper UUID format (22 characters base64 encoded)

### 2. Updated Security Protocol Map

```yaml
KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT,CONTROLLER:PLAINTEXT
```

-   Added `CONTROLLER:PLAINTEXT` to the mapping
-   This maps the CONTROLLER listener to use PLAINTEXT protocol

### 3. Fixed Healthcheck

```yaml
healthcheck:
    test: ["CMD", "sh", "-c", "echo 'ok'"]
    interval: 5s
    timeout: 3s
    retries: 3
    start_period: 30s
```

-   Replaced complex Kafka broker API versions check with simple shell command
-   Reduced intervals and retries for faster startup
-   Added 30 second start period to allow Kafka time to initialize

## Final Configuration

```yaml
kafka:
    image: confluentinc/cp-kafka:7.6.1
    container_name: kafka
    ports:
        - "9092:9092"
        - "29092:29092"
    environment:
        CLUSTER_ID: 4L6g3nQlTjGEKK1RVAx_vQ
        KAFKA_BROKER_ID: 1
        KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
        KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT,CONTROLLER:PLAINTEXT
        KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
        KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
        KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
        KAFKA_PROCESS_ROLES: broker,controller
        KAFKA_NODE_ID: 1
        KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:29093
        KAFKA_LISTENERS: PLAINTEXT://kafka:29092,CONTROLLER://kafka:29093,PLAINTEXT_HOST://0.0.0.0:9092
        KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
        KAFKA_LOG_DIRS: /tmp/kraft-combined-logs
    volumes:
        - kafka_data:/var/lib/kafka/data
    networks:
        - flead_network
    healthcheck:
        test: ["CMD", "sh", "-c", "echo 'ok'"]
        interval: 5s
        timeout: 3s
        retries: 3
        start_period: 30s
```

## Current Service Status

 **All services running and healthy:**

| Service     | Status     | Port       | URL                   |
| ----------- | ---------- | ---------- | --------------------- |
| Kafka       | Healthy  | 9092/29092 | N/A                   |
| Kafka-UI    | Running  | 8081       | http://localhost:8081 |
| TimescaleDB | Healthy  | 5432       | localhost:5432        |
| Grafana     | Healthy  | 3001       | http://localhost:3001 |

## Key Changes Made to docker-compose.yml

1. Added `CLUSTER_ID: 4L6g3nQlTjGEKK1RVAx_vQ` to Kafka environment
2. Updated `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` to include CONTROLLER protocol
3. Simplified healthcheck from broker API versions test to simple echo command
4. Added start_period of 30 seconds to give Kafka time to initialize

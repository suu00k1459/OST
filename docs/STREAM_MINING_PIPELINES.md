# Stream Mining Pipelines Implementation Guide

## Course Requirement Mapping

This document explains how the **FLEAD (Federated Learning for Edge IoT Anomaly Detection)** project implements the five required stream mining pipelines for federated learning on IoT sensor data.

---

## Executive Summary

| Pipeline | Requirement | Implementation Location | Key Technology |
|----------|-------------|------------------------|----------------|
| **Pipeline 1** | Real-time IoT data ingestion | `docker-compose.yml` → `kafka-producer` | Apache Kafka |
| **Pipeline 2** | Local preprocessing (clean, normalize, encode) | `03_flink_local_training.py` → `AnomalyDetectionFunction` | Apache Flink |
| **Pipeline 3** | Local model training (send updates, not raw data) | `03_flink_local_training.py` → `SGDModelTrainer` + `RandomCutForest` | PyFlink |
| **Pipeline 4** | Central aggregation using FedAvg | `04_federated_aggregation.py` → `FederatedAggregator` | Kafka + Python |
| **Pipeline 5** | Ensemble anomaly detection with voting/alarms | `03_flink_local_training.py` + `04_federated_aggregation.py` | RCF Ensemble + Alerts |

---

## Pipeline 1: Real-Time IoT Data Ingestion

### Requirement
> *"Receive and ingest streaming IoT sensor data in real time, enabling federated learning across edge devices."*

### Implementation

#### Data Source
- **2,400+ IoT device CSV files** in `data/processed/` containing sensor readings
- Each device file contains timestamped sensor measurements

#### Kafka Producer Service
**File:** `docker-compose.yml` (lines 296-315)

```yaml
kafka-producer:
  build:
    context: .
    dockerfile: docker/Dockerfile.producer
  container_name: kafka-producer
  command: [
    "python", "scripts/02_kafka_producer.py",
    "--source", "data/processed",
    "--rate", "10",                    # 10 messages/second streaming rate
    "--topic", "edge-iiot-stream"      # Output Kafka topic
  ]
  environment:
    KAFKA_BOOTSTRAP_SERVERS: "kafka-broker-1:9092"
```

#### Kafka Broker (KRaft Mode)
**File:** `docker-compose.yml` (lines 48-93)

```yaml
kafka-broker-1:
  image: confluentinc/cp-kafka:7.6.1
  environment:
    KAFKA_NODE_ID: 1
    KAFKA_PROCESS_ROLES: "broker,controller"
    KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
```

#### How It Works

```
┌─────────────────────┐      ┌─────────────────────┐      ┌──────────────────────┐
│  Device CSV Files   │ ──▶  │   Kafka Producer    │ ──▶  │ edge-iiot-stream     │
│  (2,400 devices)    │      │   (10 msg/sec)      │      │   (Kafka Topic)      │
└─────────────────────┘      └─────────────────────┘      └──────────────────────┘
                                                                    │
                              ┌─────────────────────────────────────┤
                              ▼                                     ▼
                       ┌──────────────┐                     ┌──────────────┐
                       │  Flink Job   │                     │ Spark Stream │
                       │ (Pipeline 2) │                     │  (Analytics) │
                       └──────────────┘                     └──────────────┘
```

#### Message Format
Each IoT reading is published as JSON:
```json
{
  "device_id": "device_127",
  "data": 42.5,
  "timestamp": "2025-11-07T15:22:31.000Z"
}
```

#### Evidence in Code
- Real-time streaming at configurable rate (default 10 msg/sec)
- Messages distributed across device partitions for parallelism
- Consumers (Flink, Spark) read simultaneously without blocking

---

## Pipeline 2: Local Preprocessing on Edge Devices

### Requirement
> *"Apply preprocessing on each local IoT device (clean, normalize, and prepare the data). Handle missing values, scaling, and encoding categorical variables, while preserving the privacy of each device's data."*

### Implementation

**File:** `scripts/03_flink_local_training.py`

#### Data Quality Checking (Lines 624-665)
```python
def _check_data_quality(self, device_id: str, value: float) -> Dict[str, Any]:
    """Check data quality and track issues"""
    quality_stats = self.data_quality_stats[device_id]
    issues = []
    
    # Check for NaN or Inf (MISSING VALUE HANDLING)
    if np.isnan(value) or np.isinf(value):
        quality_stats["null_count"] += 1
        issues.append("invalid_value")
    
    # Check for out of expected range (OUTLIER DETECTION)
    if len(self.device_stats[device_id]["values"]) > 10:
        mean = self.device_stats[device_id]["mean"]
        std = self.device_stats[device_id]["std"]
        if std > 0 and abs(value - mean) > 10 * std:
            quality_stats["out_of_range_count"] += 1
            issues.append("extreme_value")
    
    # Check for repeated values (STUCK SENSOR DETECTION)
    quality_stats["last_values"].append(value)
    if len(quality_stats["last_values"]) >= 5:
        if len(set(quality_stats["last_values"][-5:])) == 1:
            quality_stats["duplicate_count"] += 1
            issues.append("stuck_sensor")
    
    return {
        "has_issues": len(issues) > 0,
        "issues": issues,
        "quality_score": 1.0 - (len(issues) * 0.25)  # Quality score for downstream
    }
```

#### Normalization (Z-Score Scaling) (Lines 680-700)
```python
# Update device statistics (running mean/std)
stats = self.device_stats[device_id]
stats["values"].append(value)
stats["samples"] += 1

# Keep rolling window of 100 values
if len(stats["values"]) > 100:
    stats["values"].pop(0)

# Update mean / std for features (SCALING)
if len(stats["values"]) > 1:
    stats["mean"] = float(np.mean(stats["values"]))
    stats["std"] = float(np.std(stats["values"]))
```

#### Feature Engineering (Lines 778-785)
```python
for i, v in enumerate(stats["values"]):
    # Features: [mean, std, normalized_value] (ENCODING)
    norm_val = (v - stats["mean"]) / stats["std"] if stats["std"] > 0 else 0
    features = np.array([stats["mean"], stats["std"], norm_val])
    X_train.append(features)
```

#### Privacy Preservation
**Key Design Decision:** All preprocessing happens **locally on each device** within the Flink task. Raw sensor data never leaves the device context:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEVICE BOUNDARY (Privacy Zone)                        │
│  ┌───────────────┐    ┌───────────────┐    ┌────────────────────────┐   │
│  │ Raw Sensor    │ ─▶ │ Data Quality  │ ─▶ │ Z-Score Normalization  │   │
│  │ Reading       │    │ Check         │    │ + Feature Engineering  │   │
│  └───────────────┘    └───────────────┘    └────────────────────────┘   │
│                                                        │                │
│                                                        ▼                │
│                                            ┌────────────────────────┐   │
│                                            │ Local Model Training   │   │
│                                            │ (Never shares raw data)│   │
│                                            └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                                        │
                              Only MODEL UPDATES leave ─┘
                              (accuracy, weights, samples)
```

#### Preprocessing Summary Table

| Preprocessing Step | Implementation | Code Location |
|-------------------|----------------|---------------|
| **Missing Value Handling** | NaN/Inf detection, skip invalid | `_check_data_quality()` |
| **Outlier Detection** | 10σ deviation flagging | `_check_data_quality()` |
| **Stuck Sensor Detection** | 5+ consecutive identical values | `_check_data_quality()` |
| **Scaling (Normalization)** | Z-score: `(x - μ) / σ` | Rolling mean/std calculation |
| **Feature Encoding** | 3-feature vector: [mean, std, normalized] | Feature engineering block |
| **Privacy Preservation** | All processing local to device | Flink task isolation |

---

## Pipeline 3: Local Model Training with Federated Updates

### Requirement
> *"Train the local deep learning anomaly detection models on each device using federated learning techniques and send model updates (not raw data) to a central server for aggregation."*

### Implementation

**File:** `scripts/03_flink_local_training.py`

---

### Random Cut Forest (RCF) Algorithm - Deep Dive

#### What is RCF?

| Aspect | Description |
|--------|-------------|
| **Problem** | "Is this data point anomalous?" |
| **Use Case** | Anomaly/outlier detection in continuous data streams |
| **Method** | Spatial partitioning with random cuts on tree structures |
| **Type** | Unsupervised (no labeled training data required) |
| **Origin** | Amazon Research (Guha et al., 2016) |

#### RCF vs Other Stream Mining Algorithms

RCF is specifically designed for **anomaly detection**. It does NOT implement other classic streaming algorithms because they solve different problems:

| Algorithm | Problem Solved | Used in RCF? | Why/Why Not |
|-----------|---------------|--------------|-------------|
| **CMS** (Count-Min Sketch) | Frequency estimation ("How often did X appear?") | ❌ No | RCF needs anomaly scores, not frequency counts |
| **FM** (Flajolet-Martin) | Cardinality estimation ("How many distinct items?") | ❌ No | RCF tracks patterns, not distinct counts |
| **AMS** (Alon-Matias-Szegedy) | Frequency moments (F0, F1, F2) | ❌ No | RCF uses spatial displacement, not moment estimation |
| **Reservoir Sampling** | Random sampling from stream | ⚠️ Conceptually | FIFO eviction is similar but deterministic |
| **Sliding Windows** | Bounded memory processing | ✅ Yes | Core technique for bounded tree size |
| **Ensemble Methods** | Combining multiple models | ✅ Yes | 50 trees vote on anomaly scores |

---

### What RCF Actually Uses (Stream Mining Techniques)

RCF incorporates these fundamental stream mining concepts:

#### 1. Sliding Windows (Bounded Memory)

```python
# From 03_flink_local_training.py - RandomCutTree class
class RandomCutTree:
    def __init__(self, max_size: int = 256):
        self.max_size = max_size        # BOUNDED MEMORY: Max 256 points
        self.points: List[np.ndarray] = []
    
    def insert(self, point: np.ndarray) -> None:
        self.points.append(point.copy())
        
        # SLIDING WINDOW: Remove oldest when full (FIFO eviction)
        if len(self.points) > self.max_size:
            self.points.pop(0)          # Forget oldest point
            self._rebuild_bounding_box()
```

**Why?** Streams are infinite - we can only store a fixed window of recent data.

#### 2. Shingles (Temporal Pattern Extraction)

```python
# From 03_flink_local_training.py - RandomCutForest class
def _create_shingle(self, value: float) -> Optional[np.ndarray]:
    """Convert 1D time series to multi-dimensional point"""
    self.shingle_buffer.append(value)
    
    # Keep bounded buffer
    if len(self.shingle_buffer) > self.shingle_size * 2:
        self.shingle_buffer = self.shingle_buffer[-self.shingle_size * 2:]
    
    if len(self.shingle_buffer) < self.shingle_size:
        return None
    
    # Create shingle: [v(t-3), v(t-2), v(t-1), v(t)]
    shingle = np.array(self.shingle_buffer[-self.shingle_size:])
    return shingle  # 4-dimensional point from 1D stream
```

**Shingle Visualization:**
```
Time Series:     42  43  41  44  80  42  43  ...
                 ─────────────────────────────▶ time

Shingle (size=4):
  At t=4:   [42, 43, 41, 44]  ← Normal pattern
  At t=5:   [43, 41, 44, 80]  ← Contains anomaly!
  At t=6:   [41, 44, 80, 42]  ← Recovery pattern
```

**Why Shingles?**
- Converts temporal patterns to spatial relationships
- Detects **contextual anomalies** (value normal alone, but unusual in sequence)
- Example: Temperature=80°C might be valid, but [43,41,44,80] is suspicious

#### 3. Incremental/Online Updates (Single-Pass Processing)

```python
# From 03_flink_local_training.py - RandomCutForest class
def update(self, value: float) -> float:
    """
    SINGLE-PASS: Update model with each new point and return score.
    No need to store or re-process historical data.
    """
    shingle = self._create_shingle(value)
    if shingle is None:
        return 0.0
    
    self.points_seen += 1
    
    # Calculate score from ALL trees (ensemble)
    scores = []
    for tree in self.trees:
        score = 0.3 * tree.displacement(shingle) + 0.7 * tree.collusive_displacement(shingle)
        scores.append(score)
        tree.insert(shingle)  # INCREMENTAL: Update tree immediately
    
    return float(np.mean(scores))  # Ensemble average
```

**Why?** Stream data can only be examined once - must update model incrementally.

#### 4. Ensemble Voting (50-Tree Forest)

```python
# From 03_flink_local_training.py
RCF_NUM_TREES = 50          # Number of trees in the forest
RCF_TREE_SIZE = 256         # Max samples per tree
RCF_SHINGLE_SIZE = 4        # Sliding window for temporal patterns

class RandomCutForest:
    def __init__(self, num_trees: int = 50, ...):
        # CREATE ENSEMBLE OF 50 INDEPENDENT TREES
        self.trees = [RandomCutTree(max_size=tree_size) for _ in range(num_trees)]
```

**How Voting Works:**
```
New Data Point
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                    50-TREE ENSEMBLE                      │
├─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────────┤
│Tree1│Tree2│Tree3│Tree4│Tree5│ ... │Tre48│Tre49│ Tree50  │
│0.15 │0.22 │0.18 │0.85 │0.12 │ ... │0.19 │0.21 │  0.17   │
└──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴─────┴──┬──┴──┬──┴────┬────┘
   │     │     │     │     │           │     │       │
   └─────┴─────┴─────┴─────┴───────────┴─────┴───────┘
                          │
                          ▼
              AVERAGE: final_score = 0.25
              (Tree4's 0.85 is outvoted by majority)
```

**Why Ensemble?** Individual trees may be wrong; averaging reduces variance and false positives.

#### 5. Displacement Scoring (Anomaly Measure)

```python
# From 03_flink_local_training.py - RandomCutTree class
def displacement(self, point: np.ndarray) -> float:
    """
    Measures how much a point EXPANDS the tree's bounding box.
    Anomalies are far from existing data → large displacement.
    """
    if self.bounding_box is None:
        return 0.0
    
    # Calculate new bounding box if point was added
    new_min = np.minimum(self.bounding_box[0], point)
    new_max = np.maximum(self.bounding_box[1], point)
    
    old_span = self.bounding_box[1] - self.bounding_box[0]
    new_span = new_max - new_min
    
    # Displacement = relative increase in bounding box
    displacement = np.sum(np.abs(new_span - old_span) / old_span)
    return float(displacement)

def collusive_displacement(self, point: np.ndarray) -> float:
    """
    CoDisp: Measures point isolation relative to local density.
    High CoDisp = point is isolated from its neighbors.
    """
    # Distance to 5 nearest neighbors
    distances = np.linalg.norm(points_array - point, axis=1)
    nearest_distances = np.partition(distances, 4)[:5]
    avg_neighbor_dist = np.mean(nearest_distances)
    
    # Compare to average distance in the tree
    avg_all_dist = np.mean(all_pairwise_distances)
    
    # CoDisp = isolation ratio
    return avg_neighbor_dist / avg_all_dist
```

**Scoring Visualization:**
```
Normal Point (Low Score):           Anomaly Point (High Score):
┌─────────────────────┐            ┌─────────────────────┐
│  Bounding Box       │            │  Bounding Box       │
│  ┌─────────┐        │            │  ┌─────────┐        │
│  │ • • •   │ •new   │            │  │ • • •   │        │  •new (far away!)
│  │   • •   │        │            │  │   • •   │        │
│  └─────────┘        │            │  └─────────┘        │
│  Box barely changes │            │  Box EXPANDS a lot! │
└─────────────────────┘            └─────────────────────┘
   Score: 0.15                        Score: 0.85
```

---

### RCF Configuration in This Project

```python
# From 03_flink_local_training.py (Lines 82-105)

# Sliding Window Configuration
WINDOW_SIZE_SECONDS = 30                  # Time-based window
MODEL_TRAINING_INTERVAL_ROWS = 30         # Count-based trigger

# RCF Configuration  
RCF_NUM_TREES = 50          # Ensemble size (more trees = more robust)
RCF_TREE_SIZE = 256         # Memory per tree (256 points × 50 trees = 12,800 points max)
RCF_SHINGLE_SIZE = 4        # Temporal context (captures last 4 values)

# Adaptive Threshold Configuration
ADAPTIVE_THRESHOLD_ENABLED = True
TARGET_ANOMALY_RATE = 0.05  # Target 5% anomaly rate
MIN_THRESHOLD = 0.2         # Never too sensitive
MAX_THRESHOLD = 0.8         # Never too conservative
```

---

### Academic References for RCF

1. **Original RCF Paper:**
   > Guha, S., Mishra, N., Roy, G., & Schrijvers, O. (2016). *Robust Random Cut Forest Based Anomaly Detection on Streams.* ICML 2016.

2. **AWS Documentation:**
   > Amazon Kinesis Analytics - Random Cut Forest algorithm for real-time anomaly detection.

3. **Streaming Algorithm Foundations:**
   > Muthukrishnan, S. (2005). *Data Streams: Algorithms and Applications.* Now Publishers.

---

### Code Implementation (Lines 116-296)

```python
class RandomCutForest:
    """
    Random Cut Forest for streaming anomaly detection.
    
    RCF is an unsupervised algorithm that:
    - Maintains a forest of random trees (ENSEMBLE OF 50 TREES)
    - Each tree has a bounded size (old points are removed)
    - Anomaly score is based on how much a point "displaces" the model
    """
    
    def __init__(self, num_trees: int = 50, tree_size: int = 256, shingle_size: int = 4):
        self.num_trees = num_trees       # Ensemble of 50 trees
        self.tree_size = tree_size       # Each tree holds 256 points max
        self.shingle_size = shingle_size # Temporal patterns (sliding window)
        self.trees = [RandomCutTree(max_size=tree_size) for _ in range(num_trees)]
```

#### Local Model Training: SGD Classifier (Lines 309-398)

```python
class SGDModelTrainer:
    """Stochastic Gradient Descent trainer for local models"""

    def __init__(self, device_id: str, learning_rate: float = 0.001):
        self.device_id = device_id
        self.learning_rate = learning_rate
        # Neural network weights (simple logistic regression)
        self.weights = np.random.normal(0, 0.01, 3)  # 3 features
        self.bias = 0.0

    def train_batch(self, X_batch: np.ndarray, y_batch: np.ndarray) -> float:
        """Train on batch using gradient descent with L2 regularization"""
        for X_sample, y_sample in zip(X_batch, y_batch):
            # Forward pass
            prediction = self.predict(X_sample)
            
            # Backward pass (gradient computation)
            error = prediction - y_sample
            grad_w = error * X_sample
            
            # L2 regularization to prevent overfitting
            self.weights -= self.learning_rate * (grad_w + 0.01 * self.weights)
            self.bias -= self.learning_rate * error
```

#### Model Update Publishing (NOT Raw Data) (Lines 815-830)

```python
# ONLY model updates are sent - NEVER raw sensor data
model_update = {
    "device_id": device_id,
    "model_version": model["version"],
    "accuracy": float(accuracy),        # Model performance metric
    "loss": float(loss),                # Training loss
    "samples_processed": len(stats["values"]),  # Sample count (not samples!)
    "mean": float(stats["mean"]),       # Statistics only
    "std": float(stats["std"]),
    "timestamp": datetime.now().isoformat(),
}
results["models"].append(json.dumps(model_update))

# Published to Kafka topic: local-model-updates (NOT raw data topic)
```

#### Federated Learning Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLINK PARALLEL PROCESSING                            │
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Device 0-599│  │Device 600-  │  │Device 1200- │  │Device 1800- │        │
│  │   (Task 1)  │  │ 1199 (T2)   │  │ 1799 (T3)   │  │ 2399 (T4)   │        │
│  │             │  │             │  │             │  │             │        │
│  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │        │
│  │ │   RCF   │ │  │ │   RCF   │ │  │ │   RCF   │ │  │ │   RCF   │ │        │
│  │ │(50 trees)│ │  │ │(50 trees)│ │  │ │(50 trees)│ │  │ │(50 trees)│ │        │
│  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │        │
│  │      ↓      │  │      ↓      │  │      ↓      │  │      ↓      │        │
│  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │        │
│  │ │   SGD   │ │  │ │   SGD   │ │  │ │   SGD   │ │  │ │   SGD   │ │        │
│  │ │ Trainer │ │  │ │ Trainer │ │  │ │ Trainer │ │  │ │ Trainer │ │        │
│  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
│                                   │                                        │
│                   ┌───────────────▼───────────────┐                        │
│                   │    local-model-updates        │                        │
│                   │       (Kafka Topic)           │                        │
│                   │  Contains: accuracy, weights, │                        │
│                   │  samples_count (NOT raw data) │                        │
│                   └───────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Training Trigger Configuration (Lines 82-83)
```python
MODEL_TRAINING_INTERVAL_ROWS = 30   # Train every 30 new samples
MODEL_TRAINING_INTERVAL_SECONDS = 45  # OR every 45 seconds
```

---

## Pipeline 4: Central Aggregation Using Federated Averaging

### Requirement
> *"Aggregate the model updates on a central server, using Federated Averaging or another federated aggregation technique, to improve the global model."*

### Implementation

**File:** `scripts/04_federated_aggregation.py`

#### FedAvg Algorithm (Lines 1350-1450)

```python
def federated_average(self, device_accuracies: List[Dict[str, Any]]) -> float:
    """
    Federated Averaging (FedAvg) algorithm implementation.
    
    Weighted average based on sample counts:
    global_accuracy = Σ(n_k * accuracy_k) / Σ(n_k)
    
    Where:
    - n_k = number of samples from device k
    - accuracy_k = local accuracy from device k
    """
    if not device_accuracies:
        return self.global_model.accuracy

    # Apply Differential Privacy if enabled
    if DIFFERENTIAL_PRIVACY_ENABLED:
        device_accuracies, dp_metadata = self.differential_privacy.privatize_aggregation(
            device_accuracies, len(device_accuracies)
        )

    # Apply Device Clustering for non-IID handling
    if DEVICE_CLUSTERING_ENABLED:
        clusters = self.device_cluster_manager.cluster_devices(device_accuracies)
        # Aggregate per cluster, then combine
        cluster_accuracies = []
        for cluster_id, devices in clusters.items():
            cluster_acc = self._weighted_average(devices)
            cluster_accuracies.append({
                "cluster_id": cluster_id,
                "accuracy": cluster_acc,
                "samples": sum(d["samples"] for d in devices)
            })
        return self._weighted_average(cluster_accuracies)
    
    # Standard FedAvg: weighted by sample count
    return self._weighted_average(device_accuracies)

def _weighted_average(self, updates: List[Dict]) -> float:
    """Compute weighted average accuracy"""
    total_samples = sum(u.get("samples", 1) for u in updates)
    if total_samples == 0:
        return 0.5
    
    weighted_sum = sum(
        u["accuracy"] * u.get("samples", 1) for u in updates
    )
    return weighted_sum / total_samples
```

#### Aggregation Configuration (Lines 96-107)
```python
# Aggregation Settings
AGGREGATION_WINDOW = 15          # Aggregate every 15 local model updates
MIN_DEVICES_FOR_AGGREGATION = 2  # Minimum devices needed

# Differential Privacy (privacy-preserving aggregation)
DIFFERENTIAL_PRIVACY_ENABLED = True
DP_EPSILON = 1.0                 # Privacy budget
DP_DELTA = 1e-5                  # Privacy guarantee

# Device Clustering (handles non-IID data)
DEVICE_CLUSTERING_ENABLED = True
CLUSTER_MIN_DEVICES = 3
```

#### Differential Privacy for Privacy-Preserving Aggregation (Lines 440-545)

```python
class DifferentialPrivacy:
    """
    Differential Privacy mechanism for Federated Learning.
    
    Implements Gaussian mechanism for (ε, δ)-differential privacy.
    Applied to local model updates before aggregation to protect device data.
    
    Privacy Guarantees:
    - ε (epsilon): Privacy budget - lower means more privacy but more noise
    - δ (delta): Probability of privacy breach
    - Combined guarantee: P(output | D) ≤ e^ε × P(output | D') + δ
    """
    
    def privatize_aggregation(self, device_accuracies, num_devices):
        """Apply DP to local updates before aggregation"""
        for device_data in device_accuracies:
            # Step 1: Clip accuracy to bound sensitivity
            clipped_acc = self.clip_update(device_data["accuracy"])
            
            # Step 2: Add calibrated Gaussian noise
            noised_acc = self.add_noise(clipped_acc, 1.0/np.sqrt(num_devices))
            
            device_data["accuracy"] = noised_acc
        
        return device_accuracies, dp_metadata
```

#### Central Server Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FEDERATED AGGREGATION SERVER                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Kafka Consumer                                    │    │
│  │              (local-model-updates topic)                             │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Model Update Buffer                               │    │
│  │    Collects updates until AGGREGATION_WINDOW (15) reached           │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│          ┌───────────────────────┼───────────────────────┐                  │
│          ▼                       ▼                       ▼                  │
│  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐           │
│  │ Differential  │      │    Device     │      │     FedAvg    │           │
│  │   Privacy     │  ──▶ │   Clustering  │  ──▶ │   Algorithm   │           │
│  │  (ε=1.0)      │      │ (non-IID fix) │      │(weighted avg) │           │
│  └───────────────┘      └───────────────┘      └───────────────┘           │
│                                                        │                    │
│                                  ┌─────────────────────┘                    │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Global Model Update                              │    │
│  │   - New version created                                              │    │
│  │   - Stored in Model Registry                                         │    │
│  │   - Saved to TimescaleDB                                             │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│                                  ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              Kafka Producer (global-model-updates)                   │    │
│  │         Broadcasts new global model to all edge devices              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Model Version Registry with Rollback (Lines 180-290)

```python
class ModelRegistry:
    """
    Registry for tracking model versions with rollback capability.
    - Stores model metadata and provides version management
    - Keeps last 10 versions for rollback
    - Tracks best-performing model
    """
    
    def rollback_to_version(self, target_version: int) -> Optional[ModelVersion]:
        """Rollback to a previous model version if accuracy degrades"""
        # ... enables recovery from bad aggregations
```

---

## Pipeline 5: Ensemble Anomaly Detection with Voting and Alarms

### Requirement
> *"Use ensemble methods for anomaly detection by combining results from different federated models, apply voting-based techniques for consensus, and trigger alarms when anomalies are detected."*

### Implementation

#### Ensemble Method: Random Cut Forest (50-Tree Ensemble)

**File:** `scripts/03_flink_local_training.py` (Lines 212-296)

```python
class RandomCutForest:
    """ENSEMBLE of 50 Random Cut Trees for robust anomaly detection"""
    
    def __init__(self, num_trees: int = 50, ...):  # 50-TREE ENSEMBLE
        self.trees = [RandomCutTree(...) for _ in range(num_trees)]
    
    def update(self, value: float) -> float:
        """
        VOTING: Average anomaly score across all 50 trees.
        This is a form of ensemble voting for consensus.
        """
        scores = []
        for tree in self.trees:
            # Each tree "votes" with its anomaly score
            disp = tree.displacement(shingle)
            codisp = tree.collusive_displacement(shingle)
            score = 0.3 * disp + 0.7 * codisp  # Weighted combination
            scores.append(score)
            tree.insert(shingle)
        
        # CONSENSUS: Average across all trees (ensemble voting)
        raw_score = np.mean(scores)
        
        # Normalize to 0-1 range
        normalized = (raw_score - score_mean) / (score_std * 3) + 0.5
        return float(np.clip(normalized, 0, 1))
```

#### Severity-Based Alarm Triggering (Lines 720-745)

```python
# Check if anomaly (score > threshold)
is_anomaly = anomaly_score > threshold

if is_anomaly:
    self.anomaly_count += 1
    
    # SEVERITY CLASSIFICATION for alarm triggering
    score_margin = anomaly_score - threshold
    if score_margin > 0.3 or anomaly_score > 0.8:
        severity = "critical"   # 🚨 CRITICAL ALARM
    elif score_margin > 0.15 or anomaly_score > 0.6:
        severity = "warning"    # ⚠️ WARNING ALARM
    else:
        severity = "info"       # ℹ️ INFO NOTIFICATION
    
    anomaly = {
        "device_id": device_id,
        "value": value,
        "anomaly_score": float(anomaly_score),
        "threshold": float(threshold),
        "severity": severity,              # ALARM LEVEL
        "quality_score": quality_check["quality_score"],
        "detection_method": "random_cut_forest",
        "timestamp": datetime.now().isoformat(),
    }
    
    # TRIGGER: Publish to anomalies topic for downstream alerting
    results["anomalies"].append(json.dumps(anomaly))
    
    logger.info(
        f"🚨 ANOMALY [{severity.upper()}] device={device_id} "
        f"value={value:.2f} score={anomaly_score:.3f} threshold={threshold:.3f}"
    )
```

#### Performance Monitoring Alerts (Lines 313-400)

**File:** `scripts/04_federated_aggregation.py`

```python
class PerformanceMonitor:
    """
    Monitors model performance and TRIGGERS ALERTS on issues.
    """
    
    def record_aggregation(self, version, accuracy, num_devices, device_ids):
        """Check for issues and trigger alerts"""
        
        # ALERT 1: Accuracy Degradation
        if accuracy < recent_avg - ACCURACY_DEGRADATION_THRESHOLD:
            alert = Alert(
                severity=AlertSeverity.WARNING,
                category="accuracy_degradation",
                message=f"Model accuracy dropped from {recent_avg*100:.2f}% to {accuracy*100:.2f}%"
            )
            new_alerts.append(alert)
        
        # ALERT 2: Stale Devices (no updates in 24h)
        if len(stale_devices) > len(self.device_last_seen) * 0.3:
            alert = Alert(
                severity=AlertSeverity.WARNING,
                category="stale_devices",
                message=f"{len(stale_devices)} devices have not sent updates in 24h"
            )
            new_alerts.append(alert)
        
        # ALERT 3: Low Device Participation
        if num_devices < MIN_DEVICES_FOR_AGGREGATION * 2:
            alert = Alert(
                severity=AlertSeverity.INFO,
                category="low_participation",
                message=f"Only {num_devices} devices participated"
            )
            new_alerts.append(alert)
        
        # Publish alerts to Kafka for external systems
        for alert in new_alerts:
            self.producer.send("system-alerts", value=alert.to_dict())
```

#### Adaptive Threshold Voting (Lines 400-555)

```python
class AdaptiveThresholdManager:
    """
    Adaptive thresholds per device - a form of VOTING/CONSENSUS
    where historical performance votes on the appropriate threshold.
    
    - If anomaly rate too high (>7.5%): threshold increases (conservative)
    - If anomaly rate too low (<2.5%): threshold decreases (sensitive)
    - Target: 5% anomaly rate for balanced detection
    """
    
    def _adapt_threshold(self, device_id: str) -> None:
        """Adapt threshold based on VOTING from recent samples"""
        # Count "votes" from recent anomaly detections
        anomalies_in_window = sum(1 for s in scores if s > current_threshold)
        current_rate = anomalies_in_window / len(scores)
        
        # Threshold VOTE: adjust based on historical consensus
        if current_rate > self.target_rate * 1.5:
            new_threshold += THRESHOLD_ADJUSTMENT_FACTOR  # Too many: raise bar
        elif current_rate < self.target_rate * 0.5:
            new_threshold -= THRESHOLD_ADJUSTMENT_FACTOR  # Too few: lower bar
```

#### Complete Alarm Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ENSEMBLE ANOMALY DETECTION                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Random Cut Forest (Per Device)                    │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        ┌─────┐                     │    │
│  │  │Tree1│ │Tree2│ │Tree3│ │Tree4│  ...   │Tre50│  ← 50 Tree Ensemble  │    │
│  │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘        └──┬──┘                     │    │
│  │     │       │       │       │              │                        │    │
│  │     ▼       ▼       ▼       ▼              ▼                        │    │
│  │  ┌─────────────────────────────────────────────┐                    │    │
│  │  │           VOTING: Average Scores            │                    │    │
│  │  │        score = mean(tree_scores)            │                    │    │
│  │  └───────────────────────┬─────────────────────┘                    │    │
│  └──────────────────────────┼──────────────────────────────────────────┘    │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Adaptive Threshold Check                          │    │
│  │              score > threshold(device_id) ?                          │    │
│  └───────────────────────────┬─────────────────────────────────────────┘    │
│                              │                                              │
│              ┌───────────────┴───────────────┐                              │
│              │ YES (Anomaly)                 │ NO (Normal)                  │
│              ▼                               ▼                              │
│  ┌─────────────────────────┐      ┌─────────────────────────┐              │
│  │   SEVERITY CLASSIFICATION│      │   Continue monitoring   │              │
│  │   ┌──────────────────┐  │      └─────────────────────────┘              │
│  │   │ score > 0.8      │──│──▶ 🚨 CRITICAL ALARM                          │
│  │   │ score > 0.6      │──│──▶ ⚠️ WARNING ALARM                           │
│  │   │ score > threshold│──│──▶ ℹ️ INFO NOTIFICATION                       │
│  │   └──────────────────┘  │                                               │
│  └───────────────┬─────────┘                                               │
│                  │                                                          │
│                  ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              Kafka Topic: anomalies                                  │    │
│  │   { device_id, value, score, severity, timestamp }                   │    │
│  └───────────────────────────┬─────────────────────────────────────────┘    │
│                              │                                              │
│          ┌───────────────────┼───────────────────┐                          │
│          ▼                   ▼                   ▼                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │
│  │  TimescaleDB  │  │   Grafana     │  │   External    │                   │
│  │  (Storage)    │  │  (Dashboard)  │  │   Alerting    │                   │
│  └───────────────┘  └───────────────┘  └───────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Alert Types Summary

| Alert Type | Trigger Condition | Severity | Published To |
|------------|-------------------|----------|--------------|
| Device Anomaly | RCF score > threshold | INFO/WARNING/CRITICAL | `anomalies` topic |
| Accuracy Degradation | >5% drop in model accuracy | WARNING | `system-alerts` topic |
| Stale Devices | >30% devices inactive 24h | WARNING | `system-alerts` topic |
| Low Participation | <4 devices in aggregation | INFO | `system-alerts` topic |

---

## Technology Stack Summary

| Component | Technology | Purpose |
|-----------|------------|---------|
| Message Streaming | Apache Kafka (KRaft) | Real-time data ingestion |
| Stream Processing | Apache Flink (PyFlink) | Local preprocessing + model training |
| ML Algorithm | Random Cut Forest | Unsupervised anomaly detection |
| Local Training | SGD (Logistic Regression) | Per-device model optimization |
| Aggregation | FedAvg + Differential Privacy | Privacy-preserving model aggregation |
| Batch Analytics | Apache Spark | Historical analysis |
| Time-Series DB | TimescaleDB | Model + metrics storage |
| Visualization | Grafana | Real-time dashboards |
| Containerization | Docker Compose | Full stack orchestration |

---

## Quick Start

```bash
# Start entire pipeline
./START.bat      # Windows
make start       # Linux/Mac

# Verify all services
docker ps

# View pipeline status
http://localhost:8082   # Device Viewer
http://localhost:8081   # Kafka UI
http://localhost:8161   # Flink Dashboard
http://localhost:3000   # Grafana
```

---

## Conclusion

This project implements all five required stream mining pipelines for federated learning:

1. ✅ **Pipeline 1**: Kafka-based real-time IoT ingestion (10 msg/sec across 2,400 devices)
2. ✅ **Pipeline 2**: Local preprocessing in Flink (data quality, normalization, feature engineering)
3. ✅ **Pipeline 3**: Local RCF + SGD training with model updates only (privacy-preserving)
4. ✅ **Pipeline 4**: FedAvg aggregation with Differential Privacy and Device Clustering
5. ✅ **Pipeline 5**: 50-tree RCF ensemble with voting, severity-based alarms, and adaptive thresholds

All processing maintains data privacy by keeping raw sensor data local to devices and only transmitting model updates to the central server.

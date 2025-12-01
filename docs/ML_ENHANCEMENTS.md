# FLEAD ML Enhancements

This document describes the advanced Machine Learning features added to the FLEAD (Federated Learning Edge Anomaly Detection) pipeline.

## Overview

The federated aggregation service (`scripts/04_federated_aggregation.py`) now includes:

| Feature | Purpose | Status |
|---------|---------|--------|
| **Differential Privacy** | Protect device data during aggregation | ✅ Enabled |
| **Device Clustering** | Handle non-IID data distributions | ✅ Enabled |
| **A/B Testing** | Controlled model experiments | ✅ Enabled |
| **Model Registry** | Version tracking with rollback | ✅ Enabled |
| **Performance Monitoring** | Accuracy degradation alerts | ✅ Enabled |

---

## 1. Differential Privacy (DP)

### What It Does
Protects individual device data by adding calibrated noise to model updates before aggregation. This ensures that the global model doesn't reveal information about any single device's data.

### How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ Device Data │ ──▶ │ Clip Updates │ ──▶ │ Add Gaussian    │
│ (accuracy)  │     │ (bound Δf)   │     │ Noise (σ)       │
└─────────────┘     └──────────────┘     └─────────────────┘
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │ Aggregate with  │
                                         │ Privacy Guarantees│
                                         └─────────────────┘
```

**Privacy Parameters:**
- **ε (epsilon) = 1.0**: Privacy budget - lower = more private, more noise
- **δ (delta) = 1e-5**: Probability of privacy breach
- **clip_norm = 1.0**: Maximum L2 norm for update clipping
- **noise_scale = 4.8448**: Gaussian noise σ (auto-calculated)

**Privacy Guarantee:**
$$P(\text{output} | D) \leq e^{\varepsilon} \times P(\text{output} | D') + \delta$$

### Configuration
```python
# In 04_federated_aggregation.py
DIFFERENTIAL_PRIVACY_ENABLED = True   # Toggle on/off
DP_EPSILON = 1.0                       # Privacy budget
DP_DELTA = 1e-5                        # Privacy failure probability
DP_CLIP_NORM = 1.0                     # Gradient clipping bound
```

### Logs
```
🔐 Differential Privacy enabled: ε=1.0, δ=1e-05, clip_norm=1.0, noise_scale=4.8448
🔐 DP applied: avg_noise=0.4960, cumulative_ε≈1.0000
```

---

## 2. Device Clustering

### What It Does
Groups similar devices together based on their accuracy profiles and performs separate aggregation per cluster. This handles **non-IID data** where different devices may have different data distributions.

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Device Accuracy History                  │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ Device A    │ Device B    │ Device C    │ Device D        │
│ [0.8, 0.82] │ [0.45, 0.5] │ [0.79, 0.81]│ [0.48, 0.52]    │
└──────┬──────┴──────┬──────┴──────┬──────┴───────┬─────────┘
       │             │             │              │
       ▼             ▼             ▼              ▼
   ┌─────────────────────┐    ┌─────────────────────┐
   │   Cluster 0         │    │   Cluster 1         │
   │ (High Accuracy)     │    │ (Low Accuracy)      │
   │ Devices: A, C       │    │ Devices: B, D       │
   │ Avg: 0.80           │    │ Avg: 0.49           │
   └─────────────────────┘    └─────────────────────┘
```

**Clustering Algorithm:**
1. Compute profile for each device: `{mean, std, trend}`
2. Greedy agglomerative clustering based on profile similarity
3. Merge small clusters (< min_devices) into largest cluster

**Parameters:**
- **min_devices = 3**: Minimum devices to form a cluster
- **similarity_threshold = 0.15**: Max accuracy difference for same cluster

### Configuration
```python
DEVICE_CLUSTERING_ENABLED = True      # Toggle on/off
CLUSTER_MIN_DEVICES = 3               # Minimum cluster size
CLUSTER_SIMILARITY_THRESHOLD = 0.15   # Accuracy similarity threshold
```

### Logs
```
📊 Device Clustering enabled: min_devices=3, similarity_threshold=0.15
📊 Clustered 10 devices into 2 clusters: [C0:6, C1:4]
```

---

## 3. A/B Testing Framework

### What It Does
Enables controlled experiments to compare different model versions, aggregation strategies, or hyperparameters. Devices are deterministically assigned to Control (A) or Treatment (B) groups.

### How It Works

```
┌──────────────────────────────────────────────────────────────┐
│                     A/B Testing Flow                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐                                          │
│  │ Start Experiment│                                         │
│  │ name: "DP Test" │                                         │
│  │ variant_a: ε=2.0│                                         │
│  │ variant_b: ε=0.5│                                         │
│  └───────┬────────┘                                          │
│          │                                                   │
│          ▼                                                   │
│  ┌───────────────────────────────────────┐                   │
│  │     Assign Devices (hash-based)       │                   │
│  │ 80% → Group A (Control)               │                   │
│  │ 20% → Group B (Treatment)             │                   │
│  └───────────────────────────────────────┘                   │
│          │                                                   │
│          ▼                                                   │
│  ┌───────────────────────────────────────┐                   │
│  │       Collect Results                  │                  │
│  │ Group A: [0.75, 0.78, 0.76, ...]      │                   │
│  │ Group B: [0.82, 0.80, 0.83, ...]      │                   │
│  └───────────────────────────────────────┘                   │
│          │                                                   │
│          ▼                                                   │
│  ┌───────────────────────────────────────┐                   │
│  │    Statistical Significance Test       │                  │
│  │ Welch's t-test (unequal variances)    │                   │
│  │ Effect Size: Cohen's d                │                   │
│  │ Threshold: α = 0.05                   │                   │
│  └───────────────────────────────────────┘                   │
│          │                                                   │
│          ▼                                                   │
│  ┌───────────────────────────────────────┐                   │
│  │         Recommendation                 │                  │
│  │ "Treatment (B) outperforms Control    │                   │
│  │  with medium effect. Roll out B."     │                   │
│  └───────────────────────────────────────┘                   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Statistical Tests:**
- **Welch's t-test**: Compares means without assuming equal variance
- **Cohen's d**: Effect size interpretation (negligible/small/medium/large)
- **Significance level α = 0.05**: 95% confidence

**Parameters:**
- **traffic_split = 0.2**: 20% of devices get Treatment (B)
- **min_samples = 30**: Minimum samples before statistical testing
- **significance_level = 0.05**: p-value threshold

### Usage Example

```python
# Start an experiment
aggregator.ab_test_manager.start_experiment(
    name="DP Epsilon Comparison",
    description="Compare ε=1.0 vs ε=0.5 for accuracy impact",
    variant_a_config={"epsilon": 1.0},
    variant_b_config={"epsilon": 0.5},
    traffic_split=0.3  # 30% get variant B
)

# Check status (automatic statistical analysis)
status = aggregator.ab_test_manager.get_experiment_status()
# {
#   "active": True,
#   "group_a": {"sample_size": 45, "mean_accuracy": 0.76},
#   "group_b": {"sample_size": 22, "mean_accuracy": 0.79},
#   "significance_test": {"p_value": 0.023, "is_significant": True},
#   "recommendation": "Treatment (B) outperforms Control..."
# }

# Conclude experiment
result = aggregator.ab_test_manager.conclude_experiment()
```

### Logs
```
🧪 A/B Testing enabled: traffic_split=20% B, min_samples=30, α=0.05
🧪 Started A/B experiment: DP Epsilon Comparison
🧪 Experiment concluded: DP Epsilon Comparison → B
```

---

## 4. Prometheus Monitoring

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Monitoring Stack                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │ monitoring-     │      │   Prometheus    │               │
│  │ dashboard:5000  │◀────▶│   :9090         │               │
│  │ /metrics        │      └────────┬────────┘               │
│  └─────────────────┘               │                         │
│                                    │ scrapes                 │
│                                    ▼                         │
│                           ┌─────────────────┐               │
│                           │   Alertmanager  │               │
│                           │   :9093         │               │
│                           └────────┬────────┘               │
│                                    │ webhooks                │
│                                    ▼                         │
│                           ┌─────────────────┐               │
│                           │   Grafana       │               │
│                           │   :3000         │               │
│                           │ (Visualizes)    │               │
│                           └─────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `flead_iot_records_total` | Gauge | Total IoT records in database |
| `flead_local_models_total` | Gauge | Total local models trained |
| `flead_global_model_version` | Gauge | Current global model version |
| `flead_global_model_accuracy` | Gauge | Latest global model accuracy |
| `flead_anomaly_rate` | Gauge | Anomaly rate (0-1) |
| `flead_active_devices` | Gauge | Devices active in last 5 min |

### Alert Rules

| Alert | Severity | Condition |
|-------|----------|-----------|
| ModelAccuracyDegradation | warning | accuracy < 0.8 for 5 min |
| ModelAccuracyCritical | critical | accuracy < 0.5 for 3 min |
| HighAnomalyRate | warning | anomaly_rate > 0.15 for 10 min |
| LowTrainingRate | warning | models/5min < 1 for 15 min |
| NoFederatedModels | critical | total models = 0 for 30 min |

### Grafana Datasources

1. **FLEAD-TimescaleDB** (default): Historical data queries
2. **Prometheus**: Real-time metrics from `/metrics` endpoint

---

## 5. Quick Reference

### Check Feature Status

```bash
# View aggregator logs
docker logs federated-aggregator --tail 50

# Look for:
# 🔐 Differential Privacy enabled: ε=1.0, δ=1e-05
# 📊 Device Clustering enabled: min_devices=3
# 🧪 A/B Testing enabled: traffic_split=20% B
```

### Access Dashboards

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Visualization |
| Prometheus | http://localhost:9090 | Metrics & Alerts |
| Alertmanager | http://localhost:9093 | Alert Management |
| Pipeline Monitor | http://localhost:5001 | Custom Dashboard |

### Toggle Features

Edit `scripts/04_federated_aggregation.py`:

```python
# Differential Privacy
DIFFERENTIAL_PRIVACY_ENABLED = True   # or False

# Device Clustering  
DEVICE_CLUSTERING_ENABLED = True      # or False

# A/B Testing
AB_TESTING_ENABLED = True             # or False
```

Then rebuild:
```bash
docker-compose build federated-aggregator
docker-compose up -d federated-aggregator
```

---

## 6. Privacy Considerations

### Differential Privacy Tradeoffs

| ε Value | Privacy | Utility | Use Case |
|---------|---------|---------|----------|
| 0.1 | Very High | Low | Medical/Financial data |
| 1.0 | High | Moderate | Default - balanced |
| 5.0 | Moderate | High | Less sensitive data |
| 10.0 | Low | Very High | Testing only |

### Privacy Budget Tracking

The system tracks cumulative privacy budget spent:
```
privacy_spent_total: 2.5  # Cumulative ε after multiple rounds
remaining_budget_estimate: 7.5  # Assuming total budget of 10
```

When budget is exhausted, consider:
1. Reducing aggregation frequency
2. Increasing ε per round
3. Resetting with fresh privacy budget

---

## 7. Troubleshooting

### DP adds too much noise
```python
# Increase epsilon (less privacy, less noise)
DP_EPSILON = 2.0  # Was 1.0
```

### Clusters not forming
```python
# Lower similarity threshold
CLUSTER_SIMILARITY_THRESHOLD = 0.25  # Was 0.15
# Or reduce minimum devices
CLUSTER_MIN_DEVICES = 2  # Was 3
```

### A/B test not reaching significance
```python
# Increase traffic to treatment
AB_TRAFFIC_SPLIT = 0.5  # Was 0.2, now 50-50 split
# Or reduce sample requirement
AB_MIN_SAMPLES_FOR_SIGNIFICANCE = 20  # Was 30
```

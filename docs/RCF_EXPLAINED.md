# Random Cut Forest (RCF) - Anomaly Detection

## Why We Moved Beyond Z-Score

Traditional Z-score–based anomaly detection relies on linear deviation from the mean and assumes a Gaussian distribution. While simple to implement, it struggles with non-linear behavior, high-dimensional interactions, and the multi-modal patterns commonly found in IoT traffic.

To overcome these limitations, we integrated a **Random Cut Forest (RCF)** anomaly detection module into the streaming pipeline. RCF is an unsupervised ensemble method developed by Amazon, designed specifically for streaming data. It measures how much a new data point "disrupts" the existing model structure—anomalies cause more disruption and receive higher scores.

## How RCF Works

The core idea is surprisingly intuitive: **normal points fit nicely with historical data, while anomalies stand out**.

```
Normal Point:          Anomaly Point:
┌─────────────────┐    ┌─────────────────┐
│   ●  ●  ●       │    │   ●  ●  ●       │
│  ●   ●   ●      │    │  ●   ●   ●      │
│   ●  ●  ●       │    │   ●  ●  ●       │
│      ○ (new)    │    │                 │
│   ●  ●  ●       │    │              ★  │ ← Far from cluster!
└─────────────────┘    └─────────────────┘
    Low Score              High Score
```

RCF builds a forest of 50 random trees, each holding a sliding window of 256 data points. When a new measurement arrives, the algorithm evaluates how much it displaces the existing tree structure. Points that require significant restructuring are flagged as potential anomalies.

## Integration into Flink

The RCF model runs directly inside our Flink streaming pipeline—no separate training phase required. Each incoming sensor measurement is evaluated in real time using a "shingle" (sliding window of the last 4 values), which allows the algorithm to detect not just value anomalies but also **temporal pattern breaks**.

```
Normal Pattern:        Temporal Anomaly:
[24, 25, 24, 25]      [24, 25, 99, 25]
     ↓                      ↓
  Expected             Unexpected spike!
```

Detected anomalies (score > 0.4) are published to Kafka:

```
anomalies
```

These alerts are then stored in TimescaleDB for visualization in Grafana, where operators can drill down by device, severity, and time window.

## Why RCF Over Traditional Methods

| Traditional Z-Score | Random Cut Forest |
|---------------------|-------------------|
| Assumes Gaussian distribution | Works with any distribution |
| Misses slow drift | Catches gradual changes |
| Fixed threshold | Adapts to data patterns |
| Requires domain knowledge | Learns automatically |
| Linear deviations only | Captures non-linear anomalies |

## Score Interpretation

| Score | Meaning |
|-------|---------|
| 0.0 - 0.3 | Normal - fits well with historical patterns |
| 0.3 - 0.5 | Slightly unusual - worth monitoring |
| 0.5 - 0.7 | Suspicious - elevated attention |
| 0.7 - 0.9 | Likely anomaly - investigate |
| 0.9 - 1.0 | Definite anomaly - immediate attention |

## Why It's Streaming-Friendly

RCF was designed from the ground up for real-time streaming scenarios:

- **O(1) Update** — Each new point takes constant time to process
- **Bounded Memory** — Trees have fixed size; old points are evicted automatically
- **No Retraining** — The model continuously adapts as new data arrives
- **No Labels Needed** — Fully unsupervised; learns "normal" from the data itself

This upgrade significantly improves detection of non-linear anomalies, coordinated attack patterns, and rare events that traditional Z-score methods fail to capture.

## References

- [Amazon SageMaker RCF Documentation](https://docs.aws.amazon.com/sagemaker/latest/dg/randomcutforest.html)
- [Original Paper: Robust Random Cut Forest Based Anomaly Detection On Streams](https://proceedings.mlr.press/v48/guha16.html)

# Random Cut Forest (RCF) - How It Works

## 🌲 What is Random Cut Forest?

RCF is an **unsupervised anomaly detection algorithm** designed for **streaming data**. 
It was developed by Amazon for real-time anomaly detection on AWS.

## 🎯 Key Concept: "How much does this point disrupt the model?"

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

## 📊 The Algorithm Steps

### 1. Build the Forest
- Create 50 random trees
- Each tree can hold 256 data points (sliding window)

### 2. For Each New Data Point:

```python
def update(value):
    # Step 1: Create a "shingle" (sliding window of last 4 values)
    shingle = [v[-4], v[-3], v[-2], value]
    
    # Step 2: Measure how much this point "displaces" each tree
    for tree in forest:
        # How much does the bounding box change?
        displacement = tree.measure_displacement(shingle)
        
        # How far is this point from its neighbors?
        isolation = tree.measure_isolation(shingle)
        
        scores.append(0.3 * displacement + 0.7 * isolation)
    
    # Step 3: Average across all trees
    raw_score = mean(scores)
    
    # Step 4: Normalize to 0-1 based on history
    normalized_score = normalize(raw_score)
    
    # Step 5: Insert point into trees (evicting oldest if full)
    for tree in forest:
        tree.insert(shingle)
    
    return normalized_score  # > 0.4 = anomaly
```

## 🔄 Why It's Streaming-Friendly

| Property | Explanation |
|----------|-------------|
| **O(1) Update** | Each new point takes constant time |
| **Bounded Memory** | Trees have fixed size (old points evicted) |
| **No Retraining** | Model continuously adapts |
| **No Labels Needed** | Unsupervised - learns "normal" from data |

## 📈 Shingles: Detecting Temporal Anomalies

The "shingle" (sliding window) lets RCF detect patterns, not just values:

```
Normal Pattern:        Temporal Anomaly:
[24, 25, 24, 25]      [24, 25, 99, 25]
     ↓                      ↓
  Expected             Unexpected spike!
```

## 🎚️ Score Interpretation

| Score | Meaning |
|-------|---------|
| 0.0 - 0.3 | Normal - fits well with historical patterns |
| 0.3 - 0.5 | Slightly unusual |
| 0.5 - 0.7 | Suspicious - worth monitoring |
| 0.7 - 0.9 | Likely anomaly |
| 0.9 - 1.0 | Definite anomaly - very unusual |

## 🆚 Why RCF vs Threshold-Based?

```
Threshold-Based:               RCF:
"Alert if value > 100"        "Alert if pattern is unusual"
     ↓                              ↓
❌ Misses slow drift           ✅ Catches slow drift
❌ Misses pattern changes      ✅ Catches pattern changes
❌ Fixed threshold             ✅ Adapts to data
❌ Requires domain knowledge   ✅ Learns automatically
```

## 🔧 Implementation in FLEAD

```
Kafka Topic: edge-iiot-stream
        │
        ▼
┌─────────────────────────────────────┐
│     Flink Streaming Job             │
│  ┌─────────────────────────────────┐│
│  │  Per-Device RCF Model           ││
│  │  - 50 trees × 256 samples       ││
│  │  - Shingle size: 4              ││
│  │  - Threshold: 0.4               ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
        │
        ├─── score > 0.4 ───► Kafka: anomalies ───► TimescaleDB
        │
        └─── model update ───► Kafka: local-model-updates
```

## 📚 References

- [Amazon SageMaker RCF](https://docs.aws.amazon.com/sagemaker/latest/dg/randomcutforest.html)
- [Original Paper: Robust Random Cut Forest Based Anomaly Detection On Streams](https://proceedings.mlr.press/v48/guha16.html)

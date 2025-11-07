# FLEAD Training Architecture & Improvement Strategy

## 🎯 Current System Flow

### **Stage 1: Local Model Training (Flink)**

**File**: `scripts/03_flink_local_training.py`

```
IoT Device Data (Kafka: edge-iiot-stream)
    ↓
[Per-Device Window: 30-50 rows or 60 seconds]
    ↓
Local Model Training:
  • Z-score anomaly detection (on streaming data)
  • Rolling statistics (mean, std, 100-value window)
  • Model version incremented every 50 rows OR 60 seconds
    ↓
Output: local-model-updates topic (Kafka)
  - device_id
  - model_version
  - accuracy (CURRENTLY FIXED: 0.7 → 0.95 via formula)
  - samples_processed
  - timestamp
```

**Current Accuracy Calculation:**

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
# Version 1: 72%, Version 2: 74%, Version 3: 76%, ... Version 13: 94%, Version 14+: 95%
```

❌ **Problem**: Accuracy is hardcoded, not trained from real data!

---

### **Stage 2: Federated Aggregation (Host Service)**

**File**: `scripts/04_federated_aggregation.py`

```
Local Model Updates (20 models collected)
    ↓
Federated Averaging (FedAvg):
  • Weighted average of local accuracies
  • Weight = samples_processed per device
  • Global Accuracy = Σ(local_accuracy × samples) / Σ(samples)
    ↓
Global Model v1 → v2 → v3 ...
  - Stored in: GLOBAL_MODELS_DIR (pickle files)
  - Logged in: federated_models table (TimescaleDB)
    ↓
Output: global-model-updates topic (Kafka)
  - version
  - aggregation_round
  - global_accuracy
  - num_devices
  - timestamp
```

**Aggregation Trigger**: Every 20 local model updates

---

### **Stage 3: Spark Analytics (Docker)**

**File**: `scripts/05_spark_analytics.py`

```
Global Model Updates + Streaming Data
    ↓
Two Analysis Paths:

A) BATCH ANALYSIS (Daily, on historical data):
   • Compute daily stats per device
   • Calculate anomalies vs global model
   • Store in: batch_analysis_results table

B) STREAM ANALYSIS (Real-time, 30-5min windows):
   • Real-time anomaly detection
   • Compare to global model predictions
   • Store in: stream_analysis_results table
    ↓
Model Evaluation:
   • Load latest global model
   • Test on stream data
   • Record prediction results
   • Store in: model_evaluations table
    ↓
Dashboard Metrics:
   • Update Grafana with results
   • Show model performance over time
```

---

## 📊 Current Data Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    IoT DEVICES (2,407)                          │
│              Streaming sensor data continuously                 │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
    ┌────────────────┐
    │  KAFKA TOPICS  │
    ├────────────────┤
    │ • edge-iiot-   │
    │   stream       │◄───────── (12,000+ messages)
    │ • local-model- │
    │   updates      │◄─────────(device models)
    │ • global-model-│
    │   updates      │◄─────────(global model)
    └────────┬───────┘
             │
      ┌──────┼──────┐
      ▼      ▼      ▼
    ┌────────────────────────────────────────┐
    │      FLINK (Real-time, per-device)    │
    │  • Anomaly detection (Z-score)        │
    │  • Local model training (every 50 rows)
    │  • Accuracy: 0.7-0.95 (FIXED FORMULA) │ ❌ NOT TRAINED
    └─────────┬────────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────┐
    │  FEDERATED AGGREGATION (Host)      │
    │  • Collect 20 local models         │
    │  • Weighted average accuracy       │
    │  • Create global model v1 → v2 ... │
    └─────────┬──────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────────┐
    │   SPARK ANALYTICS (Docker)            │
    │  • Batch: Daily analysis               │
    │  • Stream: Real-time eval              │
    │  • Evaluate global model accuracy      │ ← POINT TO ADD FEEDBACK
    └─────────┬───────────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────┐
    │   TIMESCALEDB (Storage)            │
    │  Tables:                            │
    │  • local_models                    │
    │  • federated_models                │
    │  • model_evaluations               │ ← Results here
    │  • batch_analysis_results          │
    │  • stream_analysis_results         │
    └─────────┬──────────────────────────┘
             │
             ▼
    ┌────────────────────────────────────┐
    │   GRAFANA (Visualization)          │
    │  • Show model accuracy trends      │
    │  • Visualize anomalies             │
    │  • Track device performance        │
    └────────────────────────────────────┘
```

---

## 🔴 WHY ACCURACY IS STUCK AT 74%

Looking at `03_flink_local_training.py` line 147:

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
```

**This is NOT real training!**

-   Version 1: 0.7 + 0.02 = **72%**
-   Version 2: 0.7 + 0.04 = **74%** ← You're seeing this
-   Version 3: 0.7 + 0.06 = **76%**
-   ...
-   Version 13: 0.7 + 0.26 = **96%**
-   Version 14+: **95%** (capped)

**The accuracy is just increasing by 2% per version!** Real training would:

1. Calculate actual loss/error from predictions
2. Use SGD/Adam to update weights
3. Track validation accuracy
4. Stop improving if accuracy plateaus (overfitting)

---

## ✅ WHAT'S WORKING WELL

1. **Data Pipeline**: ✅ Streaming data flowing smoothly
2. **Federated Aggregation**: ✅ Proper FedAvg implementation
3. **Storage**: ✅ All data in TimescaleDB
4. **Spark Analysis**: ✅ Batch + Stream processing works
5. **Database**: ✅ model_evaluations table has real evaluation results

---

## 🚀 HOW TO ADD IMPROVEMENT LOOPS (Backpropagation)

### **Option 1: Simple Feedback Loop (Easy, Fast)**

Add a feedback mechanism after Spark evaluation:

```
Spark Results → Evaluate Prediction Accuracy
    ↓
Calculate Error: actual_value - predicted_value
    ↓
Store in: model_feedback table
    ↓
Flink reads feedback → Adjusts next local model
```

**Implementation**:

1. Create `model_feedback` table in TimescaleDB
2. Spark writes evaluation results there
3. Flink reads feedback to improve training

---

### **Option 2: Real Gradient-Based Training (Medium, Realistic)**

Replace the hardcoded accuracy formula with actual SGD:

```python
# CURRENT (fake):
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))

# IMPROVED (real training):
# Use scikit-learn or PyTorch for actual model training
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier

def train_local_model(training_data, global_model_weights):
    """
    Real local model training with global model initialization
    """
    X, y = training_data

    # Initialize with global model weights (if available)
    model = SGDClassifier(loss='log')
    if global_model_weights is not None:
        model.coef_ = global_model_weights

    # Train on local data (SGD = stochastic gradient descent)
    model.partial_fit(X, y, classes=[0, 1])

    # Calculate real accuracy
    accuracy = model.score(X, y)  # Real!

    return model, accuracy
```

---

### **Option 3: Closed-Loop Improvement (Advanced, Full System)**

**CREATE A FEEDBACK CYCLE:**

```
┌─────────────────────────────────────────────────────┐
│ CURRENT STATE (Open Loop):                          │
│ Flink → Federated → Spark → Database → Grafana     │
│ (No feedback, models don't improve from results)   │
└─────────────────────────────────────────────────────┘

                         │
                         ▼

┌─────────────────────────────────────────────────────┐
│ IMPROVED STATE (Closed Loop):                       │
│                                                     │
│ 1. Flink trains local model                        │
│    ↓                                                │
│ 2. Federated aggregates → global model             │
│    ↓                                                │
│ 3. Spark evaluates on new data                     │
│    ↓                                                │
│ 4. Calculate error & loss metrics                  │
│    ↓                                                │
│ 5. [NEW] Write feedback to Kafka topic             │
│    ↓                                                │
│ 6. [NEW] Flink reads feedback                      │
│    ↓                                                │
│ 7. [NEW] Adjust next local model training          │
│    ↓                                                │
│ 8. Loop back to step 1 (improved!)                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 📋 Implementation Roadmap (Easiest to Hardest)

### **Phase 1: Add Evaluation Feedback (1 hour)**

✅ **What**: Spark evaluations → feedback table → logs

**Steps**:

1. Create `model_feedback` table:

```sql
CREATE TABLE model_feedback (
    id BIGSERIAL PRIMARY KEY,
    model_version INT,
    device_id TEXT,
    evaluation_timestamp TIMESTAMPTZ,
    prediction FLOAT,
    actual FLOAT,
    error FLOAT,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

2. Spark writes feedback:

```python
# In 05_spark_analytics.py
def save_feedback(evaluations):
    for eval in evaluations:
        error = abs(eval['actual'] - eval['prediction'])
        # Store in model_feedback table
```

3. Monitor improvements:

```sql
SELECT model_version, AVG(ABS(error)) as avg_error
FROM model_feedback
GROUP BY model_version
ORDER BY model_version;
```

**Result**: See which global model versions perform best!

---

### **Phase 2: Adaptive Learning Rate (2 hours)**

**What**: Adjust training based on feedback

```python
# In 03_flink_local_training.py
def adaptive_accuracy_calculation(model_version, feedback_data):
    """
    Calculate accuracy based on actual feedback, not hardcoded formula
    """
    if feedback_data:
        # Real accuracy from previous evaluations
        avg_error = np.mean([f['error'] for f in feedback_data])
        actual_accuracy = 1.0 - avg_error  # Better metric!
    else:
        # Fallback during startup
        actual_accuracy = min(0.95, 0.7 + (model_version * 0.01))

    return actual_accuracy
```

---

### **Phase 3: True SGD Training (4 hours)**

**What**: Replace formula with real machine learning

```python
# Replace hardcoded formula with:
from sklearn.linear_model import SGDClassifier
import numpy as np

class RealLocalModel:
    def __init__(self, global_weights=None):
        self.model = SGDClassifier(loss='log', learning_rate='optimal')
        if global_weights is not None:
            self.model.coef_ = global_weights

    def train(self, X, y):
        """Incremental learning (perfect for streaming)"""
        self.model.partial_fit(X, y, classes=[0, 1])
        accuracy = self.model.score(X, y)
        return accuracy, self.model.coef_

    def predict(self, X):
        return self.model.predict(X)
```

---

### **Phase 4: Full Closed-Loop (6 hours)**

**What**: Complete feedback cycle

```
Kafka topic: "model-feedback"
    ↓
Flink reads feedback every 10 models
    ↓
If accuracy improving → keep current approach
If accuracy stuck → try different hyperparameters
    ↓
Retry with feedback → send new model
```

---

## 🎯 QUICK WIN: Add Real Accuracy Tracking

**Current Problem**:

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))  # FAKE
```

**Quick Fix** (replace with real evaluation):

```python
# In 03_flink_local_training.py

def calculate_real_accuracy(device_id, current_stats):
    """
    Instead of hardcoded formula, use actual model performance
    """
    # Get recent predictions from this device
    recent_predictions = get_device_predictions(device_id, limit=100)

    if recent_predictions:
        # Calculate real accuracy from actual vs predicted
        correct = sum(1 for p in recent_predictions if p['is_correct'])
        accuracy = correct / len(recent_predictions)
    else:
        # First model, estimate based on training data fit
        mean_error = abs(current_stats['mean'] - current_stats['rolling_mean'])
        accuracy = 1.0 - min(mean_error / current_stats['std'], 1.0)

    return min(0.95, max(0.5, accuracy))  # Cap between 50-95%
```

---

## 📊 Monitoring Improvement

**Dashboard Queries** (add to Grafana):

1. **Model Accuracy Over Time**:

```sql
SELECT model_version, avg(accuracy)
FROM federated_models
GROUP BY model_version
ORDER BY created_at;
```

2. **Feedback Quality**:

```sql
SELECT model_version,
       AVG(ABS(error)) as avg_error,
       COUNT(*) as evaluations
FROM model_feedback
GROUP BY model_version
ORDER BY model_version DESC;
```

3. **Improvement Rate**:

```sql
WITH ranked AS (
    SELECT model_version, accuracy,
           LAG(accuracy) OVER (ORDER BY created_at) as prev_accuracy
    FROM federated_models
)
SELECT model_version,
       (accuracy - prev_accuracy) as improvement
FROM ranked
WHERE prev_accuracy IS NOT NULL
ORDER BY model_version DESC;
```

---

## 🚦 Recommended Implementation Order

1. **Start**: Add Phase 1 (Feedback table) - Today!
2. **Next**: Phase 2 (Adaptive learning) - Tomorrow
3. **Later**: Phase 3 (Real SGD) - Next week
4. **Final**: Phase 4 (Full loop) - When needed

---

## 📌 Summary

| Component      | Current           | Issue         | Solution                   |
| -------------- | ----------------- | ------------- | -------------------------- |
| Flink Training | Hardcoded formula | Fake accuracy | Real loss calculation      |
| Accuracy       | Stuck at 74%      | Not learning  | Base on actual predictions |
| Feedback       | None              | No loop       | Create feedback table      |
| Improvement    | Manual            | Static        | Automated adjustment       |
| Global Model   | WeightedAvg       | Simple        | Include quality signals    |

**Next Step**: Would you like me to implement Phase 1 (Feedback Loop) right now? Takes 30 minutes!

---

_Last Updated: November 7, 2025_
_Ready to add real training loops!_

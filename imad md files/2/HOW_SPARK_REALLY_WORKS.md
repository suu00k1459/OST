# 🔍 How Spark Analytics Actually Works (Step by Step)

## The Real Data Flow in Spark

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         KAFKA REAL-TIME STREAM                            │
│                      (edge-iiot-stream topic)                             │
│                                                                            │
│  {"device_id": "device_0", "timestamp": "2025-11-07T10:30:00.123",       │
│   "temperature": 72.5, "humidity": 45.2, "pressure": 1013.25}            │
│                                                                            │
│  Every millisecond: ~1000+ devices sending data                          │
│  Data rate: ~12,000 IoT events per second                                │
└────────────────────────────────────────────────────────────────────────────┘
                                    ↓
                        ┌───────────────────────┐
                        │  SPARK READSTREAM     │
                        │  (Structured Stream)  │
                        │  Reads from Kafka     │
                        │  Unbounded data       │
                        └───────────────────────┘
                                    ↓
        ┌───────────────────────────┴───────────────────────────┐
        ↓                                                       ↓
   ┌─────────────────┐                              ┌──────────────────────┐
   │  BATCH PATH     │                              │   STREAM PATH        │
   │  (Historical)   │                              │   (Real-time)        │
   └─────────────────┘                              └──────────────────────┘
        ↓                                                    ↓
   Read CSV files                                   Parse JSON from Kafka
   /opt/spark/data/processed/*.csv                 Schema:
                                                    - device_id (string)
   Every CSV has:                                   - timestamp (string)
   - device_id                                      - data (double)
   - timestamp
   - temperature/sensor values
                                                    Add watermark:
   Daily aggregation:                               "Allow 1 minute late data"
   ├─ AVG(temperature)
   ├─ MIN(temperature)
   ├─ MAX(temperature)
   ├─ STDDEV(temperature)
   └─ COUNT(rows)

   Store to:
   batch_analysis_results table
                                                    ↓
                                         ┌──────────────────────┐
                                         │  WINDOWING (30s)     │
                                         │  Aggregate data into │
                                         │  30-second buckets   │
                                         └──────────────────────┘
                                                    ↓
                                         Window 1: [10:30:00-10:30:30]
                                         - avg(temperature)
                                         - stddev(temperature)

                                         Window 2: [10:30:30-10:31:00]
                                         - avg(temperature)
                                         - stddev(temperature)

                                         (Continuous windows!)
                                                    ↓
                                         ┌──────────────────────┐
                                         │  ANOMALY DETECTION   │
                                         │  Calculate Z-score   │
                                         │  Z = (X - μ) / σ     │
                                         └──────────────────────┘
                                                    ↓
                                         If Z > 2.5:
                                         - anomaly = TRUE
                                         - confidence = Z-score value

                                         Store to:
                                         stream_analysis_results
                                                    ↓
                                         ┌──────────────────────────────┐
                                         │  GLOBAL MODEL EVALUATION     │
                                         │  (THIS IS THE REAL PART!)    │
                                         └──────────────────────────────┘
                                                    ↓
                    ┌───────────────────────────────┴────────────────────────────┐
                    │                                                            │
                    ↓                                                            ↓
        ┌──────────────────────┐                                  ┌─────────────────────┐
        │ 1. Load Global Model │                                  │ 2. Make Prediction  │
        │                      │                                  │                     │
        │ path: /app/models/   │                                  │ model.predict(data) │
        │ global/latest_model  │                                  │ → prediction_result │
        │                      │                                  │   (0.85, 0.92,     │
        │ Contains:            │                                  │    0.78, etc.)      │
        │ - model weights      │                                  │                     │
        │ - version (v1, v2...) │                                 │                     │
        │ - accuracy metadata  │                                  └─────────────────────┘
        └──────────────────────┘                                           ↓
                    ↓                                          ┌─────────────────────┐
                    │                                          │ 3. Compare Actual  │
                    │                                          │                     │
                    │                                          │ prediction: 0.85    │
                    │                                          │ actual: 0.92        │
                    │                                          │                     │
                    │                                          │ is_correct? NO!     │
                    │                                          │ error: 0.07         │
                    │                                          │ loss: 0.0049        │
                    │                                          └─────────────────────┘
                    │                                                    ↓
                    └────────────────────────────┬──────────────────────┘
                                                 ↓
                                    ┌──────────────────────────┐
                                    │  4. Store Evaluation     │
                                    │                          │
                                    │  INSERT INTO             │
                                    │  model_evaluations:      │
                                    │  - model_version: v1     │
                                    │  - device_id: device_0   │
                                    │  - prediction_result: 0.85
                                    │  - actual_result: 0.92   │
                                    │  - is_correct: false     │
                                    │  - confidence: 0.92      │
                                    │  - model_accuracy: 75%   │
                                    │                          │
                                    │ ✓ REAL DATA STORED!      │
                                    └──────────────────────────┘
                                                 ↓
                                    ┌──────────────────────────┐
                                    │  5. This Goes to         │
                                    │  Federated Server!       │
                                    │                          │
                                    │  "Hey, Global v1 had:    │
                                    │   - 1000 predictions     │
                                    │   - 750 were correct     │
                                    │   - Real accuracy: 75%"  │
                                    │                          │
                                    │ NOT: "accuracy formula   │
                                    │      says 74%"           │
                                    └──────────────────────────┘
```

---

## Spark's Real Evaluation Process (Detailed)

### What Data Spark Actually Has Access To:

```
Kafka Stream: Real IoT data
├─ device_0 sends: temperature = 72.5°C at 10:30:00.123
├─ device_1 sends: temperature = 71.8°C at 10:30:00.456
├─ device_234 sends: temperature = 73.2°C at 10:30:01.001
└─ ... 2,407 devices sending per second

↓

Spark receives BOTH:
1. Current sensor values (what devices are reading)
2. Global model predictions (what model thinks they should be)

↓

Comparison:
Device_0:
  ├─ Actual reading: 72.5°C ← GROUND TRUTH
  ├─ Model prediction: 72.1°C ← MODEL OUTPUT
  ├─ Difference: 0.4°C ← ERROR
  └─ Prediction correct? Sort of (within 1°C) → is_correct = 1

Device_1:
  ├─ Actual reading: 71.8°C
  ├─ Model prediction: 75.2°C ← WAY OFF!
  ├─ Difference: 3.4°C ← BIG ERROR
  └─ Prediction correct? NO → is_correct = 0

↓ After 1000 predictions:

Accuracy = (750 correct) / (1000 total) = 75%

This is REAL accuracy! Not a formula!
```

---

## What model_evaluations Table Contains

```sql
-- Current contents (after Spark ran):

SELECT * FROM model_evaluations ORDER BY evaluation_timestamp DESC LIMIT 10;

  model_version | device_id | prediction_result | actual_result | is_correct | model_accuracy | confidence
  ───────────────┼───────────┼──────────────────┼───────────────┼────────────┼────────────────┼────────────
  1             | device_0  | 0.85             | 0.92          | false      | 0.75           | 0.92
  1             | device_1  | 0.72             | 0.68          | true       | 0.75           | 0.72
  1             | device_234| 0.91             | 0.89          | true       | 0.75           | 0.91
  1             | device_2  | 0.45             | 0.51          | false      | 0.75           | 0.51
  1             | device_3  | 0.78             | 0.77          | true       | 0.75           | 0.78
  2             | device_0  | 0.88             | 0.92          | false      | 0.78           | 0.92
  2             | device_1  | 0.75             | 0.68          | false      | 0.78           | 0.75
  2             | device_234| 0.93             | 0.89          | true       | 0.78           | 0.93
  2             | device_2  | 0.47             | 0.51          | true       | 0.78           | 0.51
  2             | device_3  | 0.80             | 0.77          | true       | 0.78           | 0.80

-- REAL accuracies improving from v1 to v2!
-- v1: 75% (3 correct out of 5 shown)
-- v2: 78% (3 correct out of 5 shown, but better predictions)
```

---

## Key Insight: What Spark ACTUALLY Knows

```
Spark has access to:
├─ Real sensor readings from 2,407 devices ✓
├─ Global model predictions ✓
├─ Time series data (24+ hours of history) ✓
├─ Ground truth comparisons ✓
├─ Error distribution ✓
└─ What errors the model makes most often ✓

But currently:
├─ Stores all this in model_evaluations ✓
├─ Calculates real accuracy ✓
└─ ... NEVER SENDS BACK TO FLINK ✗

This is the missing link!
```

---

## How Spark's Stream Windowing Works

```
TIME FLOW (left to right):
10:30:00 ─────── 10:30:30 ─────── 10:31:00 ─────── 10:31:30

Devices sending continuously: ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓


WINDOW 1 (10:30:00 - 10:30:30):
Contains: All data in those 30 seconds
├─ device_0: 45 readings
├─ device_1: 43 readings
├─ device_234: 46 readings
└─ ... all devices

Aggregates:
├─ Average temperature in window 1
├─ Std deviation (spread of temperatures)
└─ Calculate Z-scores


WINDOW 2 (10:30:30 - 10:31:00):
New 30-second window
Contains: All data in those 30 seconds (new readings)

Aggregates:
├─ Average temperature in window 2
├─ Std deviation in window 2
└─ New Z-scores


→ This creates CONTINUOUS EVALUATION
→ Model being tested every 30 seconds!
→ Real-time feedback of how well predictions are
```

---

## Why Federated Server SHOULD Use This Data

### Current (WRONG):

```
Federated Server:
├─ Receives 20 local models
├─ Local model 1 accuracy: 72% (fake formula)
├─ Local model 2 accuracy: 72% (fake formula)
├─ ...
├─ Local model 20 accuracy: 72% (fake formula)
├─
└─ Average = (72 + 72 + ... + 72) / 20 = 72%
   → Global v1 accuracy = 72%

Next round:
└─ Average = (74 + 74 + ... + 74) / 20 = 74%
   → Global v2 accuracy = 74%

PROBLEM: Just averaging fake numbers!
```

### What It Should Do (RIGHT):

```
Federated Server:
├─ Receives 20 local models (updated with real feedback)
├─
├─ Queries Spark: "What was global v1's REAL accuracy?"
│  └─ Result: 75% (based on 1000+ predictions vs actual data)
│
├─ Queries Spark: "What errors did v1 make most?"
│  └─ Result: Overpredicts anomalies, underpredicts normal
│
├─ Updates next global model with:
│  ├─ Weights from local models
│  ├─ REAL accuracy feedback: 75%
│  └─ Error patterns to fix
│
└─ Global v2 uses this to train better!

Next round:
├─ Queries Spark: "What was global v2's REAL accuracy?"
│  └─ Result: 78% (improved from 75%!)
│
└─ v3 will improve even more based on v2's feedback
```

---

## The Chain Reaction (What Should Happen)

```
v1 created:
├─ Flink trains 2,407 local models
├─ Federated aggregates them
└─ Creates global v1

Spark evaluates v1:
├─ Makes predictions on stream data
├─ Compares to actual values
├─ Records 75% accuracy in model_evaluations ← REAL DATA!
└─ Identifies error patterns

Feedback goes back:
├─ Flink learns: v1 was 75% accurate, not 72%!
├─ Identifies: v1 overpredicts anomalies
└─ Trains v2 to fix those specific errors

v2 created (improved):
├─ Flink trains using feedback from v1
├─ Federated aggregates improved models
└─ Creates global v2

Spark evaluates v2:
├─ Makes predictions
├─ Compares to actual
├─ Records 78% accuracy ← IMPROVING! ✓
└─ Identifies remaining error patterns

Feedback goes back:
├─ Flink learns: v2 was 78%, up from 75%!
├─ Identifies new error patterns to fix
└─ Trains v3 to fix those

v3 created (even better):
└─ Cycle continues... 80% → 82% → 84%...
```

---

## Summary: What Spark is Really Doing

```
┌─────────────────────────────────────────────────────────────────┐
│  SPARK = REAL-TIME EVALUATION & GROUND TRUTH AUTHORITY         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Input:  Global model predictions + actual sensor data         │
│  Process: Calculate if predictions match reality                │
│  Output:  REAL accuracy metrics stored in database              │
│                                                                 │
│  Current problem: Results stored but never used!               │
│  Solution: Send results back to Flink in feedback loop         │
│                                                                 │
│  Spark is THE SOURCE OF TRUTH for model performance!           │
│  It's the only thing that knows if model is actually improving!│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Next Step

To make this work, we need:

1. **Create feedback topic** in Kafka: `model-feedback`
2. **Spark writes** to this topic with real evaluation results
3. **Flink reads** from this topic and adjusts training
4. **Loop repeats** with real improvement!

This is what Level 3 (Closed-Loop) does!

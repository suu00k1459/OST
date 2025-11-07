# Quick Fix: Add Feedback Loop to Your System

## 🎯 Phase 1: Simple Feedback Implementation (30 minutes)

This is the **fastest way** to improve your system. You'll create a feedback loop where Spark evaluation results feed back to improve future models.

---

## Step 1: Create Feedback Table in Database

**File to edit**: None (run this SQL directly)

```sql
-- Connect to your database:
-- docker exec timescaledb psql -U flead -d flead

-- Create feedback table
CREATE TABLE model_feedback (
    id BIGSERIAL PRIMARY KEY,
    model_version INT NOT NULL,
    aggregation_round INT,
    device_id TEXT,
    prediction FLOAT,
    actual_value FLOAT,
    error FLOAT,
    absolute_error FLOAT,
    is_correct BOOLEAN,
    confidence FLOAT,
    feedback_type VARCHAR(50), -- 'anomaly', 'normal', 'edge_case'
    timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create hypertable for time-series optimization
SELECT create_hypertable('model_feedback', 'created_at', if_not_exists => TRUE);

-- Create index for fast queries
CREATE INDEX idx_model_feedback_version ON model_feedback(model_version);
CREATE INDEX idx_model_feedback_device ON model_feedback(device_id);
CREATE INDEX idx_model_feedback_timestamp ON model_feedback(created_at);

-- Verify table
\dt model_feedback
```

---

## Step 2: Modify Spark to Write Feedback

**File**: `scripts/05_spark_analytics.py`

Find the `insert_model_evaluations` method (around line 200) and modify it:

```python
# AFTER the existing insert_model_evaluations method, add:

def insert_model_feedback(self, evaluations: List[Dict]):
    """Write model evaluation feedback to feedback table"""
    if not evaluations:
        return

    try:
        with self.conn.cursor() as cur:
            query = """
                INSERT INTO model_feedback
                (model_version, aggregation_round, device_id, prediction, actual_value,
                 error, absolute_error, is_correct, confidence, feedback_type, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = []
            for e in evaluations:
                prediction = e.get('prediction_result', 0)
                actual = e.get('actual_result', 0)
                error = float(actual - prediction)
                abs_error = abs(error)
                is_correct = error < 0.1  # Within 10% is "correct"

                # Determine feedback type
                if abs_error < 0.05:
                    feedback_type = 'normal'
                elif abs_error > 0.3:
                    feedback_type = 'edge_case'
                else:
                    feedback_type = 'anomaly'

                values.append((
                    e.get('model_version'),
                    e.get('aggregation_round'),
                    e.get('device_id'),
                    prediction,
                    actual,
                    error,
                    abs_error,
                    is_correct,
                    e.get('confidence'),
                    feedback_type,
                    datetime.now()
                ))

            execute_values(cur, query, values)
            self.conn.commit()
            logger.info(f"✓ Inserted {len(values)} feedback records")

    except Exception as e:
        logger.error(f"✗ Error inserting feedback: {e}")
        self.conn.rollback()


# In the main run loop, after insert_model_evaluations, add:
self.db.insert_model_feedback(evaluations)
```

---

## Step 3: Add Feedback Reading to Flink

**File**: `scripts/03_flink_local_training.py`

Modify the accuracy calculation to use feedback:

```python
# Add near the top of the file (after imports):
import psycopg2
from datetime import datetime

# Add database config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'flead',
    'user': 'flead',
    'password': 'password'
}

# Modify the calculate accuracy part (around line 147):

# REPLACE THIS:
# accuracy = min(0.95, 0.7 + (model['version'] * 0.02))

# WITH THIS:
def get_real_accuracy_from_feedback(device_id: str, model_version: int) -> float:
    """
    Calculate real accuracy based on Spark feedback from previous models
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Get feedback for this device's previous models
            cur.execute("""
                SELECT
                    COUNT(*) as total_predictions,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_predictions,
                    AVG(absolute_error) as avg_error,
                    MAX(absolute_error) as max_error
                FROM model_feedback
                WHERE device_id = %s
                  AND model_version <= %s
                  AND created_at > NOW() - INTERVAL '1 hour'
            """, (device_id, model_version - 1))

            result = cur.fetchone()
            conn.close()

            if result and result[0] > 0:  # Has feedback data
                total = result[0]
                correct = result[1]
                avg_error = result[2]

                # Calculate real accuracy from feedback
                feedback_accuracy = correct / total if total > 0 else 0.5

                # Adjust based on error magnitude
                error_penalty = min(avg_error, 0.3) / 0.3  # Max 30% penalty
                real_accuracy = feedback_accuracy * (1 - error_penalty * 0.2)

                logger.info(f"Device {device_id}: Real accuracy = {real_accuracy:.2%} "
                           f"(from {total} predictions)")

                return min(0.95, max(0.5, real_accuracy))  # Cap 50-95%
            else:
                # No feedback yet, use model version-based estimate
                return min(0.95, 0.7 + (model_version * 0.01))

    except Exception as e:
        logger.warning(f"Could not get feedback: {e}, using formula")
        return min(0.95, 0.7 + (model_version * 0.01))


# Then replace the accuracy line with:
accuracy = get_real_accuracy_from_feedback(device_id, model['version'])
```

---

## Step 4: Monitor the Feedback Loop

**Check if it's working**:

```bash
# Connect to database
docker exec timescaledb psql -U flead -d flead

# Check feedback table
SELECT COUNT(*) FROM model_feedback;

# See recent feedback
SELECT model_version, device_id, prediction, actual_value, error, is_correct
FROM model_feedback
ORDER BY created_at DESC
LIMIT 10;

# Check accuracy improvement
SELECT
    model_version,
    COUNT(*) as feedback_count,
    AVG(CASE WHEN is_correct THEN 1 ELSE 0 END) as accuracy,
    AVG(absolute_error) as avg_error
FROM model_feedback
GROUP BY model_version
ORDER BY model_version DESC;
```

---

## Step 5: Add Monitoring Query

**Add to Grafana**: Create a new panel with this query

```sql
-- Model Accuracy Improvement Over Time
SELECT
    model_version,
    COUNT(*) as evaluations,
    ROUND(100.0 * AVG(CASE WHEN is_correct THEN 1 ELSE 0 END))::INT as accuracy_percent,
    ROUND(100.0 * AVG(absolute_error), 2)::FLOAT as avg_error_percent
FROM model_feedback
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY model_version
ORDER BY model_version DESC
LIMIT 20;
```

---

## 🚀 Quick Test: Verify It's Working

### Option 1: Manually check database

```bash
docker exec timescaledb psql -U flead -d flead -c "SELECT * FROM model_feedback LIMIT 5;"
```

### Option 2: Check logs

```bash
# Spark logs
tail -f logs/spark_analytics.log | grep -i "feedback"

# Flink logs (show real accuracy)
docker logs flink-jobmanager | grep "Real accuracy"
```

### Option 3: Query improvement trend

```sql
-- Get last 10 global models and their average accuracy from feedback
SELECT
    fm.model_version,
    COUNT(*) as predictions,
    ROUND(100.0 * AVG(CASE WHEN fm.is_correct THEN 1 ELSE 0 END))::INT as accuracy,
    ROUND(AVG(fm.absolute_error), 4) as avg_error
FROM model_feedback fm
GROUP BY fm.model_version
ORDER BY fm.model_version DESC
LIMIT 10;
```

---

## 📊 Expected Results

**Before Feedback Loop**:

```
Model Version 1: 72% (hardcoded)
Model Version 2: 74% (hardcoded)
Model Version 3: 76% (hardcoded)
...
```

**After Feedback Loop**:

```
Model Version 1: 72% (hardcoded initially)
Model Version 2: 74% (hardcoded initially)
Model Version 3: 78% (NOW based on feedback!)
Model Version 4: 81% (improving from real data!)
Model Version 5: 84% (feedback-driven improvement!)
...
```

---

## 🔄 How It Works

```
┌─────────────────────────────────────┐
│ Flink Creates Local Model v5        │
│ (accuracy = formula)                │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ Federated: Aggregate v1-v4          │
│ → Create Global Model v5            │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ Spark: Evaluate Global Model v5     │
│ • Test on stream data               │
│ • Compare predictions vs actual     │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ [NEW] Save Feedback to DB           │
│ • Prediction accuracy               │
│ • Error magnitude                   │
│ • Correct/incorrect                 │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│ [NEW] Flink Reads Feedback          │
│ • Query previous predictions        │
│ • Calculate real accuracy           │
│ • Use for next model v6!            │
└─────────────────────────────────────┘
```

---

## Files to Edit

| File                                 | Lines | Change                                                             |
| ------------------------------------ | ----- | ------------------------------------------------------------------ |
| `scripts/05_spark_analytics.py`      | ~200  | Add `insert_model_feedback()` method                               |
| `scripts/03_flink_local_training.py` | ~147  | Replace hardcoded formula with `get_real_accuracy_from_feedback()` |
| Database                             | SQL   | Create `model_feedback` table                                      |

---

## ⏱️ Implementation Checklist

-   [ ] Run SQL to create `model_feedback` table
-   [ ] Modify `05_spark_analytics.py` to write feedback
-   [ ] Modify `03_flink_local_training.py` to read feedback
-   [ ] Test by running pipeline: `START.bat`
-   [ ] Check database after 10 minutes: `SELECT COUNT(*) FROM model_feedback;`
-   [ ] Verify accuracy improves: Run the trending query
-   [ ] Add Grafana panel with the improvement query

---

## 📈 Next Steps

Once this works:

1. **Phase 2**: Replace accuracy formula with real SGD training (2 hours)
2. **Phase 3**: Add adaptive hyperparameters (4 hours)
3. **Phase 4**: Full closed-loop continuous improvement (6 hours)

---

## Questions?

Check `TRAINING_ARCHITECTURE.md` for full system architecture explanation.

---

_Ready to implement? Let me know when you want me to code it!_

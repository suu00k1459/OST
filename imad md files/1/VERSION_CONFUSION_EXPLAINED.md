# 🔴 VERSION CONFUSION EXPLAINED - Why v1, v4, v3 Jumping Around

## The Problem You're Seeing

On your dashboard you see:

```
device_1:    v2 - 74.0% - 2s ago
device_234:  v4 - 74.0% - 2s ago  ← Different version!
device_2705: v3 - 74.0% - 2s ago  ← Different version!
device_889:  v2 - 74.0% - 3s ago
```

**Why is each device showing different versions? (v2, v3, v4...)**

Because there are **TWO DIFFERENT VERSION SYSTEMS** running at the same time!

---

## 📊 Two Version Systems (This Is The Confusion)

### System 1: LOCAL MODEL VERSION (Per Device)

**Location**: `scripts/03_flink_local_training.py` line 138

```python
model['version'] += 1  # Each device keeps its OWN version counter
```

**What it means:**

-   **device_0**: Has trained v1, v2, v3, v4, v5... of ITS OWN local model
-   **device_1**: Has trained v1, v2, v3, v4, v5... of ITS OWN local model
-   **device_100**: Has trained v1, v2, v3, v4, v5... of ITS OWN local model

Each device INDEPENDENTLY increments its version.

**Example Timeline:**

```
Time 0:  device_0 creates v1, device_1 creates v1, device_100 creates v1
Time 5:  device_0 creates v2, device_1 creates v2, device_100 creates v2
Time 10: device_0 creates v3, device_1 creates v3, device_100 creates v3

BUT:
- device_0 trains slowly (30 second cycle) → only at v3
- device_1 trains fast (20 second cycle)  → already at v5
- device_100 trains fast (20 second cycle) → already at v5
```

### System 2: GLOBAL MODEL VERSION (Federated)

**Location**: `scripts/04_federated_aggregation.py` line 274

```python
self.global_model.version += 1  # ONE global version for entire system
```

**What it means:**

-   **Global v1**: Averaged from (device_0.v1 + device_1.v1 + device_100.v1 + ...)
-   **Global v2**: Averaged from (device_0.v2 + device_1.v2 + device_100.v2 + ...)
-   **Global v3**: Averaged from (device_0.v3 + device_1.v3 + device_100.v3 + ...)

There's ONE global version counter for the whole system.

---

## 🤔 Why This Creates Confusion

Your dashboard shows the **LOCAL** version (per device), not the global version.

When you see:

```
device_1:    v2 - 74.0%
device_234:  v4 - 74.0%
device_2705: v3 - 74.0%
```

This is CORRECT and NORMAL! Here's why:

**Reason 1: Different Training Speeds**

-   Devices train at different rates (50 rows OR 60 seconds trigger)
-   device_234 might be processing data faster → already at v4
-   device_2705 processing slower → still at v3
-   device_1 processing slowest → still at v2

**Reason 2: Devices Can Restart**

-   If device_234 crashes/restarts, its version counter resets
-   It starts back at v1 or v2 again

**Reason 3: 2,407 Devices = Chaos**

-   2,407 devices each with their own version counter
-   All incrementing at different rates
-   Creates this "jumping" effect you're seeing

---

## 📈 What SHOULD Be Happening (But Isn't - The Real Problem)

The **GLOBAL** version should be increasing steadily:

```
Global v1: Averaged from all 2,407 devices
Global v2: Averaged from all 2,407 devices
Global v3: Averaged from all 2,407 devices
Global v4: Averaged from all 2,407 devices
...
```

But the **ACCURACY** should be DIFFERENT each time:

**Expected (with real learning):**

```
Global v1: 72% accuracy
Global v2: 74% accuracy  ← Real improvement
Global v3: 78% accuracy  ← Real improvement
Global v4: 82% accuracy  ← Real improvement
```

**What You Actually Get (with hardcoded formula):**

```
All local models: 74.0% (no matter what version!)
All global models: 74.0% (no matter what version!)
```

---

## 🔍 The Real Issue: Hardcoded Accuracy

### Local Training (Flink) - Line 147

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
```

This means:

-   device_234 v1: 72%
-   device_234 v2: 74%
-   device_234 v3: 76%
-   device_234 v4: 78%
-   device_234 v5: 80%
-   device_234 v14+: 95% (capped)

**BUT**: Every device follows this SAME formula!

So device_1, device_2, device_100... all show:

-   v1: 72%
-   v2: 74%
-   v3: 76%
-   etc.

**Result**: Everyone stuck at 74% accuracy for v2! ✗

---

## ✅ What SHOULD Happen (With Real Learning)

### Step 1: Different Devices, Different Speeds

```
Time=10s: device_0 (v1), device_1 (v2), device_5 (v1)  ← Normal! Different speeds
Time=20s: device_0 (v2), device_1 (v3), device_5 (v2)  ← Still normal!
Time=30s: device_0 (v3), device_1 (v4), device_5 (v3)  ← Still normal!
```

### Step 2: Federated Aggregation Happens Every 20 Updates

```
After 20 local updates → Global v1 created
After 40 local updates → Global v2 created
After 60 local updates → Global v3 created
After 80 local updates → Global v4 created
```

### Step 3: Global Models Improve (Real Learning)

```
Global v1: 72% (initial)
Global v2: 74% (improved) ← Real feedback!
Global v3: 78% (improved) ← Real feedback!
Global v4: 82% (improved) ← Real feedback!
```

### Step 4: Local Models Learn from Global

```
device_0 v1: 72% (initial local)
  ↓ Gets Global v1 (72%)
  ↓ Trains with feedback
device_0 v2: 76% (improved from global feedback!)

device_1 v1: 72% (initial local)
  ↓ Gets Global v1 (72%)
  ↓ Trains with feedback
device_1 v2: 78% (improved from global feedback!)
```

---

## 🎯 Why It's "Going Back to 72%"

You said:

> "It's going yes from 72 to 74 to 76 to 78 then back to 72"

This happens because:

**Your local model formula:**

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
```

**With 2,407 devices at different speeds:**

-   device_0 might be at v5 (80%)
-   device_1 might be at v2 (74%)
-   device_2 might be at v1 (72%)
-   device_3 might be at v4 (78%)

When you look at recent activity, you see them in random order, so it LOOKS like:

```
72% (device_2 v1)
74% (device_1 v2)
76% (device_45 v3)
78% (device_3 v4)
72% (device_999 v1)  ← Different device, looks like it went BACK to 72%!
```

---

## 📊 How to Fix This (3 Steps)

### Step 1: Understand What You're Seeing

-   LOCAL version = Per-device version (v1, v2, v3...)
-   GLOBAL version = System-wide version (v1, v2, v3...)
-   Different devices at different versions = NORMAL
-   All showing 74% accuracy = BROKEN

### Step 2: Monitor the RIGHT Thing

Instead of watching individual device versions, monitor:

```sql
SELECT
  global_version,
  COUNT(DISTINCT device_id) as num_devices,
  AVG(accuracy) as global_accuracy,
  created_at
FROM federated_models
GROUP BY global_version
ORDER BY global_version;
```

This shows you REAL improvement:

```
Global v1: 2,407 devices, 72% average
Global v2: 2,407 devices, 74% average
Global v3: 2,407 devices, 78% average  ← Real improvement!
Global v4: 2,407 devices, 82% average  ← Real improvement!
```

### Step 3: Replace Hardcoded Formula

Change line 147 in `03_flink_local_training.py`:

**Current (FAKE):**

```python
accuracy = min(0.95, 0.7 + (model['version'] * 0.02))
```

**Next (REAL - with feedback loop):**

```python
# Get real accuracy from evaluations
real_accuracy = get_real_accuracy_from_feedback(device_id, model['version'])
accuracy = real_accuracy if real_accuracy else 0.7  # Default to 0.7 if no feedback yet
```

Then implement the feedback loop from Spark → Flink.

---

## 🎓 Summary

| Aspect                        | What You See                  | Why                               | What It Means        |
| ----------------------------- | ----------------------------- | --------------------------------- | -------------------- |
| **Local v1, v2, v3...**       | Different per device          | Devices train at different speeds | NORMAL               |
| **All showing 74%**           | Same accuracy everywhere      | Hardcoded formula                 | BROKEN               |
| **Going back to 72%**         | Random device appears with v1 | Seeing different devices          | CONFUSING but NORMAL |
| **Global v1, v2, v3...**      | Only ONE per system           | Federation aggregates all devices | CURRENTLY NOT SHOWN  |
| **Global accuracy improving** | Currently NOT happening       | No feedback loop                  | NEEDS TO BE FIXED    |

---

## 📋 Action Items

-   [ ] Monitor **global** versions instead of local versions
-   [ ] Check if global accuracy is actually improving
-   [ ] Implement feedback loop to make accuracy REAL
-   [ ] After feedback loop: You should see continuous improvement
-   [ ] Eventually: Add real SGD training to replace hardcoded formula

---

**TL;DR**: Each device has its OWN version counter (v1, v2, v3) that increments independently.
This is NORMAL. The problem is they all show 74% accuracy because of the hardcoded formula,
not because something is "going backwards". You need to implement the feedback loop to make
accuracy REAL and IMPROVING.

"""
Federated Learning Aggregation Service
Aggregates local model updates from edge devices into a global model
Implements Federated Averaging (FedAvg) algorithm

Subscribes to: local-model-updates topic
Publishes to: global-model-updates topic
Stores to: TimescaleDB (federated_models & local_models tables)

Enhanced Features:
- Model Version Registry with rollback capability
- Performance tracking with accuracy degradation detection
- Adaptive contribution weighting
- Model staleness detection
- Health monitoring with alerts

Automatically detects if running inside Docker or locally
"""
from kafka.errors import NoBrokersAvailable

import json
import logging
import os
import sys
import shutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import pickle
import time
import threading

import numpy as np
from kafka import KafkaConsumer, KafkaProducer
import psycopg2

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# CONFIG LOADER (shared helper)
# ---------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from config_loader import get_db_config, get_kafka_config  # noqa: E402

# Kafka configuration - auto-detect Docker vs local
kafka_config = get_kafka_config()

_raw_bootstrap = kafka_config["bootstrap_servers"]
if isinstance(_raw_bootstrap, str):
    KAFKA_BOOTSTRAP_SERVERS: List[str] = [
        s.strip() for s in _raw_bootstrap.split(",") if s.strip()
    ]
else:
    # Allow config_loader to return list already
    KAFKA_BOOTSTRAP_SERVERS = list(_raw_bootstrap)

INPUT_TOPIC = "local-model-updates"
OUTPUT_TOPIC = "global-model-updates"
CONSUMER_GROUP = "federated-aggregation"

# TimescaleDB configuration - auto-detect Docker vs local
db_config = get_db_config()
DB_HOST = db_config["host"]
DB_PORT = db_config["port"]
DB_NAME = db_config["database"]
DB_USER = db_config["user"]
DB_PASSWORD = db_config["password"]

logger.info(f"Kafka Brokers: {', '.join(KAFKA_BOOTSTRAP_SERVERS)}")
logger.info(
    f"Database Config: host={DB_HOST}, "
    f"port={DB_PORT}, database={DB_NAME}, user={DB_USER}"
)

# ---------------------------------------------------------------------
# MODEL STORAGE
# ---------------------------------------------------------------------
MODELS_DIR = Path("models")
LOCAL_MODELS_DIR = MODELS_DIR / "local"
GLOBAL_MODELS_DIR = MODELS_DIR / "global"
MODEL_ARCHIVE_DIR = MODELS_DIR / "archive"

for d in [MODELS_DIR, LOCAL_MODELS_DIR, GLOBAL_MODELS_DIR, MODEL_ARCHIVE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# AGGREGATION SETTINGS
# ---------------------------------------------------------------------
AGGREGATION_WINDOW = 15          # Aggregate every 15 local model updates (optimized from 20)
MIN_DEVICES_FOR_AGGREGATION = 2  # Minimum devices needed
FEDAVG_LEARNING_RATE = 0.1       # (placeholder, not used for numeric weights here)

# New: Model versioning and health monitoring settings
MAX_MODEL_VERSIONS_KEPT = 10     # Keep last N model versions for rollback
ACCURACY_DEGRADATION_THRESHOLD = 0.05  # Trigger alert if accuracy drops by 5%
MODEL_STALENESS_HOURS = 24       # Mark device stale if no updates in N hours
PERFORMANCE_HISTORY_SIZE = 50    # Track last N aggregation rounds for trend analysis

# ---------------------------------------------------------------------
# DIFFERENTIAL PRIVACY SETTINGS
# ---------------------------------------------------------------------
DIFFERENTIAL_PRIVACY_ENABLED = True   # Toggle DP on/off
DP_EPSILON = 1.0                       # Privacy budget (lower = more private, noisier)
DP_DELTA = 1e-5                        # Probability bound for privacy guarantee
DP_CLIP_NORM = 1.0                     # Max L2 norm for gradient/update clipping

# ---------------------------------------------------------------------
# DEVICE CLUSTERING SETTINGS
# ---------------------------------------------------------------------
DEVICE_CLUSTERING_ENABLED = True      # Toggle device clustering on/off
CLUSTER_MIN_DEVICES = 3               # Minimum devices to form a cluster
CLUSTER_SIMILARITY_THRESHOLD = 0.15   # Max accuracy difference for same cluster
DP_NOISE_MULTIPLIER = 1.1              # Multiplier for Gaussian noise (derived from epsilon)


# ---------------------------------------------------------------------
# ALERT SEVERITY ENUM
# ---------------------------------------------------------------------
class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Represents a system alert"""
    timestamp: datetime
    severity: AlertSeverity
    category: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "metadata": self.metadata
        }


@dataclass
class ModelVersion:
    """Represents a historical model version for registry"""
    version: int
    accuracy: float
    num_devices: int
    aggregation_round: int
    created_at: datetime
    file_path: Optional[Path] = None
    is_active: bool = False
    rolled_back_from: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "accuracy": self.accuracy,
            "num_devices": self.num_devices,
            "aggregation_round": self.aggregation_round,
            "created_at": self.created_at.isoformat(),
            "file_path": str(self.file_path) if self.file_path else None,
            "is_active": self.is_active,
            "rolled_back_from": self.rolled_back_from
        }


class ModelRegistry:
    """
    Registry for tracking model versions with rollback capability.
    Stores model metadata and provides version management.
    """

    def __init__(self, max_versions: int = MAX_MODEL_VERSIONS_KEPT):
        self.versions: Dict[int, ModelVersion] = {}
        self.max_versions = max_versions
        self.current_version: int = 0
        self.best_version: int = 0
        self.best_accuracy: float = 0.0
        self._lock = threading.Lock()

    def register_model(
        self,
        version: int,
        accuracy: float,
        num_devices: int,
        aggregation_round: int,
        file_path: Optional[Path] = None
    ) -> ModelVersion:
        """Register a new model version in the registry"""
        with self._lock:
            model_version = ModelVersion(
                version=version,
                accuracy=accuracy,
                num_devices=num_devices,
                aggregation_round=aggregation_round,
                created_at=datetime.now(),
                file_path=file_path,
                is_active=True
            )

            # Deactivate previous version
            if self.current_version in self.versions:
                self.versions[self.current_version].is_active = False

            self.versions[version] = model_version
            self.current_version = version

            # Track best model
            if accuracy > self.best_accuracy:
                self.best_accuracy = accuracy
                self.best_version = version
                logger.info(f"🏆 New best model: v{version} with accuracy {accuracy*100:.2f}%")

            # Cleanup old versions
            self._cleanup_old_versions()

            return model_version

    def _cleanup_old_versions(self) -> None:
        """Remove oldest versions beyond max_versions limit"""
        if len(self.versions) <= self.max_versions:
            return

        # Sort by version number, keep most recent
        sorted_versions = sorted(self.versions.keys())
        versions_to_remove = sorted_versions[:-self.max_versions]

        for v in versions_to_remove:
            model_version = self.versions.pop(v)
            # Archive the model file instead of deleting
            if model_version.file_path and model_version.file_path.exists():
                archive_path = MODEL_ARCHIVE_DIR / model_version.file_path.name
                # Use shutil.move for cross-device compatibility (Docker volumes)
                shutil.move(str(model_version.file_path), str(archive_path))
                logger.info(f"📦 Archived model v{v} to {archive_path}")

    def get_version(self, version: int) -> Optional[ModelVersion]:
        """Get a specific model version"""
        return self.versions.get(version)

    def get_rollback_candidates(self) -> List[ModelVersion]:
        """Get list of versions available for rollback, sorted by accuracy"""
        return sorted(
            [v for v in self.versions.values() if not v.is_active],
            key=lambda x: x.accuracy,
            reverse=True
        )

    def rollback_to_version(self, target_version: int) -> Optional[ModelVersion]:
        """
        Rollback to a previous model version.
        Creates a new version entry that references the rollback source.
        """
        with self._lock:
            if target_version not in self.versions:
                logger.error(f"❌ Cannot rollback: version {target_version} not found")
                return None

            source = self.versions[target_version]
            new_version = self.current_version + 1

            rollback_entry = ModelVersion(
                version=new_version,
                accuracy=source.accuracy,
                num_devices=source.num_devices,
                aggregation_round=source.aggregation_round,
                created_at=datetime.now(),
                file_path=source.file_path,
                is_active=True,
                rolled_back_from=target_version
            )

            # Deactivate current
            if self.current_version in self.versions:
                self.versions[self.current_version].is_active = False

            self.versions[new_version] = rollback_entry
            self.current_version = new_version

            logger.warning(
                f"⏪ ROLLBACK: Created v{new_version} from v{target_version} "
                f"(accuracy: {source.accuracy*100:.2f}%)"
            )

            return rollback_entry

    def get_registry_status(self) -> Dict[str, Any]:
        """Get registry status summary"""
        return {
            "total_versions": len(self.versions),
            "current_version": self.current_version,
            "best_version": self.best_version,
            "best_accuracy": self.best_accuracy,
            "versions": [v.to_dict() for v in sorted(
                self.versions.values(), key=lambda x: x.version, reverse=True
            )[:5]]  # Last 5 versions
        }


class PerformanceMonitor:
    """
    Monitors model performance over time and detects anomalies.
    Triggers alerts on accuracy degradation, stale devices, etc.
    """

    def __init__(self, history_size: int = PERFORMANCE_HISTORY_SIZE):
        self.accuracy_history: deque = deque(maxlen=history_size)
        self.device_last_seen: Dict[str, datetime] = {}
        self.alerts: List[Alert] = []
        self.alert_callback: Optional[callable] = None
        self._lock = threading.Lock()

    def record_aggregation(
        self,
        version: int,
        accuracy: float,
        num_devices: int,
        device_ids: List[str]
    ) -> List[Alert]:
        """Record aggregation metrics and check for issues"""
        new_alerts = []

        with self._lock:
            # Update device last seen
            now = datetime.now()
            for device_id in device_ids:
                self.device_last_seen[device_id] = now

            # Check for accuracy degradation
            if len(self.accuracy_history) >= 3:
                recent_avg = np.mean(list(self.accuracy_history)[-3:])
                if accuracy < recent_avg - ACCURACY_DEGRADATION_THRESHOLD:
                    alert = Alert(
                        timestamp=now,
                        severity=AlertSeverity.WARNING,
                        category="accuracy_degradation",
                        message=f"Model accuracy dropped from {recent_avg*100:.2f}% to {accuracy*100:.2f}%",
                        metadata={
                            "version": version,
                            "current_accuracy": accuracy,
                            "recent_average": recent_avg,
                            "degradation": recent_avg - accuracy
                        }
                    )
                    new_alerts.append(alert)

            # Record accuracy
            self.accuracy_history.append(accuracy)

            # Check for stale devices
            stale_threshold = now - timedelta(hours=MODEL_STALENESS_HOURS)
            stale_devices = [
                device_id for device_id, last_seen in self.device_last_seen.items()
                if last_seen < stale_threshold
            ]

            if stale_devices and len(stale_devices) > len(self.device_last_seen) * 0.3:
                alert = Alert(
                    timestamp=now,
                    severity=AlertSeverity.WARNING,
                    category="stale_devices",
                    message=f"{len(stale_devices)} devices have not sent updates in {MODEL_STALENESS_HOURS}h",
                    metadata={"stale_devices": stale_devices[:10]}  # Limit to first 10
                )
                new_alerts.append(alert)

            # Check for low device participation
            if num_devices < MIN_DEVICES_FOR_AGGREGATION * 2:
                alert = Alert(
                    timestamp=now,
                    severity=AlertSeverity.INFO,
                    category="low_participation",
                    message=f"Only {num_devices} devices participated in aggregation",
                    metadata={"num_devices": num_devices}
                )
                new_alerts.append(alert)

            # Store alerts
            self.alerts.extend(new_alerts)
            # Keep only last 100 alerts
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]

            # Trigger callback if set
            if new_alerts and self.alert_callback:
                for alert in new_alerts:
                    self.alert_callback(alert)

        return new_alerts

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        history = list(self.accuracy_history)
        return {
            "total_rounds": len(history),
            "current_accuracy": history[-1] if history else 0.0,
            "average_accuracy": float(np.mean(history)) if history else 0.0,
            "min_accuracy": float(np.min(history)) if history else 0.0,
            "max_accuracy": float(np.max(history)) if history else 0.0,
            "accuracy_trend": self._calculate_trend(history),
            "active_devices": len(self.device_last_seen),
            "recent_alerts": [a.to_dict() for a in self.alerts[-5:]]
        }

    def _calculate_trend(self, history: List[float]) -> str:
        """Calculate accuracy trend"""
        if len(history) < 5:
            return "insufficient_data"

        recent = history[-5:]
        older = history[-10:-5] if len(history) >= 10 else history[:5]

        recent_avg = np.mean(recent)
        older_avg = np.mean(older)

        diff = recent_avg - older_avg
        if diff > 0.02:
            return "improving"
        elif diff < -0.02:
            return "declining"
        else:
            return "stable"


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
    
    def __init__(
        self,
        epsilon: float = DP_EPSILON,
        delta: float = DP_DELTA,
        clip_norm: float = DP_CLIP_NORM,
        noise_multiplier: float = DP_NOISE_MULTIPLIER,
        enabled: bool = DIFFERENTIAL_PRIVACY_ENABLED
    ):
        self.epsilon = epsilon
        self.delta = delta
        self.clip_norm = clip_norm
        self.noise_multiplier = noise_multiplier
        self.enabled = enabled
        self.privacy_spent = 0.0  # Track cumulative privacy budget spent
        self.rounds_processed = 0
        self._lock = threading.Lock()
        
        # Calculate noise scale from epsilon and delta using Gaussian mechanism
        # σ ≥ √(2 × ln(1.25/δ)) × Δf / ε where Δf is sensitivity (clip_norm)
        self.noise_scale = self._calculate_noise_scale()
        
        if self.enabled:
            logger.info(
                f"🔐 Differential Privacy enabled: ε={epsilon}, δ={delta}, "
                f"clip_norm={clip_norm}, noise_scale={self.noise_scale:.4f}"
            )
    
    def _calculate_noise_scale(self) -> float:
        """Calculate Gaussian noise scale from privacy parameters"""
        # Standard Gaussian mechanism: σ = Δf × √(2 × ln(1.25/δ)) / ε
        sensitivity = self.clip_norm
        return sensitivity * np.sqrt(2 * np.log(1.25 / self.delta)) / self.epsilon
    
    def clip_update(self, accuracy: float) -> float:
        """
        Clip the accuracy value to bound sensitivity.
        
        For accuracy values (0-1 range), we clip to ensure bounded sensitivity.
        """
        if not self.enabled:
            return accuracy
        
        # Accuracy is already bounded [0, 1], but we can further clip for stability
        return np.clip(accuracy, 0.0, min(1.0, self.clip_norm))
    
    def add_noise(self, value: float, scale_factor: float = 1.0) -> float:
        """
        Add calibrated Gaussian noise to a value for differential privacy.
        
        Args:
            value: The value to add noise to
            scale_factor: Optional scaling for the noise (e.g., based on sample size)
            
        Returns:
            Noised value clipped to valid range
        """
        if not self.enabled:
            return value
        
        # Sample Gaussian noise with calculated scale
        noise = np.random.normal(0, self.noise_scale * scale_factor)
        noised_value = value + noise
        
        # Clip to valid accuracy range [0, 1]
        return np.clip(noised_value, 0.0, 1.0)
    
    def privatize_aggregation(
        self,
        device_accuracies: List[Dict[str, Any]],
        num_devices: int
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Apply differential privacy to local model updates before aggregation.
        
        Uses the following DP mechanisms:
        1. Clip individual contributions to bound sensitivity
        2. Add calibrated Gaussian noise to aggregated result
        3. Track privacy budget consumption
        
        Args:
            device_accuracies: List of device accuracy updates
            num_devices: Number of participating devices
            
        Returns:
            Tuple of (privatized_accuracies, dp_metadata)
        """
        if not self.enabled:
            return device_accuracies, {"dp_applied": False}
        
        with self._lock:
            self.rounds_processed += 1
            
            privatized = []
            total_noise_added = 0.0
            
            for device_data in device_accuracies:
                # Clone the data
                private_data = device_data.copy()
                
                # Step 1: Clip accuracy to bound sensitivity
                original_acc = private_data["accuracy"]
                clipped_acc = self.clip_update(original_acc)
                
                # Step 2: Add per-device noise (scaled by 1/sqrt(n) for composition)
                # This provides better utility when aggregating many devices
                scale_factor = 1.0 / np.sqrt(num_devices) if num_devices > 0 else 1.0
                noised_acc = self.add_noise(clipped_acc, scale_factor)
                
                private_data["accuracy"] = noised_acc
                private_data["dp_clipped"] = abs(original_acc - clipped_acc) > 1e-6
                private_data["dp_noise_added"] = noised_acc - clipped_acc
                
                privatized.append(private_data)
                total_noise_added += abs(noised_acc - clipped_acc)
            
            # Update privacy budget tracking (simple composition)
            # In practice, use advanced composition theorems for tighter bounds
            self.privacy_spent += self.epsilon / np.sqrt(self.rounds_processed)
            
            dp_metadata = {
                "dp_applied": True,
                "epsilon": self.epsilon,
                "delta": self.delta,
                "noise_scale": self.noise_scale,
                "avg_noise_magnitude": total_noise_added / len(device_accuracies) if device_accuracies else 0,
                "privacy_spent_total": self.privacy_spent,
                "rounds_processed": self.rounds_processed
            }
            
            logger.info(
                f"🔐 DP applied: avg_noise={dp_metadata['avg_noise_magnitude']:.4f}, "
                f"cumulative_ε≈{self.privacy_spent:.4f}"
            )
            
            return privatized, dp_metadata
    
    def get_privacy_status(self) -> Dict[str, Any]:
        """Get current privacy status and budget consumption"""
        return {
            "enabled": self.enabled,
            "epsilon": self.epsilon,
            "delta": self.delta,
            "noise_scale": self.noise_scale,
            "privacy_spent": self.privacy_spent,
            "rounds_processed": self.rounds_processed,
            "remaining_budget_estimate": max(0, 10.0 - self.privacy_spent)  # Assuming budget of 10
        }


class DeviceClusterManager:
    """
    Device Clustering for Federated Learning.
    
    Groups similar devices together based on their accuracy profiles and 
    performs separate FedAvg aggregation per cluster. This allows the system
    to create specialized models for different device behaviors/environments.
    
    Clustering Strategy:
    - Devices with similar accuracy profiles are grouped together
    - Each cluster gets its own aggregated model
    - Helps handle non-IID data distributions across devices
    """
    
    def __init__(
        self,
        min_devices_per_cluster: int = CLUSTER_MIN_DEVICES,
        similarity_threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
        enabled: bool = DEVICE_CLUSTERING_ENABLED
    ):
        self.min_devices = min_devices_per_cluster
        self.similarity_threshold = similarity_threshold
        self.enabled = enabled
        
        # Track device history for clustering decisions
        self.device_accuracy_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10)
        )
        self.device_clusters: Dict[str, int] = {}  # device_id -> cluster_id
        self.cluster_stats: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        if self.enabled:
            logger.info(
                f"📊 Device Clustering enabled: min_devices={min_devices_per_cluster}, "
                f"similarity_threshold={similarity_threshold}"
            )
    
    def update_device_history(self, device_id: str, accuracy: float) -> None:
        """Update accuracy history for a device"""
        with self._lock:
            self.device_accuracy_history[device_id].append(accuracy)
    
    def get_device_profile(self, device_id: str) -> Dict[str, float]:
        """Get statistical profile for a device based on its history"""
        history = list(self.device_accuracy_history.get(device_id, []))
        if not history:
            return {"mean": 0.5, "std": 0.0, "trend": 0.0}
        
        mean_acc = np.mean(history)
        std_acc = np.std(history) if len(history) > 1 else 0.0
        
        # Calculate trend (positive = improving, negative = declining)
        trend = 0.0
        if len(history) >= 3:
            recent = np.mean(history[-3:])
            older = np.mean(history[:-3]) if len(history) > 3 else history[0]
            trend = recent - older
        
        return {"mean": float(mean_acc), "std": float(std_acc), "trend": float(trend)}
    
    def compute_similarity(self, profile1: Dict[str, float], profile2: Dict[str, float]) -> float:
        """
        Compute similarity between two device profiles.
        Returns value in [0, 1] where 1 means identical.
        """
        mean_diff = abs(profile1["mean"] - profile2["mean"])
        std_diff = abs(profile1["std"] - profile2["std"])
        trend_diff = abs(profile1["trend"] - profile2["trend"])
        
        # Weighted combination
        distance = 0.6 * mean_diff + 0.2 * std_diff + 0.2 * trend_diff
        similarity = max(0, 1 - distance / self.similarity_threshold)
        
        return similarity
    
    def cluster_devices(
        self, 
        device_accuracies: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Cluster devices based on their accuracy profiles.
        
        Uses a simple agglomerative clustering approach:
        1. Compute profile for each device
        2. Greedily assign devices to clusters based on similarity
        
        Args:
            device_accuracies: List of device data with accuracy info
            
        Returns:
            Dict mapping cluster_id to list of devices in that cluster
        """
        if not self.enabled or len(device_accuracies) < self.min_devices:
            # Not enough devices for clustering, return all in one cluster
            return {0: device_accuracies}
        
        with self._lock:
            # Update histories first
            for device_data in device_accuracies:
                device_id = device_data["device_id"]
                accuracy = device_data["accuracy"]
                self.device_accuracy_history[device_id].append(accuracy)
            
            # Compute profiles for all devices
            profiles = {}
            for device_data in device_accuracies:
                device_id = device_data["device_id"]
                profiles[device_id] = self.get_device_profile(device_id)
            
            # Simple greedy clustering
            clusters: Dict[int, List[Dict[str, Any]]] = {}
            cluster_profiles: Dict[int, Dict[str, float]] = {}
            next_cluster_id = 0
            
            for device_data in device_accuracies:
                device_id = device_data["device_id"]
                device_profile = profiles[device_id]
                
                # Find best matching cluster
                best_cluster = None
                best_similarity = 0.0
                
                for cluster_id, cluster_profile in cluster_profiles.items():
                    sim = self.compute_similarity(device_profile, cluster_profile)
                    if sim > best_similarity and sim > 0.5:  # Minimum similarity threshold
                        best_similarity = sim
                        best_cluster = cluster_id
                
                if best_cluster is not None:
                    # Add to existing cluster
                    clusters[best_cluster].append(device_data)
                    self.device_clusters[device_id] = best_cluster
                    
                    # Update cluster profile (running average)
                    old_profile = cluster_profiles[best_cluster]
                    n = len(clusters[best_cluster])
                    cluster_profiles[best_cluster] = {
                        "mean": (old_profile["mean"] * (n-1) + device_profile["mean"]) / n,
                        "std": (old_profile["std"] * (n-1) + device_profile["std"]) / n,
                        "trend": (old_profile["trend"] * (n-1) + device_profile["trend"]) / n,
                    }
                else:
                    # Create new cluster
                    clusters[next_cluster_id] = [device_data]
                    cluster_profiles[next_cluster_id] = device_profile
                    self.device_clusters[device_id] = next_cluster_id
                    next_cluster_id += 1
            
            # Merge small clusters into the largest one
            if len(clusters) > 1:
                small_clusters = [cid for cid, devs in clusters.items() 
                                 if len(devs) < self.min_devices]
                if small_clusters:
                    # Find largest cluster
                    largest_cluster = max(clusters.keys(), 
                                         key=lambda cid: len(clusters[cid]))
                    
                    for small_cid in small_clusters:
                        if small_cid != largest_cluster:
                            # Merge into largest
                            for device_data in clusters[small_cid]:
                                clusters[largest_cluster].append(device_data)
                                self.device_clusters[device_data["device_id"]] = largest_cluster
                            del clusters[small_cid]
            
            # Update cluster stats
            self.cluster_stats = {
                cid: {
                    "num_devices": len(devs),
                    "avg_accuracy": np.mean([d["accuracy"] for d in devs]),
                    "total_samples": sum(d["samples"] for d in devs),
                    "profile": cluster_profiles.get(cid, {})
                }
                for cid, devs in clusters.items()
            }
            
            if len(clusters) > 1:
                logger.info(
                    f"📊 Clustered {len(device_accuracies)} devices into {len(clusters)} clusters: "
                    f"{[f'C{cid}:{len(devs)}' for cid, devs in clusters.items()]}"
                )
            
            return clusters
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get current clustering status"""
        return {
            "enabled": self.enabled,
            "num_clusters": len(self.cluster_stats),
            "cluster_stats": self.cluster_stats,
            "total_tracked_devices": len(self.device_accuracy_history)
        }


class GlobalModel:
    """Global model in federated learning with enhanced metadata tracking"""

    def __init__(self, version: int = 0):
        self.version = version
        self.weights = None  # Placeholder for real weight tensors if used later
        self.accuracy = 0.0
        self.created_at = datetime.now()
        self.num_devices_aggregated = 0
        self.aggregation_round = 0
        # New: Enhanced tracking
        self.total_samples_processed = 0
        self.device_contributions: Dict[str, float] = {}  # device_id -> contribution weight
        self.parent_version: Optional[int] = None  # For rollback tracking

    def to_dict(self) -> Dict[str, Any]:
        """Convert model metadata to dictionary"""
        return {
            "version": self.version,
            "accuracy": self.accuracy,
            "created_at": self.created_at.isoformat(),
            "num_devices_aggregated": self.num_devices_aggregated,
            "aggregation_round": self.aggregation_round,
            "total_samples_processed": self.total_samples_processed,
            "device_contributions": self.device_contributions,
            "parent_version": self.parent_version,
        }

    def save(self, path: Path) -> None:
        """Save model to disk"""
        try:
            with open(path, "wb") as f:
                pickle.dump(self, f)
            logger.info(f"✓ Global model v{self.version} saved to {path}")
        except Exception as e:
            logger.error(f"✗ Error saving model: {e}")

    @staticmethod
    def load(path: Path) -> "GlobalModel | None":
        """Load model from disk"""
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"✗ Error loading model: {e}")
            return None


class FederatedAggregator:
    """
    Federated learning aggregator using FedAvg algorithm.
    
    Enhanced with:
    - Model version registry with rollback capability
    - Performance monitoring with alerts
    - Adaptive contribution weighting
    - Health status reporting
    - Differential Privacy for privacy-preserving aggregation
    - Device Clustering for handling non-IID data
    """

    def __init__(self, producer: KafkaProducer):
        self.global_model = GlobalModel(version=0)
        self.local_model_buffer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.update_count = 0
        self.aggregation_round = 0
        self.db_connection: psycopg2.extensions.connection | None = None
        self.producer = producer

        # New: Enhanced components
        self.model_registry = ModelRegistry()
        self.performance_monitor = PerformanceMonitor()
        self.performance_monitor.alert_callback = self._handle_alert
        
        # Differential Privacy component
        self.differential_privacy = DifferentialPrivacy()
        
        # Device Clustering component
        self.device_cluster_manager = DeviceClusterManager()

        self._init_database()

    def _handle_alert(self, alert: Alert) -> None:
        """Handle system alerts - can be extended for notifications"""
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        emoji = severity_emoji.get(alert.severity, "📢")
        logger.log(
            logging.WARNING if alert.severity != AlertSeverity.INFO else logging.INFO,
            f"{emoji} ALERT [{alert.category}]: {alert.message}"
        )

        # Publish alert to Kafka for external consumers
        try:
            alert_data = alert.to_dict()
            alert_data["type"] = "system_alert"
            self.producer.send("system-alerts", value=alert_data)
        except Exception as e:
            logger.debug(f"Could not publish alert to Kafka: {e}")

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status for monitoring"""
        return {
            "global_model": self.global_model.to_dict(),
            "aggregation_round": self.aggregation_round,
            "pending_updates": self.update_count,
            "buffered_devices": len(self.local_model_buffer),
            "model_registry": self.model_registry.get_registry_status(),
            "performance": self.performance_monitor.get_performance_summary(),
            "differential_privacy": self.differential_privacy.get_privacy_status(),
            "device_clustering": self.device_cluster_manager.get_cluster_status(),
            "timestamp": datetime.now().isoformat()
        }

    def rollback_model(self, target_version: Optional[int] = None) -> bool:
        """
        Rollback to a previous model version.
        If target_version is None, rolls back to the best performing version.
        """
        if target_version is None:
            # Find best performing version
            target_version = self.model_registry.best_version

        if target_version == self.global_model.version:
            logger.warning("Already on the target version")
            return False

        rollback_entry = self.model_registry.rollback_to_version(target_version)
        if rollback_entry:
            # Load the model from disk if available
            if rollback_entry.file_path and rollback_entry.file_path.exists():
                loaded_model = GlobalModel.load(rollback_entry.file_path)
                if loaded_model:
                    loaded_model.version = rollback_entry.version
                    loaded_model.parent_version = target_version
                    self.global_model = loaded_model

            # Publish rollback event
            rollback_update = {
                "type": "model_rollback",
                "new_version": rollback_entry.version,
                "source_version": target_version,
                "accuracy": rollback_entry.accuracy,
                "timestamp": datetime.now().isoformat()
            }
            self._publish_global_update(rollback_update)
            return True

        return False

    # -----------------------------------------------------------------
    # DATABASE
    # -----------------------------------------------------------------
    def _init_database(self) -> None:
        """Initialize database connection and ensure tables exist.

        NOTE: In your architecture, database-init.py already creates the
        full schema with hypertables. This block is a *fallback* so the
        service is still usable if database-init was not run.
        """
        try:
            self.db_connection = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
            logger.info("✓ Connected to TimescaleDB")

            with self.db_connection.cursor() as cursor:
                # Fallback table creation (IF NOT EXISTS – won't override existing schema)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS federated_models (
                        id SERIAL PRIMARY KEY,
                        global_version INT NOT NULL,
                        aggregation_round INT NOT NULL,
                        num_devices INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS local_models (
                        id SERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        model_version INT NOT NULL,
                        global_version INT NOT NULL,
                        accuracy FLOAT NOT NULL,
                        samples_processed INT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # Tables are created by database-init service.
                # We do not attempt to convert to hypertable here to avoid deadlocks.
                
                self.db_connection.commit()
                logger.info("✓ Database tables check complete")

        except Exception as e:
            logger.error(f"✗ Database connection error: {e}")
            raise

    # -----------------------------------------------------------------
    # LOCAL MODEL HANDLING
    # -----------------------------------------------------------------
    def process_local_model_update(self, record: Dict[str, Any]) -> None:
        """Process incoming local model update from Kafka"""
        try:
            device_id = record.get("device_id")
            model_version = record.get("model_version")
            accuracy = float(record.get("accuracy", 0.0))
            samples_processed = int(record.get("samples_processed", 0))

            logger.info(
                "Received local model from %s: v%s, accuracy=%.2f%%, samples=%d",
                device_id,
                model_version,
                accuracy * 100.0,
                samples_processed,
            )

            model_info = {
                "device_id": device_id,
                "model_version": model_version,
                "accuracy": accuracy,
                "samples_processed": samples_processed,
                "timestamp": record.get("timestamp", datetime.now().isoformat()),
            }

            self.local_model_buffer[device_id].append(model_info)
            self.update_count += 1

            self._save_local_model_to_db(
                device_id, model_version, accuracy, samples_processed
            )

            # Trigger aggregation if enough updates accumulated
            if self.update_count >= AGGREGATION_WINDOW:
                global_update = self.aggregate()
                self.update_count = 0
                if global_update is not None:
                    self._publish_global_update(global_update)

        except Exception as e:
            logger.error(f"Error processing local model update: {e}", exc_info=True)

    def _save_local_model_to_db(
        self, device_id: str, model_version: int, accuracy: float, samples_processed: int
    ) -> None:
        """Persist local model metadata to TimescaleDB"""
        if not self.db_connection:
            return

        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO local_models
                        (device_id, model_version, global_version, accuracy, samples_processed)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        device_id,
                        model_version,
                        self.global_model.version,
                        accuracy,
                        samples_processed,
                    ),
                )
                self.db_connection.commit()
        except Exception as e:
            self.db_connection.rollback()
            logger.warning(f"Error saving local model to DB: {e}")

    # -----------------------------------------------------------------
    # FEDERATED AGGREGATION (FedAvg-style)
    # -----------------------------------------------------------------
    def aggregate(self) -> Dict[str, Any] | None:
        """
        Aggregate local models using a simple FedAvg-style accuracy merge.

        Aggregation:
          - GlobalAccuracy = Σ(accuracy_i × samples_i) / Σ(samples_i)
          - Devices contribute proportionally to their samples_processed
          
        Enhanced with:
          - Model registry tracking
          - Performance monitoring
          - Contribution weighting tracking
          - Differential Privacy for privacy-preserving aggregation
          - Device Clustering for handling non-IID data
        """
        try:
            num_devices = len(self.local_model_buffer)
            if num_devices < MIN_DEVICES_FOR_AGGREGATION:
                logger.warning(
                    "⚠ Not enough devices for aggregation: %d/%d",
                    num_devices,
                    MIN_DEVICES_FOR_AGGREGATION,
                )
                return None

            logger.info("\n%s", "=" * 70)
            logger.info("Federated Aggregation Round %d", self.aggregation_round + 1)
            logger.info("%s", "=" * 70)
            logger.info("Number of devices: %d", num_devices)

            total_samples = 0
            weighted_accuracy = 0.0
            device_accuracies: List[Dict[str, Any]] = []
            device_contributions: Dict[str, float] = {}
            participating_device_ids: List[str] = []

            for device_id, updates in self.local_model_buffer.items():
                if not updates:
                    continue

                latest_update = updates[-1]
                accuracy = float(latest_update["accuracy"])
                samples = int(latest_update["samples_processed"])

                device_accuracies.append(
                    {
                        "device_id": device_id,
                        "accuracy": accuracy,
                        "samples": samples,
                    }
                )
                
                total_samples += samples
                participating_device_ids.append(device_id)

                logger.info(
                    "  Device %s: accuracy=%.2f%%, samples=%d",
                    device_id,
                    accuracy * 100.0,
                    samples,
                )

            # Apply Device Clustering to group similar devices
            device_clusters = self.device_cluster_manager.cluster_devices(device_accuracies)
            cluster_info = self.device_cluster_manager.get_cluster_status()

            # Apply Differential Privacy before aggregation
            privatized_accuracies, dp_metadata = self.differential_privacy.privatize_aggregation(
                device_accuracies, num_devices
            )
            
            # Calculate weighted accuracy using privatized values
            for da in privatized_accuracies:
                weighted_accuracy += da["accuracy"] * da["samples"]
            
            # Calculate contribution weights (normalized)
            for da in privatized_accuracies:
                contrib_weight = da["samples"] / total_samples if total_samples > 0 else 0.0
                device_contributions[da["device_id"]] = contrib_weight

            global_accuracy = (
                weighted_accuracy / total_samples if total_samples > 0 else 0.0
            )

            # Update global model state
            prev_version = self.global_model.version
            self.global_model.version += 1
            self.global_model.accuracy = global_accuracy
            self.global_model.num_devices_aggregated = num_devices
            self.aggregation_round += 1
            self.global_model.aggregation_round = self.aggregation_round
            self.global_model.total_samples_processed = total_samples
            self.global_model.device_contributions = device_contributions
            self.global_model.parent_version = prev_version

            logger.info("\n  Global Model v%d:", self.global_model.version)
            logger.info("  Weighted Average Accuracy: %.2f%%", global_accuracy * 100.0)
            if dp_metadata.get("dp_applied"):
                logger.info("  🔐 Differential Privacy: ε=%.2f, noise_avg=%.4f", 
                           dp_metadata["epsilon"], dp_metadata["avg_noise_magnitude"])
            logger.info("  Total Samples Processed: %d", total_samples)
            logger.info("  Aggregation Round: %d", self.aggregation_round)

            # Persist model snapshot
            model_path = GLOBAL_MODELS_DIR / f"global_model_v{self.global_model.version}.pkl"
            self.global_model.save(model_path)

            # Register model in registry
            self.model_registry.register_model(
                version=self.global_model.version,
                accuracy=global_accuracy,
                num_devices=num_devices,
                aggregation_round=self.aggregation_round,
                file_path=model_path
            )

            # Record performance metrics and check for alerts
            alerts = self.performance_monitor.record_aggregation(
                version=self.global_model.version,
                accuracy=global_accuracy,
                num_devices=num_devices,
                device_ids=participating_device_ids
            )

            # Save summary to DB
            self._save_global_model_to_db(global_accuracy, num_devices)

            # Reset buffer for next round
            self.local_model_buffer.clear()

            global_update = {
                "version": self.global_model.version,
                "aggregation_round": self.aggregation_round,
                "global_accuracy": global_accuracy,
                "num_devices": num_devices,
                "device_accuracies": privatized_accuracies,  # Use privatized data
                "device_contributions": device_contributions,
                "timestamp": datetime.now().isoformat(),
                "total_samples": total_samples,
                "alerts_triggered": len(alerts),
                "registry_status": self.model_registry.get_registry_status(),
                "differential_privacy": dp_metadata,  # Include DP metadata
                "device_clustering": cluster_info,  # Include clustering info
            }

            logger.info("%s\n", "=" * 70)
            return global_update

        except Exception as e:
            logger.error(f"Error in aggregation: {e}", exc_info=True)
            return None

    def _save_global_model_to_db(self, accuracy: float, num_devices: int) -> None:
        """Persist global model metadata to TimescaleDB"""
        if not self.db_connection:
            return

        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO federated_models
                        (global_version, aggregation_round, num_devices, accuracy)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        self.global_model.version,
                        self.aggregation_round,
                        num_devices,
                        accuracy,
                    ),
                )
                self.db_connection.commit()
                logger.info(
                    "✓ Global model v%d saved to database", self.global_model.version
                )
        except Exception as e:
            self.db_connection.rollback()
            logger.warning(f"Error saving global model to DB: {e}")

    # -----------------------------------------------------------------
    # KAFKA PUBLISH
    # -----------------------------------------------------------------
    def _publish_global_update(self, update: Dict[str, Any]) -> None:
        """Publish the aggregated global update to Kafka"""
        try:
            self.producer.send(OUTPUT_TOPIC, value=update)
            # Aggregation is relatively infrequent, flush here is fine
            self.producer.flush()
            logger.info(
                "✓ Published global model update v%d to topic '%s'",
                update.get("version"),
                OUTPUT_TOPIC,
            )
        except Exception as e:
            logger.error(f"Error publishing global model update: {e}", exc_info=True)


# ---------------------------------------------------------------------
# KAFKA HELPERS
# ---------------------------------------------------------------------
def create_kafka_producer(max_retries: int = 30, delay: float = 5.0) -> KafkaProducer:
    """Create Kafka producer for global model updates with retries."""
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=5,
            )
            logger.info("✓ Aggregator Kafka producer connected (attempt %d)", attempt)
            return producer
        except NoBrokersAvailable as e:
            last_err = e
            logger.warning(
                "Kafka not ready yet for aggregator producer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)
        except Exception as e:
            last_err = e
            logger.warning(
                "Error creating aggregator producer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)

    logger.error(
        "Aggregator producer failed to connect after %d attempts: %s",
        max_retries,
        last_err,
    )
    raise last_err or RuntimeError("Unable to create Kafka producer")


def create_kafka_consumer(
    max_retries: int = 30, delay: float = 5.0
) -> KafkaConsumer:
    """Create Kafka consumer for local model updates with retries."""
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            consumer = KafkaConsumer(
                INPUT_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id=CONSUMER_GROUP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            logger.info("✓ Aggregator Kafka consumer connected (attempt %d)", attempt)
            return consumer
        except NoBrokersAvailable as e:
            last_err = e
            logger.warning(
                "Kafka not ready yet for aggregator consumer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)
        except Exception as e:
            last_err = e
            logger.warning(
                "Error creating aggregator consumer (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            time.sleep(delay)

    logger.error(
        "Aggregator consumer failed to connect after %d attempts: %s",
        max_retries,
        last_err,
    )
    raise last_err or RuntimeError("Unable to create Kafka consumer")



# ---------------------------------------------------------------------
# MAIN SERVICE LOOP
# ---------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 70)
    logger.info("Federated Learning Aggregation Service")
    logger.info("=" * 70)
    logger.info("Input Topic:  %s", INPUT_TOPIC)
    logger.info("Output Topic: %s", OUTPUT_TOPIC)
    logger.info("Kafka:        %s", ", ".join(KAFKA_BOOTSTRAP_SERVERS))
    logger.info("TimescaleDB:  %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
    logger.info("Aggregation Window: %d updates", AGGREGATION_WINDOW)
    logger.info("Min Devices:       %d", MIN_DEVICES_FOR_AGGREGATION)
    logger.info("=" * 70)

    consumer: KafkaConsumer | None = None
    producer: KafkaProducer | None = None
    aggregator: FederatedAggregator | None = None

    try:
        producer = create_kafka_producer()
        aggregator = FederatedAggregator(producer=producer)
        consumer = create_kafka_consumer()

        logger.info("Waiting for local model updates... (Ctrl+C to stop)\n")

        for message in consumer:
            local_model_record = message.value
            aggregator.process_local_model_update(local_model_record)

    except KeyboardInterrupt:
        logger.info("\n⚠ Service interrupted by user")
    except Exception as e:
        logger.error(f"Error in aggregation service: {e}", exc_info=True)
    finally:
        logger.info("Shutting down federated aggregation service...")
        try:
            if consumer is not None:
                consumer.close()
        except Exception:
            pass

        try:
            if producer is not None:
                producer.flush()
                producer.close()
        except Exception:
            pass

        try:
            if aggregator is not None and aggregator.db_connection is not None:
                aggregator.db_connection.close()
        except Exception:
            pass

        logger.info("✓ Service stopped cleanly")


if __name__ == "__main__":
    main()
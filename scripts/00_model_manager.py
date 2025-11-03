"""
Model Manager - Save, Load, and Version Management for Local and Global Models
Manages model lifecycle, versioning, and performance tracking
"""

import json
import logging
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Model storage paths
MODELS_DIR = Path('models')
LOCAL_MODELS_DIR = MODELS_DIR / 'local'
GLOBAL_MODELS_DIR = MODELS_DIR / 'global'
METADATA_DIR = MODELS_DIR / 'metadata'

# Create directories
for directory in [MODELS_DIR, LOCAL_MODELS_DIR, GLOBAL_MODELS_DIR, METADATA_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


class ModelMetadata:
    """Metadata for model tracking"""
    
    def __init__(self, model_type: str, version: int):
        self.model_type = model_type  # 'local' or 'global'
        self.version = version
        self.created_at = datetime.now()
        self.device_id = None
        self.accuracy = 0.0
        self.samples_processed = 0
        self.training_duration = 0.0
        self.aggregation_round = 0
        self.num_devices_aggregated = 0
        self.tags = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'model_type': self.model_type,
            'version': self.version,
            'created_at': self.created_at.isoformat(),
            'device_id': self.device_id,
            'accuracy': float(self.accuracy),
            'samples_processed': int(self.samples_processed),
            'training_duration': float(self.training_duration),
            'aggregation_round': int(self.aggregation_round),
            'num_devices_aggregated': int(self.num_devices_aggregated),
            'tags': self.tags
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'ModelMetadata':
        """Create from dictionary"""
        metadata = ModelMetadata(data['model_type'], data['version'])
        metadata.created_at = datetime.fromisoformat(data['created_at'])
        metadata.device_id = data.get('device_id')
        metadata.accuracy = data.get('accuracy', 0.0)
        metadata.samples_processed = data.get('samples_processed', 0)
        metadata.training_duration = data.get('training_duration', 0.0)
        metadata.aggregation_round = data.get('aggregation_round', 0)
        metadata.num_devices_aggregated = data.get('num_devices_aggregated', 0)
        metadata.tags = data.get('tags', [])
        return metadata


class LocalModel:
    """Local model wrapper"""
    
    def __init__(self, device_id: str, version: int):
        self.device_id = device_id
        self.version = version
        self.metadata = ModelMetadata('local', version)
        self.metadata.device_id = device_id
        self.weights = None
        self.parameters = {}
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Save model to disk"""
        if path is None:
            path = LOCAL_MODELS_DIR / f"device_{self.device_id}_v{self.version}.pkl"
        
        try:
            with open(path, 'wb') as f:
                pickle.dump(self, f)
            
            # Save metadata
            metadata_path = METADATA_DIR / f"device_{self.device_id}_v{self.version}_meta.json"
            with open(metadata_path, 'w') as f:
                json.dump(self.metadata.to_dict(), f, indent=2)
            
            logger.info(f"✓ Local model saved: {path.name}")
            return path
        
        except Exception as e:
            logger.error(f"✗ Error saving local model: {e}")
            raise
    
    @staticmethod
    def load(path: Path) -> Optional['LocalModel']:
        """Load model from disk"""
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"✗ Error loading local model: {e}")
            return None


class GlobalModel:
    """Global model wrapper"""
    
    def __init__(self, version: int):
        self.version = version
        self.metadata = ModelMetadata('global', version)
        self.weights = None
        self.parameters = {}
        self.device_contributions = {}  # Track which devices contributed
    
    def save(self, path: Optional[Path] = None) -> Path:
        """Save model to disk"""
        if path is None:
            path = GLOBAL_MODELS_DIR / f"global_model_v{self.version}.pkl"
        
        try:
            with open(path, 'wb') as f:
                pickle.dump(self, f)
            
            # Save metadata
            metadata_path = METADATA_DIR / f"global_v{self.version}_meta.json"
            with open(metadata_path, 'w') as f:
                json.dump(self.metadata.to_dict(), f, indent=2)
            
            logger.info(f"✓ Global model saved: {path.name}")
            return path
        
        except Exception as e:
            logger.error(f"✗ Error saving global model: {e}")
            raise
    
    @staticmethod
    def load(path: Path) -> Optional['GlobalModel']:
        """Load model from disk"""
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"✗ Error loading global model: {e}")
            return None


class ModelManager:
    """Manage model lifecycle"""
    
    def __init__(self):
        self.local_models_registry = {}  # device_id -> latest_version
        self.global_models_registry = {}  # version -> path
        self._load_registries()
    
    def _load_registries(self) -> None:
        """Load existing model registries"""
        try:
            # Load local models
            for model_file in LOCAL_MODELS_DIR.glob('device_*.pkl'):
                parts = model_file.stem.split('_')
                if len(parts) >= 3:
                    device_id = parts[1]
                    version = int(parts[2][1:])  # Remove 'v' prefix
                    
                    if device_id not in self.local_models_registry or \
                       version > self.local_models_registry[device_id]:
                        self.local_models_registry[device_id] = version
            
            # Load global models
            for model_file in GLOBAL_MODELS_DIR.glob('global_model_v*.pkl'):
                parts = model_file.stem.split('_')
                if len(parts) >= 3:
                    version = int(parts[2][1:])  # Remove 'v' prefix
                    self.global_models_registry[version] = model_file
            
            logger.info(f"✓ Loaded model registry:")
            logger.info(f"  Local models: {len(self.local_models_registry)} devices")
            logger.info(f"  Global models: {len(self.global_models_registry)} versions")
        
        except Exception as e:
            logger.warning(f"Could not load model registry: {e}")
    
    def create_local_model(self, device_id: str, accuracy: float = 0.0,
                          samples_processed: int = 0, **metadata) -> LocalModel:
        """Create new local model"""
        version = self.local_models_registry.get(device_id, 0) + 1
        model = LocalModel(device_id, version)
        model.metadata.accuracy = accuracy
        model.metadata.samples_processed = samples_processed
        
        for key, value in metadata.items():
            setattr(model.metadata, key, value)
        
        return model
    
    def create_global_model(self, accuracy: float = 0.0,
                           aggregation_round: int = 0,
                           num_devices: int = 0, **metadata) -> GlobalModel:
        """Create new global model"""
        version = max(self.global_models_registry.keys()) if self.global_models_registry else 0
        version += 1
        
        model = GlobalModel(version)
        model.metadata.accuracy = accuracy
        model.metadata.aggregation_round = aggregation_round
        model.metadata.num_devices_aggregated = num_devices
        
        for key, value in metadata.items():
            setattr(model.metadata, key, value)
        
        return model
    
    def save_local_model(self, model: LocalModel) -> Path:
        """Save local model and update registry"""
        path = model.save()
        self.local_models_registry[model.device_id] = model.version
        return path
    
    def save_global_model(self, model: GlobalModel) -> Path:
        """Save global model and update registry"""
        path = model.save()
        self.global_models_registry[model.version] = path
        return path
    
    def load_local_model(self, device_id: str, version: Optional[int] = None) -> Optional[LocalModel]:
        """Load local model for device"""
        if version is None:
            # Load latest version
            version = self.local_models_registry.get(device_id)
        
        if version is None:
            logger.warning(f"No model found for device {device_id}")
            return None
        
        path = LOCAL_MODELS_DIR / f"device_{device_id}_v{version}.pkl"
        return LocalModel.load(path)
    
    def load_global_model(self, version: Optional[int] = None) -> Optional[GlobalModel]:
        """Load global model"""
        if version is None:
            # Load latest version
            version = max(self.global_models_registry.keys()) if self.global_models_registry else None
        
        if version is None:
            logger.warning("No global model found")
            return None
        
        path = self.global_models_registry.get(version)
        if path is None:
            return None
        
        return GlobalModel.load(path)
    
    def get_local_model_info(self, device_id: str) -> Optional[Dict]:
        """Get info about latest local model for device"""
        version = self.local_models_registry.get(device_id)
        if version is None:
            return None
        
        metadata_path = METADATA_DIR / f"device_{device_id}_v{version}_meta.json"
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def get_global_model_info(self, version: Optional[int] = None) -> Optional[Dict]:
        """Get info about global model"""
        if version is None:
            version = max(self.global_models_registry.keys()) if self.global_models_registry else None
        
        if version is None:
            return None
        
        metadata_path = METADATA_DIR / f"global_v{version}_meta.json"
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def list_local_models(self, device_id: Optional[str] = None) -> List[Dict]:
        """List all local models"""
        models = []
        
        for model_file in sorted(LOCAL_MODELS_DIR.glob('device_*.pkl')):
            parts = model_file.stem.split('_')
            if len(parts) >= 3:
                dev_id = parts[1]
                version = int(parts[2][1:])
                
                if device_id and dev_id != device_id:
                    continue
                
                metadata_path = METADATA_DIR / f"device_{dev_id}_v{version}_meta.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        meta = json.load(f)
                        models.append(meta)
        
        return models
    
    def list_global_models(self) -> List[Dict]:
        """List all global models"""
        models = []
        
        for model_file in sorted(GLOBAL_MODELS_DIR.glob('global_model_v*.pkl')):
            parts = model_file.stem.split('_')
            if len(parts) >= 3:
                version = int(parts[2][1:])
                
                metadata_path = METADATA_DIR / f"global_v{version}_meta.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        meta = json.load(f)
                        models.append(meta)
        
        return models
    
    def cleanup_old_models(self, keep_local: int = 5, keep_global: int = 10) -> None:
        """Clean up old model versions"""
        logger.info("Cleaning up old models...")
        
        # Clean local models per device
        for device_id in self.local_models_registry:
            device_models = sorted(
                [f for f in LOCAL_MODELS_DIR.glob(f'device_{device_id}_v*.pkl')],
                key=lambda x: int(x.stem.split('v')[-1]),
                reverse=True
            )
            
            for old_model in device_models[keep_local:]:
                try:
                    old_model.unlink()
                    logger.info(f"  Deleted old local model: {old_model.name}")
                except:
                    pass
        
        # Clean global models
        global_models = sorted(
            GLOBAL_MODELS_DIR.glob('global_model_v*.pkl'),
            key=lambda x: int(x.stem.split('v')[-1]),
            reverse=True
        )
        
        for old_model in global_models[keep_global:]:
            try:
                old_model.unlink()
                logger.info(f"  Deleted old global model: {old_model.name}")
            except:
                pass


def main():
    """Demo model manager usage"""
    logger.info("=" * 70)
    logger.info("Model Manager Demo")
    logger.info("=" * 70)
    
    manager = ModelManager()
    
    # Create and save a local model
    logger.info("\n1. Creating local model for device_0...")
    local_model = manager.create_local_model(
        'device_0',
        accuracy=0.92,
        samples_processed=1000
    )
    manager.save_local_model(local_model)
    
    # Create and save a global model
    logger.info("\n2. Creating global model...")
    global_model = manager.create_global_model(
        accuracy=0.89,
        aggregation_round=1,
        num_devices=5
    )
    manager.save_global_model(global_model)
    
    # List models
    logger.info("\n3. Listing all local models...")
    local_models = manager.list_local_models()
    for model in local_models:
        logger.info(f"  {model['device_id']} v{model['version']}: accuracy={model['accuracy']:.2%}")
    
    logger.info("\n4. Listing all global models...")
    global_models = manager.list_global_models()
    for model in global_models:
        logger.info(f"  Global v{model['version']}: accuracy={model['accuracy']:.2%}, "
                   f"devices={model['num_devices_aggregated']}")
    
    # Get model info
    logger.info("\n5. Getting model info...")
    info = manager.get_local_model_info('device_0')
    logger.info(f"  Local model info: {json.dumps(info, indent=2)}")
    
    logger.info("\n✓ Demo complete")


if __name__ == '__main__':
    main()

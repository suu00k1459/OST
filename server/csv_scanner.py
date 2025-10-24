"""
CSV Device Scanner for Federated Learning
Scans the edge_iiot_processed directory and discovers devices from CSV files
"""

import os
from pathlib import Path
import pandas as pd
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


class CSVDeviceScanner:
    """
    Scans for device CSV files and provides device metadata
    """
    
    def __init__(self, csv_directory: str = None):
        """
        Initialize scanner with CSV directory path
        
        Args:
            csv_directory: Path to directory containing device_*.csv files
        """
        if csv_directory is None:
            # Default path: data/processed/
            csv_directory = Path(__file__).parent.parent / 'data' / 'processed'
        
        self.csv_directory = Path(csv_directory)
        self.devices = {}
        self.device_count = 0
    
    def scan(self) -> Tuple[int, List[Dict]]:
        """
        Scan directory for device CSV files
        
        Returns:
            Tuple of (device_count, devices_list)
        """
        if not self.csv_directory.exists():
            logger.error(f"Directory not found: {self.csv_directory}")
            return 0, []
        
        devices_list = []
        device_files = sorted(self.csv_directory.glob('device_*.csv'))
        
        for csv_file in device_files:
            try:
                # Extract device ID from filename (device_0.csv -> 0)
                device_id = int(csv_file.stem.split('_')[1])
                
                # Get file stats
                file_size = csv_file.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
                
                # Load CSV to get sample count
                try:
                    df = pd.read_csv(csv_file, nrows=5)  # Only read first 5 rows for speed
                    # Count actual rows more efficiently
                    row_count = sum(1 for _ in open(csv_file)) - 1  # -1 for header
                    feature_count = len(df.columns)
                except Exception as e:
                    logger.warning(f"Could not read {csv_file}: {e}")
                    row_count = 0
                    feature_count = 0
                
                device_info = {
                    'device_id': device_id,
                    'device_name': f'device_{device_id}',
                    'csv_file': csv_file.name,
                    'csv_path': str(csv_file),
                    'file_size_mb': round(file_size_mb, 2),
                    'data_samples': row_count,
                    'features': feature_count,
                    'status': 'idle'
                }
                
                devices_list.append(device_info)
                self.devices[device_id] = device_info
                
                logger.info(f"Found device_{device_id}: {row_count} samples, {feature_count} features")
            
            except Exception as e:
                logger.error(f"Error processing {csv_file}: {e}")
                continue
        
        self.device_count = len(devices_list)
        logger.info(f"Scan complete: Found {self.device_count} devices")
        
        return self.device_count, devices_list
    
    def get_device_info(self, device_id: int) -> Dict:
        """Get info for specific device"""
        return self.devices.get(device_id, None)
    
    def get_all_devices(self) -> List[Dict]:
        """Get all discovered devices"""
        return list(self.devices.values())
    
    def get_device_csv_path(self, device_id: int) -> str:
        """Get CSV file path for specific device"""
        device = self.devices.get(device_id)
        return device['csv_path'] if device else None
    
    def get_total_samples(self) -> int:
        """Get total data samples across all devices"""
        return sum(d['data_samples'] for d in self.devices.values())
    
    def get_device_count(self) -> int:
        """Get total number of devices found"""
        return self.device_count


# Create global scanner instance
csv_scanner = None


def initialize_scanner(csv_directory: str = None) -> CSVDeviceScanner:
    """
    Initialize the global CSV device scanner
    
    Args:
        csv_directory: Optional path to CSV directory
    
    Returns:
        Initialized CSVDeviceScanner
    """
    global csv_scanner
    csv_scanner = CSVDeviceScanner(csv_directory)
    return csv_scanner


def get_scanner() -> CSVDeviceScanner:
    """Get the global CSV device scanner"""
    global csv_scanner
    if csv_scanner is None:
        csv_scanner = CSVDeviceScanner()
    return csv_scanner

#!/usr/bin/env python3
"""
Convert chunked NPZ/NPY files to device_*.csv format for the Kafka Producer.

Input (by default):
  data/processed/chunks/
    - X_chunk_0.npz, X_chunk_1.npz, ...
    - y_chunk_0.npy, y_chunk_1.npy, ...

Output:
  data/processed/
    - device_0.csv, device_1.csv, ..., device_N.csv

These CSVs are then consumed by:
    scripts/02_kafka_producer.py --source data/processed
"""

import sys
import logging
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import pandas as pd

# -----------------------------------------------------
# LOGGING
# -----------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_chunks(chunks_dir: Path) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Load all X_chunk_*.npz and y_chunk_*.npy files and combine them."""
    if not chunks_dir.exists():
        logger.error(f"Chunks directory not found: {chunks_dir}")
        return None, None

    # Find all chunk files
    x_chunks = sorted(chunks_dir.glob("X_chunk_*.npz"))
    y_chunks = sorted(chunks_dir.glob("y_chunk_*.npy"))

    if not x_chunks or not y_chunks:
        logger.error(f"No chunk files found in {chunks_dir}")
        return None, None

    logger.info(f"Found {len(x_chunks)} X chunks and {len(y_chunks)} y chunks")

    # ---- Load and combine X chunks (dense matrices) ----
    X_list = []
    for x_chunk_file in x_chunks:
        logger.info(f"Loading {x_chunk_file.name}...")
        x_chunk = np.load(x_chunk_file)
        # Convention: NPZ contains dense matrix under key 'X'
        if "X" not in x_chunk:
            logger.error(f"File {x_chunk_file} does not contain key 'X'")
            return None, None
        x_chunk_data = x_chunk["X"]
        X_list.append(x_chunk_data)

    X = np.vstack(X_list) if X_list else None
    if X is None:
        logger.error("Combined X is empty after loading chunks")
        return None, None
    logger.info(f"Combined X shape: {X.shape}")

    # ---- Load and combine y chunks ----
    y_list = []
    for y_chunk_file in y_chunks:
        logger.info(f"Loading {y_chunk_file.name}...")
        y_chunk = np.load(y_chunk_file)
        y_list.append(y_chunk)

    y = np.concatenate(y_list) if y_list else None
    if y is None:
        logger.error("Combined y is empty after loading chunks")
        return None, None
    logger.info(f"Combined y shape: {y.shape}")

    if X.shape[0] != y.shape[0]:
        logger.warning(
            f"X samples ({X.shape[0]}) != y samples ({y.shape[0]}). "
            "Using the minimum common length."
        )
        n = min(X.shape[0], y.shape[0])
        X = X[:n]
        y = y[:n]

    return X, y


def infer_feature_names(num_features: int):
    """Generate feature names based on Edge-IIoT dataset structure (approx)."""
    base_features = [
        "flow_duration", "Header_length", "Protocol Type", "Duration",
        "Rate", "Srate", "Drate", "fin_flag_number", "syn_flag_number",
        "rst_flag_number", "psh_flag_number", "ack_flag_number",
        "urg_flag_number", "cwr_flag_number", "ece_flag_number",
        "Src_Port", "Dst_Port", "Protocol", "Timestamp", "TCP_Length",
        "TCP_Flags", "Sequence_Num", "Ack_Num", "TCP_Win_Size",
        "TCP_Chksum", "TCP_Urgent_Ptr", "TCP_Options", "ICMP_Type",
        "ICMP_Code", "ICMP_Checksum", "ICMP_ID", "ICMP_Sequence",
        "UDP_Length", "UDP_Checksum", "ARP_Hard_Type", "ARP_Proto_Type",
        "ARP_Hard_Size", "ARP_Proto_Size", "ARP_Opcode", "ARP_Src_IP",
        "ARP_Src_MAC", "ARP_Dst_IP", "ARP_Dst_MAC", "IPv6_Version",
        "IPv6_Traffic_Class", "IPv6_Flow_Label", "IPv6_Payload_Length",
        "IPv6_Next_Header", "IPv6_Hop_Limit", "IGMP_Type", "IGMP_Max_Resp_Time",
        "DNS_ID", "DNS_QR", "DNS_OPCODE", "DNS_AA", "DNS_TC", "DNS_RD",
        "DHCP_Opcode", "DHCP_Hardware_Type", "DHCP_Hardware_Length",
        "DHCP_Hops", "DHCP_Transaction_ID", "DHCP_Seconds", "DHCP_Flags",
        "NTP_Timestamp", "NTP_Version", "MDNS_ID", "SSH_Version",
        "TLS_Version", "Packet_Loss", "Latency", "Throughput",
    ]

    features = list(base_features)

    # If we have more features than names, generate additional generic ones
    while len(features) < num_features:
        features.append(f"feature_{len(features)}")

    return features[:num_features]


def create_device_csvs(
    X: np.ndarray,
    y: np.ndarray,
    output_dir: Path,
    num_devices: int = 2400,
    rows_per_device: int = None,
) -> int:
    """
    Create individual device_*.csv files from combined data.

    Args:
        X: Feature matrix (num_samples, num_features)
        y: Labels (num_samples,)
        output_dir: Directory to save device CSV files
        num_devices: Number of devices to simulate
        rows_per_device: Rows per device (auto-calculated if None)

    Returns:
        int: number of device files actually created
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    num_samples, num_features = X.shape

    if rows_per_device is None:
        rows_per_device = max(1, num_samples // num_devices)

    logger.info(f"Creating up to {num_devices} device files")
    logger.info(f"Rows per device (approx): {rows_per_device}")
    logger.info(f"Total samples available: {num_samples}")

    # Generate feature names
    feature_names = infer_feature_names(num_features)

    device_index = 0
    sample_index = 0

    while device_index < num_devices and sample_index < num_samples:
        remaining_devices = num_devices - device_index
        remaining_samples = num_samples - sample_index
        rows_for_device = min(rows_per_device, remaining_samples)

        if rows_for_device <= 0:
            break

        # Slice data for this device
        X_device = X[sample_index : sample_index + rows_for_device]
        y_device = y[sample_index : sample_index + rows_for_device]

        df_device = pd.DataFrame(
            X_device,
            columns=feature_names[: X_device.shape[1]],
        )
        df_device["label"] = y_device
        df_device["timestamp"] = pd.date_range(
            start="2025-01-01", periods=len(df_device), freq="1S"
        )

        device_file = output_dir / f"device_{device_index}.csv"
        df_device.to_csv(device_file, index=False)

        if (device_index + 1) % 100 == 0:
            logger.info(f"Created {device_index + 1} device files so far...")

        sample_index += rows_for_device
        device_index += 1

    logger.info(f"Successfully created {device_index} device CSV files in {output_dir}")
    return device_index


def main() -> int:
    """Main conversion process."""
    # Repo root / scripts / (this file)
    repo_root = Path(__file__).resolve().parent.parent

    chunks_dir = repo_root / "data" / "processed" / "chunks"
    output_dir = repo_root / "data" / "processed"

    logger.info("=" * 70)
    logger.info("CHUNK → DEVICE CSV CONVERSION")
    logger.info("=" * 70)
    logger.info(f"Chunks directory: {chunks_dir}")
    logger.info(f"Output directory: {output_dir}")

    X, y = load_chunks(chunks_dir)

    if X is None or y is None:
        logger.error("Failed to load chunk files")
        return 1

    num_devices = create_device_csvs(X, y, output_dir)

    logger.info("=" * 70)
    logger.info(f"CONVERSION COMPLETE - Created {num_devices} device CSV files")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Next step: start the Kafka producer (inside Docker):")
    logger.info("  docker compose up -d kafka-producer")
    logger.info("or from host (if you run it locally):")
    logger.info("  python scripts/02_kafka_producer.py --source data/processed")
    logger.info("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""
FLEAD Data Preprocessing Script

Headless version of `notebooks/Data PreProcessing.ipynb`.

Pipeline:
  1. Ensure Kaggle credentials (~/.kaggle/kaggle.json)
  2. Download Edge-IIoTSet dataset from Kaggle into data/raw/
  3. Load all CSVs, simple cleaning, pick DNN-EdgeIIoT-dataset
  4. Ensure a `device_id` column
  5. Run sklearn-based, chunked preprocessing to create:
       - sparse feature chunks: data/processed/chunks/X_chunk_*.npz
       - label chunks:         data/processed/chunks/y_chunk_*.npy
       - merged_data.csv, preprocessor.pkl, processing_summary.json

This script is called automatically by ./start (Linux/WSL/macOS)
and START.bat (Windows) if `data/processed/chunks/` does not exist.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import numpy as np
import pandas as pd
from kaggle.api.kaggle_api_extended import KaggleApi

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, FunctionTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from scipy.sparse import issparse, save_npz

# Optional but nice to have
try:
    import joblib
except ImportError:  # pragma: no cover
    joblib = None


# ---------------------------------------------------------------------
# Paths & Kaggle config
# ---------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
CHUNKS_DIR = DATA_PROCESSED / "chunks"

# Make sure Kaggle API looks in ~/.kaggle
os.environ["KAGGLE_CONFIG_DIR"] = os.path.expanduser("~/.kaggle")


# ---------------------------------------------------------------------
# STEP 1 – Download from Kaggle
# ---------------------------------------------------------------------
def ensure_kaggle_credentials() -> None:
    kaggle_dir = Path(os.environ["KAGGLE_CONFIG_DIR"])
    cfg = kaggle_dir / "kaggle.json"
    if not cfg.exists():
        raise FileNotFoundError(
            f"kaggle.json not found at {cfg}. "
            "Your start script should copy it from ./kaggle/kaggle.json."
        )


def download_edge_iiot() -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    existing_csv = list(DATA_RAW.glob("*.csv"))
    if len(existing_csv) >= 3:
        print("[INFO] Raw CSV files already present in data/raw, skipping Kaggle download.")
        for f in sorted(existing_csv):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"    {f.name} ({size_mb:.2f} MB)")
        return

    print("[INFO] Downloading Edge-IIoTSet dataset from Kaggle...")
    api = KaggleApi()
    api.authenticate()

    api.dataset_download_files(
        "sibasispradhan/edge-iiotset-dataset",
        path=str(DATA_RAW),
        unzip=True,
    )

    print("[INFO] Download complete. Files in data/raw:")
    for f in sorted(DATA_RAW.glob("*.csv")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"    {f.name} ({size_mb:.2f} MB)")


# ---------------------------------------------------------------------
# STEP 2 – Basic loading & cleaning
# ---------------------------------------------------------------------
def load_all_datasets() -> Dict[str, pd.DataFrame]:
    csv_files = sorted(DATA_RAW.glob("*.csv"))
    if not csv_files:
        raise RuntimeError("No CSV files found in data/raw after Kaggle download.")

    datasets: Dict[str, pd.DataFrame] = {}
    print(f"[INFO] Found {len(csv_files)} CSV files in {DATA_RAW}")
    for csv_file in csv_files:
        print(f"[INFO] Loading {csv_file.name} ...")
        df = pd.read_csv(csv_file)
        datasets[csv_file.stem] = df
        print(f"    Shape: {df.shape}, columns: {len(df.columns)}")
    return datasets


def clean_dataset(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Simple cleaning used in the notebook."""
    print(f"[CLEAN] Cleaning {name} ...")
    initial_rows = len(df)

    # Remove duplicates
    df_clean = df.drop_duplicates().reset_index(drop=True)
    duplicates = initial_rows - len(df_clean)
    if duplicates > 0:
        print(f"    Removed {duplicates} duplicate rows")

    # Drop rows with any missing values
    rows_before = len(df_clean)
    df_clean = df_clean.dropna()
    missing_removed = rows_before - len(df_clean)
    if missing_removed > 0:
        print(f"    Removed {missing_removed} rows with missing values")

    # Convert object columns to numeric where possible
    converted_success = 0
    for col in df_clean.columns:
        if df_clean[col].dtype == "object":
            try:
                converted = pd.to_numeric(df_clean[col], errors="coerce")
                if converted.notna().sum() > 0:
                    df_clean[col] = converted
                    converted_success += 1
            except Exception:
                pass
    if converted_success > 0:
        print(f"    Converted {converted_success} object columns to numeric")

    # Add source dataset indicator
    df_clean["dataset_source"] = name
    print(f"    Final: {len(df_clean):,} rows ({100 * len(df_clean) / initial_rows:.1f}% retained)")
    return df_clean


def build_merged_dataset(datasets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    cleaned: Dict[str, pd.DataFrame] = {}
    for name, df in datasets.items():
        cleaned[name] = clean_dataset(df, name)

    print("\n[INFO] Cleaned datasets:")
    for key in cleaned.keys():
        print(f"    - {key}")

    # Use DNN-EdgeIIoT-dataset as in notebook
    if "DNN-EdgeIIoT-dataset" not in cleaned:
        raise KeyError(
            "Expected 'DNN-EdgeIIoT-dataset' in cleaned datasets but did not find it. "
            "Available: " + ", ".join(cleaned.keys())
        )

    df_merged = cleaned["DNN-EdgeIIoT-dataset"].copy()
    print(f"\n[INFO] Using DNN-EdgeIIoT-dataset, shape: {df_merged.shape}")

    # Drop columns that are completely NaN
    all_nan_cols = df_merged.columns[df_merged.isnull().all()].tolist()
    if all_nan_cols:
        print(f"[CLEAN] Dropping {len(all_nan_cols)} all-NaN columns.")
        df_merged = df_merged.drop(columns=all_nan_cols)

    print(f"[INFO] After dropping all-NaN: {df_merged.shape}")
    return df_merged


def ensure_device_id(df_merged: pd.DataFrame) -> pd.DataFrame:
    print("[INFO] Ensuring device_id column...")

    device_col_candidates = [
        "device_id",
        "Device_ID",
        "DeviceID",
        "device",
        "Device",
        "id",
        "ID",
        "src_ip",
        "dst_ip",
        "ip.src",
        "ip.dst",
    ]

    device_col = None
    for col in device_col_candidates:
        if col in df_merged.columns and df_merged[col].notna().sum() > 0:
            device_col = col
            break

    df = df_merged.copy()
    if device_col is None:
        print("  No device identifier column found; creating synthetic device_id.")
        num_devices = max(5, len(df) // 1000)
        df["device_id"] = df.groupby("dataset_source").cumcount() % num_devices
        print(f"  Created {num_devices} synthetic devices.")
    else:
        print(f"  Using existing device column: {device_col}")
        df = df.rename(columns={device_col: "device_id"})

    print("[INFO] Device distribution summary:")
    print(df["device_id"].value_counts().sort_index().head(10))
    return df


# ---------------------------------------------------------------------
# STEP 3 – Feature preprocessing (chunked pipeline)
# ---------------------------------------------------------------------
LABEL_GUESS_CANDIDATES = [
    "attack",
    "Attack",
    "Label",
    "label",
    "class",
    "Class",
    "Attack_type",
    "AttackType",
    "Category",
]


def guess_label_column(df: pd.DataFrame, override: Optional[str] = None) -> str:
    if override and override in df.columns:
        return override
    for c in LABEL_GUESS_CANDIDATES:
        if c in df.columns:
            return c
    # fallback: last column
    return df.columns[-1]


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [
        str(c).strip().replace(" ", "_").replace("-", "_") for c in df.columns
    ]
    return df


def to_binary_labels(y: pd.Series) -> np.ndarray:
    y_norm = y.astype(str).str.lower().str.strip()
    attack = ~(y_norm.isin(["benign", "normal", "0"]))
    return attack.astype(int).to_numpy()


def to_multiclass_labels(y: pd.Series) -> Tuple[np.ndarray, List[str]]:
    classes, uniques = pd.factorize(y.astype(str).str.strip())
    return classes.astype(int), [str(u) for u in uniques]


@dataclass
class FittedPreprocessor:
    pipeline: Pipeline
    features: List[str]
    label_name: str
    classes: Optional[List[str]] = None


def _detect_feature_columns(X: pd.DataFrame) -> Tuple[List[str], List[str]]:
    numeric_cols = X.select_dtypes(
        include=["number", "float", "int", "Int64", "Float64"]
    ).columns.tolist()
    cat_cols = [c for c in X.columns if c not in numeric_cols]
    return numeric_cols, cat_cols


def _cast_to_str(X):
    if isinstance(X, pd.DataFrame):
        return X.astype(str)
    return X.astype(str)


def build_pipeline(
    df: pd.DataFrame, label_col: str
) -> Tuple[Pipeline, List[str], List[str], List[str]]:
    X = df.drop(columns=[label_col])

    reserved = {"device_id", "dataset_source"}
    X = X.drop(columns=[c for c in reserved if c in X.columns], errors="ignore")

    X = X.dropna(axis=1, how="all")

    numeric_cols, cat_cols = _detect_feature_columns(X)

    numeric_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="mean")),
        ]
    )

    # Safe OneHotEncoder across sklearn versions
    try:
        ohe = OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=True,
            dtype=np.float32,
            min_frequency=0.01,
        )
    except TypeError:
        try:
            ohe = OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=True,
                dtype=np.float32,
                max_categories=50,
            )
        except TypeError:
            try:
                ohe = OneHotEncoder(
                    handle_unknown="ignore", sparse=True, dtype=np.float32
                )
            except TypeError:
                ohe = OneHotEncoder(handle_unknown="ignore")

    categorical_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("cast_str", FunctionTransformer(_cast_to_str, validate=False)),
            ("ohe", ohe),
        ]
    )

    pre = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_cols),
            ("cat", categorical_pipeline, cat_cols),
        ],
        remainder="drop",
    )

    pipe = Pipeline([("pre", pre)])
    return pipe, X.columns.tolist(), numeric_cols, cat_cols


def fit_on_sample_and_transform_in_chunks(
    df: pd.DataFrame,
    task_mode: str = "binary",
    label_override: Optional[str] = None,
    sample_n: int = 200_000,
    chunk_size: int = 100_000,
    out_dir: Optional[Path] = None,
) -> Tuple[FittedPreprocessor, Dict[str, Any]]:
    df = clean_column_names(df)
    label_col = guess_label_column(df, label_override)

    n_rows = len(df)
    print(f"[PRE] Fitting preprocessing pipeline on sample of {min(sample_n, n_rows)} rows.")
    fit_idx = np.random.RandomState(42).choice(
        n_rows, size=min(sample_n, n_rows), replace=False
    )
    df_fit = df.iloc[fit_idx]

    pipe, features, *_ = build_pipeline(df, label_col)
    pipe.fit(df_fit.drop(columns=[label_col]))

    fitted = FittedPreprocessor(
        pipeline=pipe, features=features, label_name=label_col, classes=None
    )

    out_dir = CHUNKS_DIR if out_dir is None else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    total = n_rows
    n_features = None
    chunk_files: List[Dict[str, Any]] = []
    total_y = 0

    print(f"[PRE] Transforming full dataset in chunks of {chunk_size} rows...")
    xi = 0
    for start in range(0, total, chunk_size):
        end = min(start + chunk_size, total)
        df_chunk = df.iloc[start:end]
        X_chunk = pipe.transform(df_chunk.drop(columns=[label_col]))

        if n_features is None:
            n_features = X_chunk.shape[1]

        if task_mode.lower().startswith("multi"):
            y_chunk, classes = to_multiclass_labels(df_chunk[label_col])
            if fitted.classes is None:
                fitted.classes = classes
        else:
            y_chunk = to_binary_labels(df_chunk[label_col])

        X_path = out_dir / f"X_chunk_{xi}.npz"
        y_path = out_dir / f"y_chunk_{xi}.npy"

        if issparse(X_chunk):
            save_npz(X_path, X_chunk)
        else:
            np.savez(X_path, X=X_chunk.astype(np.float32))

        np.save(y_path, y_chunk.astype(np.int64))

        chunk_files.append(
            {"X": str(X_path), "y": str(y_path), "rows": int(len(y_chunk))}
        )
        total_y += len(y_chunk)

        if xi % 5 == 0:
            print(f"  Saved chunk {xi} [{start} : {end}]")
        xi += 1

    meta: Dict[str, Any] = {
        "total_samples": int(total_y),
        "n_features": int(n_features) if n_features is not None else None,
        "label_name": label_col,
        "out_dir": str(out_dir),
        "chunks": chunk_files,
    }
    return fitted, meta


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    print("==========================================================")
    print("FLEAD DATA PREPROCESSING (Edge-IIoTSet)")
    print("==========================================================")

    ensure_kaggle_credentials()
    download_edge_iiot()

    datasets = load_all_datasets()
    df_merged = build_merged_dataset(datasets)
    df_merged = ensure_device_id(df_merged)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    # Save merged CSV for reference / later use
    merged_csv_path = DATA_PROCESSED / "merged_data.csv"
    print(f"[INFO] Writing merged dataset to {merged_csv_path} ...")
    df_merged.to_csv(merged_csv_path, index=False)

    # Run chunked preprocessing
    preprocessor, meta = fit_on_sample_and_transform_in_chunks(
        df=df_merged,
        task_mode="binary",
        label_override=None,
        sample_n=200_000,
        chunk_size=100_000,
        out_dir=CHUNKS_DIR,
    )

    # Save preprocessor + summary
    if joblib is not None:
        preproc_path = DATA_PROCESSED / "preprocessor.pkl"
        print(f"[INFO] Saving fitted preprocessor to {preproc_path} ...")
        joblib.dump(preprocessor, preproc_path)
    else:
        print("[WARN] joblib not installed, skipping preprocessor.pkl save.")

    summary_path = DATA_PROCESSED / "processing_summary.json"
    print(f"[INFO] Saving preprocessing summary to {summary_path} ...")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print("\n==========================================================")
    print("PREPROCESSING COMPLETE")
    print("----------------------------------------------------------")
    print(f"  Total rows processed:     {meta['total_samples']:,}")
    print(f"  Output feature dimension: {meta['n_features']}")
    print(f"  Label column detected:    {meta['label_name']}")
    print(f"  Chunks directory:         {meta['out_dir']}")
    print(f"  Number of chunks:         {len(meta['chunks'])}")
    print("  Merged CSV:               data/processed/merged_data.csv")
    print("  Preprocessor (if saved):  data/processed/preprocessor.pkl")
    print("  Summary JSON:             data/processed/processing_summary.json")
    print("==========================================================")


if __name__ == "__main__":
    main()

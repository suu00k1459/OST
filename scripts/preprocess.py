"""
Edge-IIoT Dataset Preprocessing Module

This module provides functionality for end-to-end preprocessing of the Edge-IIoT dataset
including data loading, cleaning, merging, feature engineering, and chunked export for
memory-efficient processing of large datasets.

Author: Federated Learning Pipeline
License: MIT
"""

import os
import json
import pickle
import warnings
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, FunctionTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from scipy.sparse import issparse, save_npz, load_npz


# Configuration Constants
LABEL_GUESS_CANDIDATES = ["attack", "Attack", "Label", "label", "class", "Class", 
                          "Attack_type", "AttackType", "Category"]
DEVICE_COLUMN_CANDIDATES = ['device_id', 'Device_ID', 'DeviceID', 'device', 'Device', 
                            'id', 'ID', 'src_ip', 'dst_ip', 'ip.src', 'ip.dst']


@dataclass
class FittedPreprocessor:
    """
    Container for fitted preprocessing pipeline and associated metadata.
    
    Attributes:
        pipeline: Fitted scikit-learn Pipeline object containing all transformations
        features: List of feature column names after excluding identifiers
        label_name: Name of the label/target column in source data
        classes: Optional list of class names for multiclass scenarios
    """
    pipeline: Pipeline
    features: List[str]
    label_name: str
    classes: Optional[List[str]] = None


def guess_label_column(df: pd.DataFrame, override: Optional[str] = None) -> str:
    """
    Auto-detect label column from common naming conventions.
    
    Args:
        df: Input DataFrame to search
        override: Optional explicit column name to use instead of auto-detection
        
    Returns:
        str: Name of detected or overridden label column
    """
    if override and override in df.columns:
        return override
    for candidate in LABEL_GUESS_CANDIDATES:
        if candidate in df.columns:
            return candidate
    return df.columns[-1]


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize column names by removing whitespace and replacing special characters.
    
    Args:
        df: Input DataFrame
        
    Returns:
        pd.DataFrame: DataFrame with standardized column names
    """
    df = df.copy()
    df.columns = [str(c).strip().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df


def to_binary_labels(y: pd.Series) -> np.ndarray:
    """
    Convert arbitrary label values to binary classification format.
    
    Classification rule: Benign/Normal/0 mapped to 0, all other values mapped to 1.
    
    Args:
        y: Input label Series
        
    Returns:
        np.ndarray: Binary labels as integers (0 or 1)
    """
    y_norm = y.astype(str).str.lower().str.strip()
    is_attack = ~(y_norm.isin(["benign", "normal", "0"]))
    return is_attack.astype(int).to_numpy()


def to_multiclass_labels(y: pd.Series) -> Tuple[np.ndarray, List[str]]:
    """
    Convert arbitrary label values to multiclass classification format.
    
    Args:
        y: Input label Series
        
    Returns:
        Tuple of (class_indices: np.ndarray, class_names: List[str])
    """
    class_indices, class_names = pd.factorize(y.astype(str).str.strip())
    return class_indices.astype(int), [str(name) for name in class_names]


def _detect_feature_columns(X: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    Partition columns into numeric and categorical based on dtype.
    
    Args:
        X: Feature DataFrame
        
    Returns:
        Tuple of (numeric_columns: List[str], categorical_columns: List[str])
    """
    numeric_cols = X.select_dtypes(include=["number", "float", "int", "Int64", "Float64"]).columns.tolist()
    categorical_cols = [c for c in X.columns if c not in numeric_cols]
    return numeric_cols, categorical_cols


def _cast_to_str(X):
    """
    Cast array-like input to string type for categorical encoding compatibility.
    
    Args:
        X: Input array or DataFrame
        
    Returns:
        String-typed version of input
    """
    if isinstance(X, pd.DataFrame):
        return X.astype(str)
    return X.astype(str)


def build_pipeline(df: pd.DataFrame, label_col: str) -> Tuple[Pipeline, List[str], List[str], List[str]]:
    """
    Construct scikit-learn preprocessing pipeline with separate numeric and categorical paths.
    
    Numeric Path:
        - SimpleImputer with mean strategy for missing value handling
        
    Categorical Path:
        - SimpleImputer with 'missing' constant for null values
        - FunctionTransformer for type casting to string
        - OneHotEncoder with sparse output and float32 dtype for memory efficiency
        
    Args:
        df: Input DataFrame containing features and labels
        label_col: Name of label column to exclude from features
        
    Returns:
        Tuple of (pipeline: Pipeline, all_features: List[str], numeric_cols: List[str], cat_cols: List[str])
    """
    X = df.drop(columns=[label_col])
    
    # Exclude reserved columns from feature list
    reserved = {"device_id", "dataset_source"}
    X = X.drop(columns=[c for c in reserved if c in X.columns], errors='ignore')
    
    # Drop completely empty columns
    X = X.dropna(axis=1, how='all')
    
    numeric_cols, categorical_cols = _detect_feature_columns(X)
    
    # Numeric preprocessing: mean imputation only
    numeric_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="mean")),
    ])
    
    # OneHotEncoder with version-compatible parameters
    try:
        ohe = OneHotEncoder(
            handle_unknown="ignore",
            sparse_output=True,
            dtype=np.float32,
            min_frequency=0.01
        )
    except TypeError:
        try:
            ohe = OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=True,
                dtype=np.float32,
                max_categories=50
            )
        except TypeError:
            try:
                ohe = OneHotEncoder(
                    handle_unknown="ignore",
                    sparse=True,
                    dtype=np.float32
                )
            except TypeError:
                ohe = OneHotEncoder(handle_unknown="ignore")
    
    # Categorical preprocessing: imputation, casting, encoding
    categorical_pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
        ("cast_str", FunctionTransformer(_cast_to_str, validate=False)),
        ("ohe", ohe),
    ])
    
    # Combine numeric and categorical transformations
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_cols),
            ("cat", categorical_pipeline, categorical_cols),
        ],
        remainder="drop",
    )
    
    pipe = Pipeline([("pre", preprocessor)])
    return pipe, X.columns.tolist(), numeric_cols, categorical_cols


def fit_on_sample_and_transform_in_chunks(
    df: pd.DataFrame,
    task_mode: str = "binary",
    label_override: Optional[str] = None,
    sample_n: int = 200_000,
    chunk_size: int = 100_000,
    out_dir: Optional[Path] = None,
) -> Tuple[FittedPreprocessor, Dict[str, Any]]:
    """
    Memory-efficient preprocessing: fit on sample, transform full dataset in chunks.
    
    This approach prevents out-of-memory errors when processing large datasets by:
    1. Fitting the preprocessing pipeline on a random sample of the full dataset
    2. Applying fitted transformations to the full dataset in configurable chunks
    3. Writing each chunk's features (sparse NPZ) and labels (NPY) directly to disk
    
    Args:
        df: Full input DataFrame
        task_mode: "binary" or "multiclass" for label conversion
        label_override: Explicit label column name (overrides auto-detection)
        sample_n: Number of rows to use for pipeline fitting (default 200,000)
        chunk_size: Number of rows to process in each chunk (default 100,000)
        out_dir: Output directory for chunk files (default ../data/processed/chunks)
        
    Returns:
        Tuple of (preprocessor: FittedPreprocessor, metadata: Dict[str, Any])
        
    Metadata Dictionary Keys:
        - total_samples: Total number of processed rows
        - n_features: Number of features after preprocessing
        - label_name: Detected label column name
        - out_dir: Output directory path as string
        - chunks: List of dicts with X path, y path, and row count per chunk
    """
    df = clean_column_names(df)
    label_col = guess_label_column(df, label_override)
    
    # Fit on random sample
    n_rows = len(df)
    fit_idx = np.random.RandomState(42).choice(n_rows, size=min(sample_n, n_rows), replace=False)
    df_fit = df.iloc[fit_idx]
    
    pipe, features, _, _ = build_pipeline(df, label_col)
    pipe.fit(df_fit.drop(columns=[label_col]))
    
    fitted = FittedPreprocessor(
        pipeline=pipe,
        features=features,
        label_name=label_col,
        classes=None
    )
    
    # Create output directory
    if out_dir is None:
        out_dir = Path('../data/processed/chunks')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Transform in chunks
    n_features = None
    chunk_files = []
    total_processed = 0
    
    for chunk_idx, start in enumerate(range(0, n_rows, chunk_size)):
        end = min(start + chunk_size, n_rows)
        df_chunk = df.iloc[start:end]
        
        # Transform features
        X_chunk = pipe.transform(df_chunk.drop(columns=[label_col]))
        
        # Detect feature dimension from first chunk
        if n_features is None:
            n_features = X_chunk.shape[1]
        
        # Transform labels
        if task_mode.lower().startswith("multi"):
            y_chunk, classes = to_multiclass_labels(df_chunk[label_col])
            if fitted.classes is None:
                fitted.classes = classes
        else:
            y_chunk = to_binary_labels(df_chunk[label_col])
        
        # Save chunk to disk
        X_path = out_dir / f"X_chunk_{chunk_idx}.npz"
        y_path = out_dir / f"y_chunk_{chunk_idx}.npy"
        
        if issparse(X_chunk):
            save_npz(X_path, X_chunk)
        else:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                np.savez(X_path, X=X_chunk.astype(np.float32))
        
        np.save(y_path, y_chunk.astype(np.int64))
        
        chunk_files.append({
            "X": str(X_path),
            "y": str(y_path),
            "rows": int(len(y_chunk))
        })
        total_processed += len(y_chunk)
        
        if chunk_idx % 5 == 0:
            print(f"  Processed chunks up to index {chunk_idx} ({end}/{n_rows} rows)")
    
    metadata = {
        "total_samples": int(total_processed),
        "n_features": int(n_features) if n_features is not None else None,
        "label_name": label_col,
        "out_dir": str(out_dir),
        "chunks": chunk_files,
    }
    
    return fitted, metadata


def save_preprocessor(preprocessor: FittedPreprocessor, filepath: Path) -> None:
    """
    Serialize fitted preprocessor object to disk using pickle.
    
    Args:
        preprocessor: FittedPreprocessor instance
        filepath: Output file path (typically .pkl extension)
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'wb') as f:
        pickle.dump(preprocessor, f)
    print(f"Preprocessor saved to {filepath}")


def load_preprocessor(filepath: Path) -> FittedPreprocessor:
    """
    Deserialize fitted preprocessor object from disk.
    
    Args:
        filepath: Input file path (typically .pkl extension)
        
    Returns:
        FittedPreprocessor: Loaded preprocessor object
    """
    with open(filepath, 'rb') as f:
        preprocessor = pickle.load(f)
    return preprocessor


def save_metadata(metadata: Dict[str, Any], filepath: Path) -> None:
    """
    Export preprocessing metadata to JSON format.
    
    Args:
        metadata: Metadata dictionary from fit_on_sample_and_transform_in_chunks
        filepath: Output JSON file path
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {filepath}")


if __name__ == "__main__":
    print("Edge-IIoT Preprocessing Module")
    print("Use this module by importing functions into your preprocessing notebook or script.")

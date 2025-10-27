from __future__ import annotations
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple

LABEL_GUESS_CANDIDATES = ["attack", "Attack", "Label", "label", "class", "Class", "Attack_type", "AttackType", "Category"]

def guess_label_column(df: pd.DataFrame, override: Optional[str] = None) -> str:
    if override and override in df.columns:
        return override
    # try common names
    for c in LABEL_GUESS_CANDIDATES:
        if c in df.columns:
            return c
    # else last column
    return df.columns[-1]

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df

def to_binary_labels(y: pd.Series) -> np.ndarray:
    # Treat anything not clearly "Benign"/0 as attack = 1
    y_norm = y.astype(str).str.lower().str.strip()
    attack = ~(y_norm.isin(["benign", "normal", "0"]))
    return attack.astype(int).to_numpy()

def to_multiclass_labels(y: pd.Series) -> Tuple[np.ndarray, List[str]]:
    # factorize preserves unique class names order
    classes, uniques = pd.factorize(y.astype(str).str.strip())
    return classes.astype(int), [str(u) for u in uniques]

@dataclass
class FittedPreprocessor:
    numeric_means: dict
    numeric_stds: dict
    categorical_mappings: dict
    features: List[str]
    label_name: str
    classes: Optional[List[str]] = None

def simple_fit_transform(df: pd.DataFrame, label_col: str) -> Tuple[np.ndarray, FittedPreprocessor]:
    """Simple manual preprocessing without scikit-learn"""
    df_clean = df.copy()
    
    # Handle numeric columns
    numeric_cols = df_clean.select_dtypes(include=["number", "float", "int"]).columns.tolist()
    numeric_cols = [col for col in numeric_cols if col != label_col]
    
    numeric_means = {}
    numeric_stds = {}
    
    # Calculate stats for numeric columns
    for col in numeric_cols:
        # Convert to numeric, coercing errors to NaN
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
        # Fill NaN with mean
        col_mean = df_clean[col].mean()
        df_clean[col] = df_clean[col].fillna(col_mean)
        numeric_means[col] = col_mean
        numeric_stds[col] = df_clean[col].std() if df_clean[col].std() > 0 else 1.0
    
    # Handle categorical columns
    categorical_cols = [col for col in df_clean.columns 
                       if col not in numeric_cols + [label_col] 
                       and col in df_clean.columns]
    
    categorical_mappings = {}
    
    # Create mappings for categorical columns
    for col in categorical_cols:
        # Convert to string and clean
        df_clean[col] = df_clean[col].astype(str).str.strip()
        # Get unique values and create mapping
        unique_vals = df_clean[col].unique()
        mapping = {val: idx for idx, val in enumerate(unique_vals)}
        categorical_mappings[col] = mapping
        # Apply mapping
        df_clean[col] = df_clean[col].map(mapping)
        # Fill any NaN from unknown values with 0
        df_clean[col] = df_clean[col].fillna(0)
    
    # Standardize numeric columns
    for col in numeric_cols:
        if numeric_stds[col] > 0:
            df_clean[col] = (df_clean[col] - numeric_means[col]) / numeric_stds[col]
    
    # Create final feature matrix
    feature_cols = numeric_cols + categorical_cols
    X = df_clean[feature_cols].values.astype("float32")
    
    fitted = FittedPreprocessor(
        numeric_means=numeric_means,
        numeric_stds=numeric_stds,
        categorical_mappings=categorical_mappings,
        features=feature_cols,
        label_name=label_col
    )
    
    return X, fitted

def simple_transform(df: pd.DataFrame, fitted: FittedPreprocessor) -> np.ndarray:
    """Transform new data using fitted preprocessor"""
    df_clean = df.copy()
    
    # Process numeric columns
    for col in fitted.numeric_means:
        if col in df_clean.columns:
            # Convert to numeric, coercing errors to NaN
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
            # Fill NaN with fitted mean
            df_clean[col] = df_clean[col].fillna(fitted.numeric_means[col])
            # Standardize
            if fitted.numeric_stds[col] > 0:
                df_clean[col] = (df_clean[col] - fitted.numeric_means[col]) / fitted.numeric_stds[col]
    
    # Process categorical columns
    for col, mapping in fitted.categorical_mappings.items():
        if col in df_clean.columns:
            # Convert to string and clean
            df_clean[col] = df_clean[col].astype(str).str.strip()
            # Map using fitted mapping, unknown values get 0
            df_clean[col] = df_clean[col].map(mapping).fillna(0)
    
    # Ensure all expected features are present
    for col in fitted.features:
        if col not in df_clean.columns:
            df_clean[col] = 0  # Add missing columns with default value
    
    # Select only the features we need
    X = df_clean[fitted.features].values.astype("float32")
    return X

def fit_transform_first_batch(df: pd.DataFrame, task_mode: str = "binary", label_override: Optional[str] = None
                             ) -> Tuple[np.ndarray, np.ndarray, FittedPreprocessor]:
    df = clean_column_names(df)
    label_col = guess_label_column(df, label_override)
    y_raw = df[label_col]

    if task_mode.lower().startswith("multi"):
        y, classes = to_multiclass_labels(y_raw)
    else:
        y = to_binary_labels(y_raw)
        classes = None

    # Use simple preprocessing
    X, fitted = simple_fit_transform(df, label_col)
    
    # Add classes to fitted preprocessor
    fitted.classes = classes
    
    return X, y.astype("int64"), fitted

def transform_next_batch(df: pd.DataFrame, fitted: FittedPreprocessor, task_mode: str = "binary") -> Tuple[np.ndarray, np.ndarray]:
    df = clean_column_names(df)
    label_col = fitted.label_name if fitted.label_name in df.columns else guess_label_column(df)
    y_raw = df[label_col]
    
    if task_mode.lower().startswith("multi"):
        # Map unseen labels to -1 (will be filtered out)
        mapping = {name: i for i, name in enumerate(fitted.classes)} if fitted.classes else {}
        y = np.array([mapping.get(str(v).strip(), -1) for v in y_raw], dtype="int64")
        df = df[y != -1]  # drop rows with unknown class
        y = y[y != -1]
    else:
        y = to_binary_labels(y_raw)

    # Use simple transformation
    X = simple_transform(df, fitted)
    
    return X, y.astype("int64")
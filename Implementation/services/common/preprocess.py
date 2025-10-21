from __future__ import annotations
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline

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
    pipeline: Pipeline
    features: List[str]
    label_name: str
    classes: Optional[List[str]] = None  # for multiclass

def build_pipeline(df: pd.DataFrame, label_col: str) -> Tuple[Pipeline, List[str], List[str], List[str]]:
    X = df.drop(columns=[label_col])
    # Identify types
    numeric_cols = X.select_dtypes(include=["number", "float", "int"]).columns.tolist()
    cat_cols = [c for c in X.columns if c not in numeric_cols]
    # Preprocess
    transformers = []
    if numeric_cols:
        transformers.append(("num", StandardScaler(with_mean=True, with_std=True), numeric_cols))
    if cat_cols:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols))
    pre = ColumnTransformer(transformers=transformers, remainder="drop")
    pipe = Pipeline([("pre", pre)])
    return pipe, X.columns.tolist(), numeric_cols, cat_cols

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

    pipe, features, *_ = build_pipeline(df, label_col)
    X = pipe.fit_transform(df.drop(columns=[label_col]))
    return X.astype("float32"), y.astype("int64"), FittedPreprocessor(pipeline=pipe, features=features,
                                                                      label_name=label_col, classes=classes)

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

    X = fitted.pipeline.transform(df.drop(columns=[label_col]))
    return X.astype("float32"), y.astype("int64")
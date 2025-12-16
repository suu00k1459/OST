from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple

import numpy as np
import pandas as pd


# -----------------------------
# Config
# -----------------------------

@dataclass
class ZScoreConfig:
    # Feature selection
    include_cols: Optional[List[str]] = None
    exclude_cols: Optional[List[str]] = None
    id_cols: Optional[List[str]] = None
    time_col: Optional[str] = None

    # Z-score behavior
    method: str = "standard"  # "standard" (mean/std) or "robust" (median/MAD)
    epsilon: float = 1e-12    # avoid divide-by-zero

    # Decision rule
    threshold: float = 3.0    # typical z threshold
    aggregate: str = "max"    # "max" | "mean" | "rms" | "count"

    # Output columns
    score_col: str = "anomaly_score"
    label_col: str = "is_anomaly"


# -----------------------------
# IO helpers
# -----------------------------

def read_table(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input not found: {path}")

    lower = path.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    if lower.endswith(".parquet") or lower.endswith(".pq"):
        return pd.read_parquet(path)
    raise ValueError("Unsupported input format. Use .csv or .parquet/.pq")


def write_table(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lower = path.lower()
    if lower.endswith(".csv"):
        df.to_csv(path, index=False)
        return
    if lower.endswith(".parquet") or lower.endswith(".pq"):
        df.to_parquet(path, index=False)
        return
    raise ValueError("Unsupported output format. Use .csv or .parquet/.pq")


# -----------------------------
# Feature selection
# -----------------------------

def select_numeric_features(df: pd.DataFrame, cfg: ZScoreConfig) -> Tuple[pd.DataFrame, List[str]]:
    drop_cols = set()
    if cfg.id_cols:
        drop_cols.update(cfg.id_cols)
    if cfg.time_col:
        drop_cols.add(cfg.time_col)
    if cfg.exclude_cols:
        drop_cols.update(cfg.exclude_cols)

    if cfg.include_cols:
        candidates = [c for c in cfg.include_cols if c in df.columns and c not in drop_cols]
    else:
        candidates = [c for c in df.columns if c not in drop_cols]

    numeric_cols = [c for c in candidates if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        raise ValueError("No numeric feature columns found after filtering.")

    X = df[numeric_cols].copy()
    return X, numeric_cols


# -----------------------------
# Stats (train)
# -----------------------------

def compute_stats_standard(X: pd.DataFrame, eps: float) -> Dict[str, Dict[str, float]]:
    stats: Dict[str, Dict[str, float]] = {}
    for c in X.columns:
        col = X[c].astype(float)
        mu = float(np.nanmean(col))
        sigma = float(np.nanstd(col, ddof=0))
        if not np.isfinite(sigma) or sigma < eps:
            sigma = eps
        stats[c] = {"center": mu, "scale": sigma}
    return stats


def compute_stats_robust(X: pd.DataFrame, eps: float) -> Dict[str, Dict[str, float]]:
    # median / MAD scaled to be comparable to std: MAD * 1.4826
    stats: Dict[str, Dict[str, float]] = {}
    for c in X.columns:
        col = X[c].astype(float)
        med = float(np.nanmedian(col))
        mad = float(np.nanmedian(np.abs(col - med)))
        scale = float(mad * 1.4826)
        if not np.isfinite(scale) or scale < eps:
            scale = eps
        stats[c] = {"center": med, "scale": scale}
    return stats


# -----------------------------
# Z-score + aggregation
# -----------------------------

def zscores(X: pd.DataFrame, stats: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    Z = pd.DataFrame(index=X.index)
    for c in X.columns:
        if c not in stats:
            raise ValueError(f"Feature '{c}' missing in model stats.")
        center = stats[c]["center"]
        scale = stats[c]["scale"]
        Z[c] = (X[c].astype(float) - center) / scale
    return Z


def aggregate_score(absZ: pd.DataFrame, cfg: ZScoreConfig) -> np.ndarray:
    agg = cfg.aggregate.lower()

    if agg == "max":
        return absZ.max(axis=1).to_numpy()
    if agg == "mean":
        return absZ.mean(axis=1).to_numpy()
    if agg == "rms":
        return np.sqrt((absZ ** 2).mean(axis=1)).to_numpy()
    if agg == "count":
        # count how many features exceed threshold; score is the count
        return (absZ > cfg.threshold).sum(axis=1).to_numpy(dtype=float)

    raise ValueError("aggregate must be one of: max, mean, rms, count")


def label_from_absZ(absZ: pd.DataFrame, cfg: ZScoreConfig) -> np.ndarray:
    # Label = anomaly if ANY feature exceeds threshold
    return (absZ.max(axis=1) > cfg.threshold).to_numpy(dtype=int)


# -----------------------------
# Train / Predict
# -----------------------------

def train(cfg: ZScoreConfig, input_path: str, model_out: str) -> Dict[str, Any]:
    df = read_table(input_path)
    X, feature_cols = select_numeric_features(df, cfg)

    if cfg.method.lower() == "standard":
        stats = compute_stats_standard(X, cfg.epsilon)
    elif cfg.method.lower() == "robust":
        stats = compute_stats_robust(X, cfg.epsilon)
    else:
        raise ValueError("method must be 'standard' or 'robust'")

    model = {
        "type": "zscore",
        "config": asdict(cfg),
        "feature_cols": feature_cols,
        "stats": stats,
        "schema": {
            "input_columns": list(df.columns),
            "feature_columns": feature_cols,
        },
    }

    os.makedirs(os.path.dirname(model_out) or ".", exist_ok=True)
    with open(model_out, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)

    return {
        "model_out": model_out,
        "rows": int(len(df)),
        "n_features": int(len(feature_cols)),
        "method": cfg.method,
        "aggregate": cfg.aggregate,
        "threshold": cfg.threshold,
    }


def predict(cfg: ZScoreConfig, input_path: str, model_in: str, output_path: str) -> Dict[str, Any]:
    df = read_table(input_path)

    with open(model_in, "r", encoding="utf-8") as f:
        model = json.load(f)

    feature_cols: List[str] = model.get("feature_cols", [])
    stats: Dict[str, Dict[str, float]] = model.get("stats", {})

    if not feature_cols or not stats:
        raise ValueError("Invalid model file: missing feature_cols/stats")

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required feature columns in input: {missing}")

    X = df[feature_cols].copy()
    Z = zscores(X, stats)
    absZ = Z.abs()

    scores = aggregate_score(absZ, cfg)
    labels = label_from_absZ(absZ, cfg)

    out = df.copy()
    out[cfg.score_col] = scores
    out[cfg.label_col] = labels

    # Optional: also export per-feature z-scores (comment out if too wide)
    # for c in feature_cols:
    #     out[f"z_{c}"] = Z[c].to_numpy()

    write_table(out, output_path)

    n_anom = int(out[cfg.label_col].sum())
    return {
        "model_in": model_in,
        "output": output_path,
        "rows": int(len(out)),
        "anomalies": n_anom,
        "anomaly_rate": float(n_anom / max(1, len(out))),
        "threshold": cfg.threshold,
        "aggregate": cfg.aggregate,
        "method": cfg.method,
    }


# -----------------------------
# CLI
# -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Z-Score Anomaly Detection (train/predict)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--input", required=True, help="Input dataset (.csv or .parquet)")
        sp.add_argument("--include-cols", nargs="*", default=None, help="Optional whitelist of feature cols")
        sp.add_argument("--exclude-cols", nargs="*", default=None, help="Optional blacklist of cols")
        sp.add_argument("--id-cols", nargs="*", default=None, help="ID cols to ignore as features")
        sp.add_argument("--time-col", default=None, help="Timestamp column to ignore as a feature")

        sp.add_argument("--method", default="standard", choices=["standard", "robust"],
                        help="standard=mean/std, robust=median/MAD")
        sp.add_argument("--threshold", type=float, default=3.0, help="Z threshold for anomalies")
        sp.add_argument("--aggregate", default="max", choices=["max", "mean", "rms", "count"],
                        help="How to aggregate per-feature |z| into anomaly_score")

    tr = sub.add_parser("train", help="Compute stats and save a zscore model (.json)")
    add_common(tr)
    tr.add_argument("--model-out", required=True, help="Path to save model json")

    pr = sub.add_parser("predict", help="Score data using a saved zscore model")
    add_common(pr)
    pr.add_argument("--model-in", required=True, help="Path to load model json")
    pr.add_argument("--output", required=True, help="Path to write scored dataset")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = ZScoreConfig(
        include_cols=args.include_cols,
        exclude_cols=args.exclude_cols,
        id_cols=args.id_cols,
        time_col=args.time_col,
        method=args.method,
        threshold=args.threshold,
        aggregate=args.aggregate,
    )

    if args.cmd == "train":
        info = train(cfg, args.input, args.model_out)
        print(json.dumps(info, indent=2))
    elif args.cmd == "predict":
        info = predict(cfg, args.input, args.model_in, args.output)
        print(json.dumps(info, indent=2))
    else:
        raise ValueError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()

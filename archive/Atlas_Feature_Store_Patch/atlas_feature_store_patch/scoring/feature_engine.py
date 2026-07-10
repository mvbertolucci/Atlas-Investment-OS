from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def load_features(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(f"Feature Store não encontrada: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def pct_rank(df: pd.DataFrame, col: str, higher: bool = True) -> pd.Series:
    if col not in df.columns:
        return pd.Series(50.0, index=df.index)

    s = pd.to_numeric(df[col], errors="coerce")

    if s.notna().sum() <= 1:
        return pd.Series(50.0, index=df.index)

    r = s.rank(method="average", pct=True) * 100

    if not higher:
        r = 100 - r

    return r.fillna(50.0)


def normalize_weights(features: dict[str, dict[str, Any]]) -> dict[str, float]:
    total = sum(float(meta.get("weight", 0)) for meta in features.values())
    if total <= 0:
        count = max(len(features), 1)
        return {name: 1 / count for name in features}
    return {name: float(meta.get("weight", 0)) / total for name, meta in features.items()}


def score_engine(df: pd.DataFrame, engine_name: str, feature_store: dict) -> pd.DataFrame:
    result = df.copy()
    features = feature_store.get(engine_name, {})
    weights = normalize_weights(features)

    if not features:
        result[f"{engine_name.title()} Score"] = 50.0
        result[f"{engine_name.title()} Confidence"] = 0.0
        return result

    engine_score = pd.Series(0.0, index=result.index)
    available_required = pd.Series(0.0, index=result.index)
    total_required = 0
    available_all = pd.Series(0.0, index=result.index)
    total_all = len(features)

    for feature, meta in features.items():
        higher = bool(meta.get("higher_is_better", True))
        weight = weights.get(feature, 0.0)
        label = meta.get("label", feature)
        required = bool(meta.get("required", False))

        feature_score = pct_rank(result, feature, higher)
        result[f"{engine_name.title()}::{label} Score"] = feature_score.round(1)
        engine_score += feature_score * weight

        if feature in result.columns:
            non_null = pd.to_numeric(result[feature], errors="coerce").notna().astype(float)
        else:
            non_null = pd.Series(0.0, index=result.index)

        available_all += non_null
        if required:
            total_required += 1
            available_required += non_null

    if total_required > 0:
        confidence = (available_required / total_required) * 100
    else:
        confidence = (available_all / max(total_all, 1)) * 100

    result[f"{engine_name.title()} Score"] = engine_score.round(1)
    result[f"{engine_name.title()} Confidence"] = confidence.round(1)

    return result

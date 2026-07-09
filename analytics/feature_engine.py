from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class Feature:
    name: str
    label: str
    engine: str
    weight: float = 1.0
    higher_is_better: bool = True
    required: bool = False
    missing_score: float = 50.0
    source: str = "unknown"
    update: str = "unknown"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_features(features_path: Path) -> list[Feature]:
    raw = load_yaml(features_path)
    features: list[Feature] = []

    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue

        features.append(
            Feature(
                name=name,
                label=cfg.get("label", name),
                engine=cfg.get("engine", "unknown"),
                weight=float(cfg.get("weight", 1.0)),
                higher_is_better=bool(cfg.get("higher_is_better", True)),
                required=bool(cfg.get("required", False)),
                missing_score=float(cfg.get("missing_score", 50.0)),
                source=cfg.get("source", "unknown"),
                update=cfg.get("update", "unknown"),
            )
        )

    return features


def features_by_engine(features: list[Feature], engine: str) -> list[Feature]:
    return [f for f in features if f.engine == engine]


def feature_score(df: pd.DataFrame, feature: Feature) -> pd.Series:
    if feature.name not in df.columns:
        return pd.Series(feature.missing_score, index=df.index)

    s = pd.to_numeric(df[feature.name], errors="coerce")

    if s.notna().sum() <= 1:
        return pd.Series(feature.missing_score, index=df.index)

    score = s.rank(pct=True) * 100

    if not feature.higher_is_better:
        score = 100 - score

    return score.fillna(feature.missing_score).clip(0, 100)


def engine_score(df: pd.DataFrame, features: list[Feature], engine: str) -> pd.Series:
    selected = features_by_engine(features, engine)

    if not selected:
        return pd.Series(50.0, index=df.index)

    total_weight = sum(f.weight for f in selected)

    if total_weight == 0:
        return pd.Series(50.0, index=df.index)

    score = pd.Series(0.0, index=df.index)

    for feature in selected:
        score += feature_score(df, feature) * feature.weight

    return (score / total_weight).round(1)


def feature_coverage(df: pd.DataFrame, features: list[Feature], engine: str | None = None) -> pd.Series:
    selected = features_by_engine(features, engine) if engine else features

    if not selected:
        return pd.Series(0.0, index=df.index)

    available = pd.Series(0, index=df.index)

    for feature in selected:
        if feature.name in df.columns:
            available += pd.to_numeric(df[feature.name], errors="coerce").notna().astype(int)

    return (available / len(selected) * 100).round(1)


def add_feature_diagnostics(df: pd.DataFrame, features: list[Feature]) -> pd.DataFrame:
    result = df.copy()

    engines = sorted({f.engine for f in features})

    for engine in engines:
        result[f"{engine.title()} Coverage"] = feature_coverage(result, features, engine)

    result["Feature Coverage"] = feature_coverage(result, features)

    return result
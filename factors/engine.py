from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from factors.valuation import score_valuation


DEFAULT_FACTORS = {
    "business": 0.35,
    "valuation": 0.30,
    "financial": 0.15,
    "timing": 0.20,
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def pct_rank(df: pd.DataFrame, column: str, higher_is_better: bool = True) -> pd.Series:
    if column not in df.columns:
        return pd.Series(50.0, index=df.index)

    s = pd.to_numeric(df[column], errors="coerce")

    if s.notna().sum() <= 1:
        return pd.Series(50.0, index=df.index)

    r = s.rank(method="average", pct=True) * 100

    if not higher_is_better:
        r = 100 - r

    return r.fillna(50.0).clip(0, 100)


def metric_available(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)

    return pd.to_numeric(df[column], errors="coerce").notna()


def get_factor_features(features: dict[str, Any], factor: str) -> dict[str, Any]:
    factor = factor.lower()

    # Formato novo/hierárquico:
    # business:
    #   roic:
    #     weight: ...
    if factor in features and isinstance(features[factor], dict):
        return features[factor]

    # Formato antigo/plano:
    # roic:
    #   factor: business
    selected = {}

    for feature_name, cfg in features.items():
        if not isinstance(cfg, dict):
            continue

        cfg_factor = str(cfg.get("factor") or cfg.get("engine") or "").lower()

        if cfg_factor == factor:
            selected[feature_name] = cfg

    return selected


def score_factor(
    df: pd.DataFrame,
    features: dict[str, Any],
    factor: str,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    factor = factor.lower()
    selected = get_factor_features(features, factor)

    if not selected:
        neutral = pd.Series(50.0, index=df.index)
        confidence = pd.Series(0.0, index=df.index)
        details = pd.DataFrame(index=df.index)
        return neutral, confidence, details

    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight = pd.Series(0.0, index=df.index)
    total_weight = 0.0
    details = pd.DataFrame(index=df.index)

    for feature_name, cfg in selected.items():
        if not isinstance(cfg, dict):
            continue

        column = str(cfg.get("column") or feature_name)
        label = str(cfg.get("label") or feature_name)
        weight = float(cfg.get("weight", 1.0))
        higher = bool(cfg.get("higher_is_better", True))

        score = pct_rank(df, column, higher)
        available = metric_available(df, column)

        weighted_sum += score * weight
        available_weight += available.astype(float) * weight
        total_weight += weight

        safe_label = (
            label.replace("/", "_")
            .replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("-", "_")
        )

        details[f"{factor}_{safe_label}_score"] = score.round(1)
        details[f"{factor}_{safe_label}_available"] = available

    if total_weight <= 0:
        factor_score = pd.Series(50.0, index=df.index)
        factor_confidence = pd.Series(0.0, index=df.index)
    else:
        factor_score = weighted_sum / total_weight
        factor_confidence = (available_weight / total_weight * 100).clip(0, 100)

    return factor_score.round(1), factor_confidence.round(1), details


def score_all_factors(
    df: pd.DataFrame,
    features_path: Path,
    model_path: Path | None = None,
) -> pd.DataFrame:
    result = df.copy()

    features = load_yaml(features_path)
    model = load_yaml(model_path) if model_path else {}

    factor_weights = model.get("factor_weights", DEFAULT_FACTORS)

    factor_scores: dict[str, pd.Series] = {}
    confidence_parts: list[pd.Series] = []

    for factor, weight in factor_weights.items():
        factor = str(factor).lower()

        if factor == "valuation":
            score, confidence, details = score_valuation(result, features)
        else:
            score, confidence, details = score_factor(result, features, factor)

        factor_col = f"{factor.title()} Factor"
        confidence_col = f"{factor.title()} Confidence"

        result[factor_col] = score.round(1)
        result[confidence_col] = confidence.round(1)

        result = pd.concat([result, details], axis=1)

        factor_scores[factor] = score
        confidence_parts.append(confidence)

    total_weight = sum(float(w) for w in factor_weights.values()) or 1.0
    investment = pd.Series(0.0, index=result.index)

    for factor, weight in factor_weights.items():
        factor = str(factor).lower()
        investment += factor_scores.get(factor, pd.Series(50.0, index=result.index)) * float(weight)

    result["Investment Score"] = (investment / total_weight).round(1)

    if confidence_parts:
        result["Model Confidence"] = (
            pd.concat(confidence_parts, axis=1)
            .mean(axis=1)
            .round(1)
        )
    else:
        result["Model Confidence"] = 0.0

    # Cobertura efetiva do score: o mesmo percentual de peso de features
    # observado pelo motor de fatores. Nome explícito para gating operacional;
    # não altera score, pesos ou semântica de Confidence Score.
    result["Score Coverage"] = result["Model Confidence"].round(1)

    aliases = {
        "Business Factor": "Business Score",
        "Valuation Factor": "Valuation Score",
        "Financial Factor": "Financial Score",
        "Timing Factor": "Timing Score",
        "Model Confidence": "Confidence Score",
    }

    for src, dst in aliases.items():
        if src in result.columns:
            result[dst] = result[src]

    return result

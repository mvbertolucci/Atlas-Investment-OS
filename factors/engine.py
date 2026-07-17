from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any

import pandas as pd
import yaml

from analytics.data_quality import freshness_scores, source_quality_scores
from factors.valuation import score_valuation
from scoring.reference import ScoringReference, percentile_rank


DEFAULT_FACTORS = {
    "business": 0.35,
    "valuation": 0.30,
    "financial": 0.15,
    "timing": 0.20,
}


def pct_rank(
    df: pd.DataFrame,
    column: str,
    higher_is_better: bool = True,
) -> pd.Series:
    """Interface legada: percentil dentro do lote, sem referência externa."""
    return percentile_rank(
        df,
        column,
        higher_is_better=higher_is_better,
    )


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


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
    reference: ScoringReference | None = None,
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
        scope = str(cfg.get("percentile_scope", "market")).strip().lower()

        score = percentile_rank(
            df,
            column,
            higher_is_better=higher,
            reference=reference,
            scope=scope,
        )
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
    reference: ScoringReference | None = None,
    quality_policy: dict[str, Any] | None = None,
    quality_at: datetime | None = None,
) -> pd.DataFrame:
    result = df.copy()

    features = load_yaml(features_path)
    model = load_yaml(model_path) if model_path else {}

    factor_weights = model.get("factor_weights", DEFAULT_FACTORS)

    factor_scores: dict[str, pd.Series] = {}
    factor_confidences: dict[str, pd.Series] = {}

    for factor, weight in factor_weights.items():
        factor = str(factor).lower()

        if factor == "valuation":
            score, confidence, details = score_valuation(
                result, features, reference=reference
            )
        else:
            score, confidence, details = score_factor(
                result, features, factor, reference=reference
            )

        factor_col = f"{factor.title()} Factor"
        confidence_col = f"{factor.title()} Confidence"

        result[factor_col] = score.round(1)
        result[confidence_col] = confidence.round(1)

        result = pd.concat([result, details], axis=1)

        factor_scores[factor] = score
        factor_confidences[factor] = confidence

    total_weight = sum(float(w) for w in factor_weights.values()) or 1.0
    investment = pd.Series(0.0, index=result.index)

    for factor, weight in factor_weights.items():
        factor = str(factor).lower()
        investment += factor_scores.get(factor, pd.Series(50.0, index=result.index)) * float(weight)

    result["Investment Score"] = (investment / total_weight).round(1)

    weighted_coverage = pd.Series(0.0, index=result.index, dtype="float64")
    for factor, weight in factor_weights.items():
        factor_name = str(factor).lower()
        weighted_coverage += factor_confidences.get(
            factor_name,
            pd.Series(0.0, index=result.index),
        ) * float(weight)
    result["Data Coverage"] = (weighted_coverage / total_weight).round(1)

    missing_required: list[list[str]] = [[] for _ in range(len(result))]
    required_count = 0
    for factor in factor_weights:
        factor_name = str(factor).lower()
        selected = get_factor_features(features, factor_name)
        for feature_name, cfg in selected.items():
            if not isinstance(cfg, dict) or not bool(cfg.get("required", False)):
                continue
            required_count += 1
            column = str(cfg.get("column") or feature_name)
            available = metric_available(result, column).tolist()
            for position, present in enumerate(available):
                if not present:
                    missing_required[position].append(
                        f"{factor_name}:{feature_name}"
                    )

    result["Required Feature Count"] = required_count
    result["Missing Required Feature Count"] = [
        len(items) for items in missing_required
    ]
    result["Missing Required Features"] = [
        "; ".join(items) if items else "Nenhum"
        for items in missing_required
    ]
    result["Required Features Complete"] = [
        not items for items in missing_required
    ]

    confidence_cfg = model.get("confidence") or {}
    missing_required_cap = float(
        confidence_cfg.get("missing_required_cap", 59.0)
    )
    model_confidence = result["Data Coverage"].copy()
    incomplete_required = ~result["Required Features Complete"]
    model_confidence = model_confidence.mask(
        incomplete_required,
        model_confidence.clip(upper=missing_required_cap),
    )
    result["Model Confidence"] = model_confidence.round(1)
    result["Source Quality"] = source_quality_scores(result, quality_policy)
    result["Data Freshness"] = freshness_scores(
        result,
        quality_policy,
        evaluated_at=quality_at,
    )

    # Alias legado mantido para sell rules, histórico e relatórios antigos.
    result["Score Coverage"] = result["Data Coverage"].round(1)

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

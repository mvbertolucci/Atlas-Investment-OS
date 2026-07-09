from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scoring.feature_engine import load_features, score_engine


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def classify(score: float) -> str:
    if score >= 90:
        return "★★★★★ Comprar Forte"
    if score >= 80:
        return "★★★★ Comprar"
    if score >= 70:
        return "★★★ Acumular"
    if score >= 60:
        return "★★ Manter"
    return "★ Evitar"


def apply_deal_breakers(df: pd.DataFrame, score: pd.Series, deal_breakers: dict) -> pd.Series:
    adjusted = score.copy()

    max_net_debt_ebitda = deal_breakers.get("net_debt_ebitda_max", 4)
    min_current_ratio = deal_breakers.get("current_ratio_min", 1)
    min_f_score = deal_breakers.get("piotroski_min", 4)
    max_short_float = deal_breakers.get("short_float_max", 20)

    if "net_debt_ebitda" in df.columns:
        s = pd.to_numeric(df["net_debt_ebitda"], errors="coerce")
        adjusted -= (s > max_net_debt_ebitda).fillna(False) * 15

    if "current_ratio" in df.columns:
        s = pd.to_numeric(df["current_ratio"], errors="coerce")
        adjusted -= (s < min_current_ratio).fillna(False) * 10

    if "f_score_annual" in df.columns:
        s = pd.to_numeric(df["f_score_annual"], errors="coerce")
        adjusted -= (s < min_f_score).fillna(False) * 15

    if "short_float" in df.columns:
        s = pd.to_numeric(df["short_float"], errors="coerce")
        adjusted -= (s > max_short_float).fillna(False) * 10

    return adjusted.clip(lower=0, upper=100)


def score_dataframe(
    df: pd.DataFrame,
    weights_path: Path,
    deal_breakers_path: Path,
) -> pd.DataFrame:
    result = df.copy()

    config_dir = weights_path.parent
    features = load_features(config_dir / "features.yaml")
    weights = load_json(weights_path)
    deal_breakers = load_json(deal_breakers_path)

    for engine in ["business", "valuation", "financial", "timing"]:
        result = score_engine(result, engine, features)

    business_weight = weights.get("business_score", 0.35)
    valuation_weight = weights.get("valuation_score", 0.30)
    financial_weight = weights.get("financial_score", 0.15)
    timing_weight = weights.get("timing_score", 0.20)

    total_weight = business_weight + valuation_weight + financial_weight + timing_weight
    if total_weight == 0:
        total_weight = 1

    investment = (
        result["Business Score"] * business_weight
        + result["Valuation Score"] * valuation_weight
        + result["Financial Score"] * financial_weight
        + result["Timing Score"] * timing_weight
    ) / total_weight

    investment = apply_deal_breakers(result, investment, deal_breakers)

    result["Investment Score"] = investment.round(1)
    result["Recommendation"] = result["Investment Score"].apply(classify)

    engine_conf_cols = [
        "Business Confidence",
        "Valuation Confidence",
        "Financial Confidence",
        "Timing Confidence",
    ]
    existing = [c for c in engine_conf_cols if c in result.columns]
    if existing:
        result["Model Confidence"] = result[existing].mean(axis=1).round(1)

    result = result.sort_values("Investment Score", ascending=False)
    return result

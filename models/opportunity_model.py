from __future__ import annotations

import pandas as pd


def classify_opportunity(score: float) -> str:
    if score >= 90:
        return "★★★★★ Strong Opportunity"
    if score >= 80:
        return "★★★★ Opportunity"
    if score >= 70:
        return "★★★ Watch"
    if score >= 60:
        return "★★ Neutral"
    return "★ Ignore"


def apply_opportunity(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    required = [
        "Business Score",
        "Valuation Score",
        "Financial Score",
        "Timing Score",
    ]

    for col in required:
        if col not in result.columns:
            result[col] = 50.0

    business = pd.to_numeric(result["Business Score"], errors="coerce").fillna(50.0)
    valuation = pd.to_numeric(result["Valuation Score"], errors="coerce").fillna(50.0)
    financial = pd.to_numeric(result["Financial Score"], errors="coerce").fillna(50.0)
    timing = pd.to_numeric(result["Timing Score"], errors="coerce").fillna(50.0)

    opportunity = (
        business * 0.45
        + valuation * 0.35
        + financial * 0.15
        + timing * 0.05
    )

    if "Risk Penalty" in result.columns:
        penalty = pd.to_numeric(result["Risk Penalty"], errors="coerce").fillna(0.0)
        opportunity = opportunity - penalty

    if "Confidence Score" in result.columns:
        confidence = pd.to_numeric(result["Confidence Score"], errors="coerce").fillna(100.0)
        low_confidence_penalty = ((100 - confidence).clip(lower=0) * 0.05)
        opportunity = opportunity - low_confidence_penalty

    result["Opportunity Score"] = opportunity.clip(lower=0, upper=100).round(1)
    result["Opportunity Rating"] = result["Opportunity Score"].apply(classify_opportunity)

    return result
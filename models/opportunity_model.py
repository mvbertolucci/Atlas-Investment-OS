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
        business * 0.40
        + valuation * 0.30
        + financial * 0.20
        + timing * 0.10
    )

    drivers: list[list[str]] = [[] for _ in range(len(result))]

    def add_driver(condition: pd.Series, label: str) -> None:
        for i, ok in enumerate(condition.fillna(False).tolist()):
            if ok:
                drivers[i].append(label)

    bonus = pd.Series(0.0, index=result.index)
    penalty = pd.Series(0.0, index=result.index)

    business_bonus = business >= 80
    valuation_bonus = valuation >= 75
    financial_bonus = financial >= 80

    bonus += business_bonus.astype(float) * 5
    bonus += valuation_bonus.astype(float) * 5
    bonus += financial_bonus.astype(float) * 3

    add_driver(business_bonus, "Business excelente (+5)")
    add_driver(valuation_bonus, "Valuation atrativo (+5)")
    add_driver(financial_bonus, "Financial forte (+3)")

    business_penalty = business < 50
    financial_penalty = financial < 40

    penalty += business_penalty.astype(float) * 10
    penalty += financial_penalty.astype(float) * 10

    add_driver(business_penalty, "Business fraco (-10)")
    add_driver(financial_penalty, "Financial fraco (-10)")

    if "Confidence Score" in result.columns:
        confidence = pd.to_numeric(result["Confidence Score"], errors="coerce").fillna(100.0)

        confidence_bonus = confidence >= 90
        confidence_penalty = confidence < 60

        bonus += confidence_bonus.astype(float) * 2
        penalty += confidence_penalty.astype(float) * 5

        add_driver(confidence_bonus, "Confiança alta (+2)")
        add_driver(confidence_penalty, "Confiança baixa (-5)")

    if "Risk Penalty" in result.columns:
        risk_penalty = pd.to_numeric(result["Risk Penalty"], errors="coerce").fillna(0.0)
        penalty += risk_penalty

        add_driver(risk_penalty > 0, "Risk Penalty aplicado")

    final_score = opportunity + bonus - penalty

    result["Opportunity Base"] = opportunity.round(1)
    result["Opportunity Bonus"] = bonus.round(1)
    result["Opportunity Penalty"] = penalty.round(1)
    result["Opportunity Score"] = final_score.clip(lower=0, upper=100).round(1)
    result["Opportunity Rating"] = result["Opportunity Score"].apply(classify_opportunity)
    result["Opportunity Drivers"] = [
        "; ".join(items) if items else "Nenhum"
        for items in drivers
    ]

    return result
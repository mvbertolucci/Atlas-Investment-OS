from __future__ import annotations

import pandas as pd

from decision.policy import (
    DEFAULT_POLICY,
    DecisionPolicy,
    decision_priority,
    evaluate_decision,
)


DECISION_LABELS = {
    "STRONG_BUY": "★★★★★ Forte Compra",
    "BUY": "★★★★ Comprar",
    "ACCUMULATE": "★★★ Acumular",
    "HOLD": "★★ Manter",
    "WATCH": "★ Observar",
    "AVOID": "Evitar",
}


DECISION_ACTIONS = {
    "STRONG_BUY": "Considerar compra prioritária",
    "BUY": "Considerar compra gradual",
    "ACCUMULATE": "Considerar aumentar posição",
    "HOLD": "Manter e acompanhar",
    "WATCH": "Monitorar antes de agir",
    "AVOID": "Não comprar ou revisar posição",
}


def _numeric_column(
    df: pd.DataFrame,
    column: str,
    default: float,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(
            default,
            index=df.index,
            dtype="float64",
        )

    return (
        pd.to_numeric(
            df[column],
            errors="coerce",
        )
        .fillna(default)
        .clip(lower=0, upper=100)
    )


def _has_deal_breaker(df: pd.DataFrame) -> pd.Series:
    if "Deal Breakers" not in df.columns:
        return pd.Series(
            False,
            index=df.index,
            dtype="bool",
        )

    values = (
        df["Deal Breakers"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    neutral_values = {
        "",
        "nenhum",
        "none",
        "nan",
        "n/a",
        "-",
    }

    return ~values.isin(neutral_values)


def _build_decision_drivers(
    row: pd.Series,
) -> str:
    drivers: list[str] = []

    opportunity = pd.to_numeric(
        row.get("Opportunity Score"),
        errors="coerce",
    )
    conviction = pd.to_numeric(
        row.get("Conviction Score"),
        errors="coerce",
    )
    investment = pd.to_numeric(
        row.get("Investment Score"),
        errors="coerce",
    )
    business = pd.to_numeric(
        row.get("Business Score"),
        errors="coerce",
    )
    valuation = pd.to_numeric(
        row.get("Valuation Score"),
        errors="coerce",
    )
    financial = pd.to_numeric(
        row.get("Financial Score"),
        errors="coerce",
    )
    timing = pd.to_numeric(
        row.get("Timing Score"),
        errors="coerce",
    )
    risk_penalty = pd.to_numeric(
        row.get("Risk Penalty"),
        errors="coerce",
    )

    if pd.notna(opportunity):
        if opportunity >= 80:
            drivers.append("Opportunity muito alta")
        elif opportunity >= 70:
            drivers.append("Opportunity atrativa")
        elif opportunity < 45:
            drivers.append("Opportunity baixa")

    if pd.notna(conviction):
        if conviction >= 85:
            drivers.append("Conviction muito alta")
        elif conviction >= 70:
            drivers.append("Conviction adequada")
        elif conviction < 50:
            drivers.append("Conviction baixa")

    if pd.notna(investment):
        if investment >= 75:
            drivers.append("Investment Score forte")
        elif investment < 50:
            drivers.append("Investment Score fraco")

    if pd.notna(business):
        if business >= 75:
            drivers.append("Business forte")
        elif business < 50:
            drivers.append("Business fraco")

    if pd.notna(valuation):
        if valuation >= 75:
            drivers.append("Valuation atrativa")
        elif valuation < 40:
            drivers.append("Valuation desfavorável")

    if pd.notna(financial):
        if financial >= 75:
            drivers.append("Estrutura financeira forte")
        elif financial < 40:
            drivers.append("Estrutura financeira fraca")

    if pd.notna(timing):
        if timing >= 70:
            drivers.append("Timing favorável")
        elif timing < 40:
            drivers.append("Timing fraco")

    if pd.notna(risk_penalty):
        if risk_penalty <= 0:
            drivers.append("Sem penalidade de risco")
        elif risk_penalty >= 15:
            drivers.append("Penalidade de risco elevada")

    deal_breakers = str(
        row.get("Deal Breakers", "")
    ).strip()

    if (
        deal_breakers
        and deal_breakers.lower()
        not in {"nenhum", "none", "nan", "n/a", "-"}
    ):
        drivers.append(
            f"Deal Breakers: {deal_breakers}"
        )

    return "; ".join(drivers) if drivers else "Nenhum"


def _decision_confidence(
    opportunity: pd.Series,
    conviction: pd.Series,
    confidence: pd.Series,
    risk_penalty: pd.Series,
) -> pd.Series:
    score = (
        conviction * 0.50
        + confidence * 0.30
        + opportunity * 0.20
    )

    score = score - risk_penalty * 0.50

    return score.clip(
        lower=0,
        upper=100,
    )


def apply_decision(
    df: pd.DataFrame,
    policy: DecisionPolicy = DEFAULT_POLICY,
) -> pd.DataFrame:
    """
    Aplica a política de decisão do Atlas ao DataFrame.

    Colunas criadas:

    - Decision
    - Decision Rating
    - Suggested Action
    - Decision Confidence
    - Decision Drivers
    - Decision Priority
    """

    result = df.copy()

    opportunity = _numeric_column(
        result,
        "Opportunity Score",
        50.0,
    )
    conviction = _numeric_column(
        result,
        "Conviction Score",
        50.0,
    )
    confidence = _numeric_column(
        result,
        "Confidence Score",
        50.0,
    )
    risk_penalty = _numeric_column(
        result,
        "Risk Penalty",
        0.0,
    )

    deal_breakers = _has_deal_breaker(result)

    decisions = [
        evaluate_decision(
            opportunity_score=opportunity_value,
            conviction_score=conviction_value,
            risk_penalty=risk_value,
            has_deal_breaker=deal_breaker_value,
            policy=policy,
        )
        for (
            opportunity_value,
            conviction_value,
            risk_value,
            deal_breaker_value,
        ) in zip(
            opportunity,
            conviction,
            risk_penalty,
            deal_breakers,
        )
    ]

    result["Decision"] = decisions

    result["Decision Rating"] = (
        result["Decision"]
        .map(DECISION_LABELS)
        .fillna("Sem classificação")
    )

    result["Suggested Action"] = (
        result["Decision"]
        .map(DECISION_ACTIONS)
        .fillna("Revisar manualmente")
    )

    result["Decision Confidence"] = (
        _decision_confidence(
            opportunity=opportunity,
            conviction=conviction,
            confidence=confidence,
            risk_penalty=risk_penalty,
        )
        .round(1)
    )

    result["Decision Drivers"] = result.apply(
        _build_decision_drivers,
        axis=1,
    )

    result["Decision Priority"] = (
        result["Decision"]
        .apply(decision_priority)
        .astype(int)
    )

    return result
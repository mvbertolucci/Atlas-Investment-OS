from __future__ import annotations

import pandas as pd


def classify_conviction(score: float) -> str:
    if score >= 90:
        return "★★★★★ Convicção Muito Alta"
    if score >= 80:
        return "★★★★ Convicção Alta"
    if score >= 70:
        return "★★★ Convicção Moderada"
    if score >= 60:
        return "★★ Convicção Baixa"
    return "★ Convicção Muito Baixa"


def _numeric_column(
    df: pd.DataFrame,
    column: str,
    default: float,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")

    return (
        pd.to_numeric(df[column], errors="coerce")
        .fillna(default)
        .clip(lower=0, upper=100)
    )


def _factor_agreement(
    business: pd.Series,
    valuation: pd.Series,
    financial: pd.Series,
    timing: pd.Series,
) -> pd.Series:
    factors = pd.concat(
        [business, valuation, financial, timing],
        axis=1,
    )

    dispersion = factors.std(axis=1, ddof=0)

    return (100.0 - dispersion * 2.0).clip(
        lower=0,
        upper=100,
    )


def _historical_stability(df: pd.DataFrame) -> pd.Series:
    possible_columns = [
        "Historical Stability",
        "Opportunity Stability",
        "Score Stability",
    ]

    for column in possible_columns:
        if column in df.columns:
            return _numeric_column(df, column, 50.0)

    return pd.Series(50.0, index=df.index, dtype="float64")


def apply_conviction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula o Conviction Score do Atlas.

    Componentes:

    - Data Quality: confiança e cobertura dos dados.
    - Factor Agreement: convergência entre os fatores.
    - Historical Stability: estabilidade histórica disponível.
    - Risk Profile: ausência de penalidades e deal breakers.

    O cálculo não altera Investment Score nem Opportunity Score.
    """

    result = df.copy()

    business = _numeric_column(
        result,
        "Business Score",
        50.0,
    )
    valuation = _numeric_column(
        result,
        "Valuation Score",
        50.0,
    )
    financial = _numeric_column(
        result,
        "Financial Score",
        50.0,
    )
    timing = _numeric_column(
        result,
        "Timing Score",
        50.0,
    )

    confidence = _numeric_column(
        result,
        "Confidence Score",
        50.0,
    )

    if "Data Coverage %" in result.columns:
        coverage = _numeric_column(
            result,
            "Data Coverage %",
            50.0,
        )
        data_quality = (
            confidence * 0.70
            + coverage * 0.30
        )
    else:
        data_quality = confidence

    factor_agreement = _factor_agreement(
        business,
        valuation,
        financial,
        timing,
    )

    historical_stability = _historical_stability(result)

    if "Risk Penalty" in result.columns:
        risk_penalty = (
            pd.to_numeric(
                result["Risk Penalty"],
                errors="coerce",
            )
            .fillna(0.0)
            .clip(lower=0, upper=100)
        )
    else:
        risk_penalty = pd.Series(
            0.0,
            index=result.index,
            dtype="float64",
        )

    risk_profile = (
        100.0 - risk_penalty * 4.0
    ).clip(
        lower=0,
        upper=100,
    )

    conviction_base = (
        data_quality * 0.30
        + factor_agreement * 0.30
        + historical_stability * 0.20
        + risk_profile * 0.20
    )

    bonus = pd.Series(
        0.0,
        index=result.index,
        dtype="float64",
    )

    penalty = pd.Series(
        0.0,
        index=result.index,
        dtype="float64",
    )

    drivers: list[list[str]] = [
        [] for _ in range(len(result))
    ]

    def add_driver(
        condition: pd.Series,
        label: str,
    ) -> None:
        for position, active in enumerate(
            condition.fillna(False).tolist()
        ):
            if active:
                drivers[position].append(label)

    high_data_quality = data_quality >= 85
    high_agreement = factor_agreement >= 85
    high_stability = historical_stability >= 80
    low_risk = risk_penalty <= 0

    bonus += high_data_quality.astype(float) * 3
    bonus += high_agreement.astype(float) * 3
    bonus += high_stability.astype(float) * 2
    bonus += low_risk.astype(float) * 2

    add_driver(
        high_data_quality,
        "Dados completos e confiáveis (+3)",
    )
    add_driver(
        high_agreement,
        "Alta convergência entre fatores (+3)",
    )
    add_driver(
        high_stability,
        "Boa estabilidade histórica (+2)",
    )
    add_driver(
        low_risk,
        "Sem penalidades de risco (+2)",
    )

    low_data_quality = data_quality < 60
    low_agreement = factor_agreement < 55
    low_stability = historical_stability < 40
    high_risk = risk_penalty >= 15

    penalty += low_data_quality.astype(float) * 10
    penalty += low_agreement.astype(float) * 8
    penalty += low_stability.astype(float) * 5
    penalty += high_risk.astype(float) * 10

    add_driver(
        low_data_quality,
        "Qualidade dos dados baixa (-10)",
    )
    add_driver(
        low_agreement,
        "Fatores divergentes (-8)",
    )
    add_driver(
        low_stability,
        "Histórico instável ou insuficiente (-5)",
    )
    add_driver(
        high_risk,
        "Risco elevado (-10)",
    )

    conviction_score = (
        conviction_base
        + bonus
        - penalty
    ).clip(
        lower=0,
        upper=100,
    )

    result["Conviction Data Quality"] = data_quality.round(1)
    result["Conviction Factor Agreement"] = factor_agreement.round(1)
    result["Conviction Historical Stability"] = (
        historical_stability.round(1)
    )
    result["Conviction Risk Profile"] = risk_profile.round(1)

    result["Conviction Base"] = conviction_base.round(1)
    result["Conviction Bonus"] = bonus.round(1)
    result["Conviction Penalty"] = penalty.round(1)
    result["Conviction Score"] = conviction_score.round(1)

    result["Conviction Rating"] = (
        result["Conviction Score"]
        .apply(classify_conviction)
    )

    result["Conviction Drivers"] = [
        "; ".join(items) if items else "Nenhum"
        for items in drivers
    ]

    return result
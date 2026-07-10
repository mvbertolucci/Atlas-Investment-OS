from __future__ import annotations

from typing import Any

import pandas as pd


def _number(
    row: pd.Series,
    column: str,
) -> float | None:
    value = pd.to_numeric(
        row.get(column),
        errors="coerce",
    )

    if pd.isna(value):
        return None

    return float(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "n/a",
        "-",
        "nenhum",
    }:
        return ""

    return text


def _build_strengths(row: pd.Series) -> list[str]:
    strengths: list[str] = []

    business = _number(row, "Business Score")
    valuation = _number(row, "Valuation Score")
    financial = _number(row, "Financial Score")
    timing = _number(row, "Timing Score")
    opportunity = _number(row, "Opportunity Score")
    conviction = _number(row, "Conviction Score")
    confidence = _number(row, "Confidence Score")

    if business is not None:
        if business >= 80:
            strengths.append("Qualidade do negócio muito forte")
        elif business >= 70:
            strengths.append("Qualidade do negócio consistente")

    if valuation is not None:
        if valuation >= 80:
            strengths.append("Valuation muito atrativa")
        elif valuation >= 70:
            strengths.append("Valuation favorável")

    if financial is not None:
        if financial >= 80:
            strengths.append("Estrutura financeira muito sólida")
        elif financial >= 70:
            strengths.append("Estrutura financeira saudável")

    if timing is not None:
        if timing >= 75:
            strengths.append("Timing favorável")
        elif timing >= 65:
            strengths.append("Timing construtivo")

    if opportunity is not None:
        if opportunity >= 80:
            strengths.append("Opportunity Score elevado")
        elif opportunity >= 70:
            strengths.append("Oportunidade relevante")

    if conviction is not None:
        if conviction >= 85:
            strengths.append("Convicção muito alta")
        elif conviction >= 70:
            strengths.append("Convicção adequada")

    if confidence is not None and confidence >= 85:
        strengths.append("Boa qualidade e cobertura dos dados")

    return strengths


def _build_risks(row: pd.Series) -> list[str]:
    risks: list[str] = []

    business = _number(row, "Business Score")
    valuation = _number(row, "Valuation Score")
    financial = _number(row, "Financial Score")
    timing = _number(row, "Timing Score")
    conviction = _number(row, "Conviction Score")
    confidence = _number(row, "Confidence Score")
    risk_penalty = _number(row, "Risk Penalty")

    if business is not None and business < 50:
        risks.append("Qualidade do negócio abaixo do desejável")

    if valuation is not None and valuation < 40:
        risks.append("Valuation desfavorável")

    if financial is not None and financial < 45:
        risks.append("Estrutura financeira frágil")

    if timing is not None and timing < 40:
        risks.append("Timing fraco")

    if conviction is not None and conviction < 50:
        risks.append("Baixa convicção na avaliação")

    if confidence is not None and confidence < 60:
        risks.append("Cobertura ou qualidade dos dados limitada")

    if risk_penalty is not None and risk_penalty > 0:
        risks.append(
            f"Penalidade de risco de {risk_penalty:.1f} pontos"
        )

    deal_breakers = _clean_text(
        row.get("Deal Breakers")
    )

    if deal_breakers:
        risks.append(f"Deal breakers: {deal_breakers}")

    return risks


def _build_catalysts(row: pd.Series) -> list[str]:
    catalysts: list[str] = []

    opportunity = _number(row, "Opportunity Score")
    business = _number(row, "Business Score")
    valuation = _number(row, "Valuation Score")
    timing = _number(row, "Timing Score")

    if opportunity is not None and opportunity >= 75:
        catalysts.append("Reprecificação positiva da oportunidade")

    if (
        business is not None
        and business >= 75
        and valuation is not None
        and valuation >= 70
    ):
        catalysts.append(
            "Combinação de qualidade elevada com valuation favorável"
        )

    if timing is not None and timing >= 70:
        catalysts.append("Momento de mercado favorável")

    drivers = _clean_text(
        row.get("Opportunity Drivers")
    )

    if drivers:
        catalysts.append(drivers)

    return catalysts


def _build_summary(
    row: pd.Series,
    strengths: list[str],
    risks: list[str],
) -> str:
    symbol = _clean_text(row.get("symbol")) or "Ativo"
    decision = _clean_text(row.get("Decision Rating"))
    action = _clean_text(row.get("Suggested Action"))

    parts: list[str] = [symbol]

    if decision:
        parts.append(f"recebeu a classificação {decision}")

    if strengths:
        parts.append(
            "com suporte em "
            + ", ".join(strengths[:3]).lower()
        )

    if risks:
        parts.append(
            "mas exige atenção a "
            + ", ".join(risks[:2]).lower()
        )

    summary = " ".join(parts).strip()

    if action:
        summary += f". Ação sugerida: {action}"

    if not summary.endswith("."):
        summary += "."

    return summary


def build_thesis_for_row(
    row: pd.Series,
) -> dict[str, Any]:
    strengths = _build_strengths(row)
    risks = _build_risks(row)
    catalysts = _build_catalysts(row)

    return {
        "Investment Thesis": _build_summary(
            row,
            strengths,
            risks,
        ),
        "Thesis Strengths": (
            "; ".join(strengths)
            if strengths
            else "Nenhum destaque positivo relevante"
        ),
        "Thesis Risks": (
            "; ".join(risks)
            if risks
            else "Nenhum risco crítico identificado"
        ),
        "Thesis Catalysts": (
            "; ".join(catalysts)
            if catalysts
            else "Nenhum catalisador relevante identificado"
        ),
    }


def apply_investment_thesis(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Gera uma tese de investimento estruturada para cada ativo.

    Colunas criadas:

    - Investment Thesis
    - Thesis Strengths
    - Thesis Risks
    - Thesis Catalysts
    """

    result = df.copy()

    thesis_rows = result.apply(
        build_thesis_for_row,
        axis=1,
        result_type="expand",
    )

    for column in thesis_rows.columns:
        result[column] = thesis_rows[column]

    return result

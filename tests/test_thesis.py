from __future__ import annotations

import pandas as pd

from decision.thesis import (
    apply_investment_thesis,
    build_thesis_for_row,
)


def test_thesis_columns_are_created() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Decision Rating": ["★★★★ Comprar"],
            "Suggested Action": ["Considerar compra gradual"],
            "Business Score": [82.0],
            "Valuation Score": [76.0],
            "Financial Score": [80.0],
            "Timing Score": [72.0],
            "Opportunity Score": [84.0],
            "Conviction Score": [88.0],
            "Confidence Score": [90.0],
            "Risk Penalty": [0.0],
            "Deal Breakers": ["Nenhum"],
        }
    )

    result = apply_investment_thesis(df)

    expected = {
        "Investment Thesis",
        "Thesis Strengths",
        "Thesis Risks",
        "Thesis Catalysts",
    }

    assert expected.issubset(result.columns)


def test_strong_company_generates_positive_thesis() -> None:
    row = pd.Series(
        {
            "symbol": "AAA",
            "Decision Rating": "★★★★★ Forte Compra",
            "Suggested Action": "Considerar compra prioritária",
            "Business Score": 90.0,
            "Valuation Score": 84.0,
            "Financial Score": 88.0,
            "Timing Score": 76.0,
            "Opportunity Score": 91.0,
            "Conviction Score": 93.0,
            "Confidence Score": 95.0,
            "Risk Penalty": 0.0,
            "Deal Breakers": "Nenhum",
        }
    )

    thesis = build_thesis_for_row(row)

    assert "Qualidade do negócio muito forte" in thesis["Thesis Strengths"]
    assert "Valuation muito atrativa" in thesis["Thesis Strengths"]
    assert "Convicção muito alta" in thesis["Thesis Strengths"]
    assert thesis["Thesis Risks"] == "Nenhum risco crítico identificado"


def test_weak_company_generates_risk_thesis() -> None:
    row = pd.Series(
        {
            "symbol": "BBB",
            "Decision Rating": "Evitar",
            "Suggested Action": "Não comprar ou revisar posição",
            "Business Score": 42.0,
            "Valuation Score": 35.0,
            "Financial Score": 38.0,
            "Timing Score": 30.0,
            "Opportunity Score": 28.0,
            "Conviction Score": 40.0,
            "Confidence Score": 55.0,
            "Risk Penalty": 20.0,
            "Deal Breakers": "Piotroski baixo",
        }
    )

    thesis = build_thesis_for_row(row)

    assert "Qualidade do negócio abaixo do desejável" in thesis["Thesis Risks"]
    assert "Valuation desfavorável" in thesis["Thesis Risks"]
    assert "Deal breakers: Piotroski baixo" in thesis["Thesis Risks"]


def test_thesis_preserves_dataframe_rows() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Business Score": [80.0, 40.0],
        }
    )

    result = apply_investment_thesis(df)

    assert len(result) == 2
    assert result["symbol"].tolist() == ["AAA", "BBB"]


def test_missing_data_uses_safe_defaults() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
        }
    )

    result = apply_investment_thesis(df)

    assert result.loc[0, "Investment Thesis"].startswith("AAA")
    assert (
        result.loc[0, "Thesis Strengths"]
        == "Nenhum destaque positivo relevante"
    )
    assert (
        result.loc[0, "Thesis Risks"]
        == "Nenhum risco crítico identificado"
    )

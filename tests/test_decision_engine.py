from __future__ import annotations

import pandas as pd

from decision.engine import apply_decision


def test_decision_columns_are_created() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score": [90.0],
            "Conviction Score": [92.0],
            "Confidence Score": [95.0],
            "Investment Score": [85.0],
            "Business Score": [90.0],
            "Valuation Score": [82.0],
            "Financial Score": [88.0],
            "Timing Score": [75.0],
            "Risk Penalty": [0.0],
            "Deal Breakers": ["Nenhum"],
        }
    )

    result = apply_decision(df)

    expected_columns = {
        "Decision",
        "Decision Rating",
        "Suggested Action",
        "Decision Confidence",
        "Decision Drivers",
        "Decision Priority",
    }

    assert expected_columns.issubset(result.columns)


def test_strong_buy_decision() -> None:
    df = pd.DataFrame(
        {
            "Opportunity Score": [90.0],
            "Conviction Score": [92.0],
            "Confidence Score": [95.0],
            "Risk Penalty": [0.0],
            "Deal Breakers": ["Nenhum"],
        }
    )

    result = apply_decision(df)

    assert result.loc[0, "Decision"] == "STRONG_BUY"
    assert "Forte Compra" in result.loc[0, "Decision Rating"]


def test_deal_breaker_blocks_positive_decision() -> None:
    df = pd.DataFrame(
        {
            "Opportunity Score": [95.0],
            "Conviction Score": [95.0],
            "Confidence Score": [95.0],
            "Risk Penalty": [0.0],
            "Deal Breakers": ["Piotroski baixo"],
        }
    )

    result = apply_decision(df)

    assert result.loc[0, "Decision"] == "WATCH"
    assert "Deal Breakers" in result.loc[0, "Decision Drivers"]


def test_high_risk_results_in_avoid() -> None:
    df = pd.DataFrame(
        {
            "Opportunity Score": [90.0],
            "Conviction Score": [90.0],
            "Confidence Score": [90.0],
            "Risk Penalty": [25.0],
            "Deal Breakers": ["Nenhum"],
        }
    )

    result = apply_decision(df)

    assert result.loc[0, "Decision"] == "AVOID"
    assert (
        result.loc[0, "Suggested Action"]
        == "Não comprar ou revisar posição"
    )


def test_decision_confidence_is_reduced_by_risk() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["LOW_RISK", "HIGH_RISK"],
            "Opportunity Score": [80.0, 80.0],
            "Conviction Score": [80.0, 80.0],
            "Confidence Score": [80.0, 80.0],
            "Risk Penalty": [0.0, 20.0],
            "Deal Breakers": ["Nenhum", "Nenhum"],
        }
    )

    result = apply_decision(df)

    low_risk = result.loc[
        result["symbol"] == "LOW_RISK",
        "Decision Confidence",
    ].iloc[0]

    high_risk = result.loc[
        result["symbol"] == "HIGH_RISK",
        "Decision Confidence",
    ].iloc[0]

    assert low_risk > high_risk


def test_missing_scores_use_neutral_defaults() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
        }
    )

    result = apply_decision(df)

    assert result.loc[0, "Decision"] == "WATCH"
    assert 0 <= result.loc[0, "Decision Confidence"] <= 100
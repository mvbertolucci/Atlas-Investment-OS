from __future__ import annotations

import pandas as pd

from models.opportunity_model import apply_opportunity


def test_opportunity_score_is_created():
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Business Score": [80],
            "Valuation Score": [70],
            "Financial Score": [60],
            "Timing Score": [50],
            "Confidence Score": [90],
            "Risk Penalty": [0],
        }
    )

    result = apply_opportunity(df)

    assert "Opportunity Score" in result.columns
    assert "Opportunity Rating" in result.columns
    assert "Opportunity Drivers" in result.columns


def test_high_quality_gets_bonus():
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Business Score": [85],
            "Valuation Score": [70],
            "Financial Score": [60],
            "Timing Score": [50],
            "Confidence Score": [90],
            "Risk Penalty": [0],
        }
    )

    result = apply_opportunity(df)

    assert result.loc[0, "Opportunity Bonus"] >= 5
    assert "Business excelente" in result.loc[0, "Opportunity Drivers"]


def test_low_financial_gets_penalty():
    df = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Business Score": [70],
            "Valuation Score": [70],
            "Financial Score": [30],
            "Timing Score": [50],
            "Confidence Score": [80],
            "Risk Penalty": [0],
        }
    )

    result = apply_opportunity(df)

    assert result.loc[0, "Opportunity Penalty"] >= 10
    assert "Financial fraco" in result.loc[0, "Opportunity Drivers"]


def test_risk_penalty_reduces_opportunity():
    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Business Score": [70, 70],
            "Valuation Score": [70, 70],
            "Financial Score": [70, 70],
            "Timing Score": [70, 70],
            "Confidence Score": [80, 80],
            "Risk Penalty": [0, 20],
        }
    )

    result = apply_opportunity(df)

    score_without_penalty = result.loc[result["symbol"] == "AAA", "Opportunity Score"].iloc[0]
    score_with_penalty = result.loc[result["symbol"] == "BBB", "Opportunity Score"].iloc[0]

    assert score_without_penalty > score_with_penalty
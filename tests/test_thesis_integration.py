from __future__ import annotations

from pathlib import Path

import pandas as pd

import scoring.investment as investment
from reports.excel import write_latest_and_history
from reports.morning_brief import render_morning_brief


def _decision_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "name": ["Example Company"],
            "Investment Score": [82.0],
            "Opportunity Score": [86.0],
            "Opportunity Rating": ["★★★★ Opportunity"],
            "Opportunity Drivers": ["Business excelente (+5)"],
            "Conviction Score": [88.0],
            "Conviction Rating": ["★★★★ Convicção Alta"],
            "Decision": ["BUY"],
            "Decision Rating": ["★★★★ Comprar"],
            "Suggested Action": ["Considerar compra gradual"],
            "Decision Confidence": [89.0],
            "Decision Drivers": ["Opportunity muito alta"],
            "Decision Priority": [1],
            "Business Score": [84.0],
            "Valuation Score": [78.0],
            "Financial Score": [80.0],
            "Timing Score": [70.0],
            "Confidence Score": [92.0],
            "Risk Penalty": [0.0],
            "Deal Breakers": ["Nenhum"],
            "Recommendation": ["★★★★ Comprar"],
        }
    )


def test_scoring_pipeline_applies_thesis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "config"
    config.mkdir()

    features = config / "features.yaml"
    features.write_text("business: {}", encoding="utf-8")

    model = config / "model.yaml"
    model.write_text("factor_weights: {}", encoding="utf-8")

    deal_breakers = config / "deal_breakers.json"
    deal_breakers.write_text("{}", encoding="utf-8")

    frame = _decision_frame()

    monkeypatch.setattr(
        investment,
        "score_all_factors",
        lambda df, **kwargs: df.copy(),
    )
    monkeypatch.setattr(
        investment,
        "apply_opportunity",
        lambda df: df.copy(),
    )
    monkeypatch.setattr(
        investment,
        "apply_conviction",
        lambda df: df.copy(),
    )
    monkeypatch.setattr(
        investment,
        "apply_decision",
        lambda df: df.copy(),
    )
    monkeypatch.setattr(
        investment,
        "apply_recommendation",
        lambda df: df.copy(),
    )

    result = investment.score_dataframe(
        frame,
        model,
        deal_breakers,
    )

    assert "Investment Thesis" in result.columns
    assert "Thesis Strengths" in result.columns
    assert "Thesis Risks" in result.columns
    assert "Thesis Catalysts" in result.columns


def test_excel_contains_decision_analysis(
    tmp_path: Path,
) -> None:
    frame = _decision_frame()

    # Apply the real thesis engine through the scoring module import.
    frame = investment.apply_investment_thesis(frame)

    history_file, latest_file = write_latest_and_history(
        frame,
        tmp_path / "output",
    )

    assert history_file.exists()
    assert latest_file is not None
    assert latest_file.exists()

    workbook = pd.ExcelFile(latest_file)

    assert "Decision Analysis" in workbook.sheet_names

    decision_sheet = pd.read_excel(
        latest_file,
        sheet_name="Decision Analysis",
    )

    assert "Investment Thesis" in decision_sheet.columns
    assert "Thesis Strengths" in decision_sheet.columns
    assert "Thesis Risks" in decision_sheet.columns
    assert "Thesis Catalysts" in decision_sheet.columns


def test_morning_brief_contains_thesis(
    tmp_path: Path,
) -> None:
    frame = investment.apply_investment_thesis(
        _decision_frame()
    )

    text = render_morning_brief(
        current_df=frame,
        database_path=tmp_path / "atlas_history.db",
        top_count=1,
    )

    assert "Decisão:" in text
    assert "Conviction:" in text
    assert "Tese:" in text
    assert "Ação:" in text

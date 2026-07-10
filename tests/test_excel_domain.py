from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.excel import (
    _company_reports_dataframe,
    write_latest_and_history,
)
from reports.report_engine import build_company_reports


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "Decision": "BUY",
                "Decision Rating": "★★★★ Comprar",
                "Suggested Action": "Considerar compra gradual",
                "Decision Confidence": 88.0,
                "Decision Drivers": "Opportunity alta; Conviction alta",
                "Investment Thesis": "Tese Alpha",
                "Thesis Strengths": "Business forte; Valuation atrativa",
                "Thesis Risks": "Ciclicidade",
                "Thesis Catalysts": "Expansão de margens",
                "Opportunity Score": 90.0,
                "Conviction Score": 86.0,
                "Investment Score": 82.0,
                "Business Score": 84.0,
                "Valuation Score": 78.0,
                "Financial Score": 80.0,
                "Timing Score": 70.0,
                "Confidence Score": 92.0,
                "Risk Penalty": 0.0,
                "Deal Breakers": "Nenhum",
                "Recommendation": "★★★★ Comprar",
            }
        ]
    )


def test_company_reports_dataframe_uses_domain_model() -> None:
    reports = build_company_reports(_frame())

    result = _company_reports_dataframe(reports)

    assert len(result) == 1
    assert result.loc[0, "symbol"] == "AAA"
    assert result.loc[0, "Investment Thesis"] == "Tese Alpha"
    assert (
        result.loc[0, "Thesis Strengths"]
        == "Business forte; Valuation atrativa"
    )
    assert (
        result.loc[0, "Decision Drivers"]
        == "Opportunity alta; Conviction alta"
    )


def test_excel_decision_analysis_is_generated(
    tmp_path: Path,
) -> None:
    history_file, latest_file = write_latest_and_history(
        _frame(),
        tmp_path / "output",
    )

    assert history_file.exists()
    assert latest_file is not None
    assert latest_file.exists()

    workbook = pd.ExcelFile(latest_file)

    assert "Decision Analysis" in workbook.sheet_names

    sheet = pd.read_excel(
        latest_file,
        sheet_name="Decision Analysis",
    )

    assert "Decision" in sheet.columns
    assert "Investment Thesis" in sheet.columns
    assert "Thesis Strengths" in sheet.columns
    assert "Thesis Risks" in sheet.columns
    assert "Thesis Catalysts" in sheet.columns

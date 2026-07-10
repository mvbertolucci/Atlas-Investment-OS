from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.morning_brief import (
    build_morning_brief_tables,
    build_top_opportunities,
    render_morning_brief,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "Opportunity Score": 90.0,
                "Conviction Score": 88.0,
                "Decision": "BUY",
                "Decision Rating": "★★★★ Comprar",
                "Suggested Action": "Considerar compra gradual",
                "Decision Confidence": 89.0,
                "Investment Thesis": "Tese Alpha",
                "Thesis Risks": "Risco A",
                "Decision Drivers": "Alta convicção",
            },
            {
                "symbol": "BBB",
                "name": "Beta",
                "Opportunity Score": 70.0,
                "Conviction Score": 72.0,
                "Decision": "ACCUMULATE",
                "Decision Rating": "★★★ Acumular",
                "Suggested Action": "Considerar aumentar posição",
                "Decision Confidence": 74.0,
                "Investment Thesis": "Tese Beta",
                "Thesis Risks": "Nenhum risco crítico identificado",
                "Decision Drivers": "Opportunity atrativa",
            },
        ]
    )


def test_top_opportunities_use_company_reports() -> None:
    result = build_top_opportunities(
        _frame(),
        top_count=1,
    )

    assert len(result) == 1
    assert result.loc[0, "symbol"] == "AAA"
    assert result.loc[0, "Investment Thesis"] == "Tese Alpha"


def test_brief_tables_expose_domain_reports(
    tmp_path: Path,
) -> None:
    data = build_morning_brief_tables(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=2,
    )

    assert len(data["company_reports"]) == 2
    assert data["top_reports"][0].symbol == "AAA"
    assert data["top_reports"][0].investment_thesis == "Tese Alpha"


def test_render_brief_uses_company_report_fields(
    tmp_path: Path,
) -> None:
    text = render_morning_brief(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=1,
    )

    assert "AAA" in text
    assert "Decisão: ★★★★ Comprar" in text
    assert "Conviction: 88.0" in text
    assert "Tese: Tese Alpha" in text
    assert "Riscos: Risco A" in text
    assert "Ação: Considerar compra gradual" in text
    assert "Drivers: Alta convicção" in text

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

import run_all
from portfolio.report import PortfolioReport


def _portfolio_report() -> PortfolioReport:
    return PortfolioReport(
        portfolio_name="Atlas Portfolio",
        generated_at=datetime(2026, 7, 12, 9, 0, 0),
        summary={},
        allocation={},
        concentration={},
        quality={},
        rebalance={},
    )


def test_generate_morning_brief_forwards_portfolio_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _portfolio_report()
    output = tmp_path / "morning_brief.md"
    received: list[PortfolioReport | None] = []

    def fake_write_morning_brief(**kwargs):
        received.append(kwargs.get("portfolio_report"))
        return output

    def fake_render_morning_brief(**kwargs):
        received.append(kwargs.get("portfolio_report"))
        return "portfolio brief"

    monkeypatch.setattr(
        run_all,
        "write_morning_brief",
        fake_write_morning_brief,
    )
    monkeypatch.setattr(
        run_all,
        "render_morning_brief",
        fake_render_morning_brief,
    )

    result_path, text = run_all.generate_morning_brief(
        pd.DataFrame(),
        portfolio_report=report,
    )

    assert result_path == output
    assert text == "portfolio brief"
    assert received == [report, report]

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from reports.research_excel import build_combined_workbook


def _ranking(total: int, eligible: int, candidates: int) -> dict:
    return {
        "generated_at": "2026-07-14T00:00:00",
        "summary": {
            "total_count": total,
            "universe_eligible_count": eligible,
            "candidate_count": candidates,
            "blocked_by_reason": {"CONFIDENCE_BELOW_MINIMUM": 1},
        },
        "companies": [
            {
                "symbol": "AAA",
                "sector": "Tech",
                "universe_eligible": True,
                "safeguard_passed": True,
                "safeguard_reasons": [],
                "market_rank": 1,
                "investment_score": 80.0,
                "opportunity_score": 70.0,
                "conviction_score": 85.0,
                "confidence_score": 90.0,
                "candidate_rank": 1,
                "already_held": True,
            },
            {
                "symbol": "BBB",
                "sector": "Health",
                "universe_eligible": True,
                "safeguard_passed": False,
                "safeguard_reasons": ["CONFIDENCE_BELOW_MINIMUM"],
                "market_rank": 2,
                "investment_score": 60.0,
                "opportunity_score": 50.0,
                "conviction_score": 55.0,
                "confidence_score": 40.0,
                "candidate_rank": None,
                "already_held": False,
            },
        ],
    }


def _portfolio() -> dict:
    return {
        "summary": {"position_count": 1, "invested_weight": 0.05},
        "positions": [
            {
                "candidate_rank": 1,
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "industry": "Software",
                "target_weight": 0.05,
                "investment_score": 80.0,
                "reference_price": 123.45,
            }
        ],
    }


def _write_screener(output_dir: Path, label: str) -> None:
    suffix = f"_{label}" if label else ""
    (output_dir / f"research_ranking_report{suffix}.json").write_text(
        json.dumps(_ranking(2, 2, 1)), encoding="utf-8"
    )
    (output_dir / f"model_portfolio_report{suffix}.json").write_text(
        json.dumps(_portfolio()), encoding="utf-8"
    )


def test_combined_workbook_joins_all_three_screeners(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    for label in ("", "market", "adr"):
        _write_screener(output_dir, label)

    workbook_path = build_combined_workbook(
        (("", "S&P 500"), ("market", "Mercado Amplo"), ("adr", "ADR")),
        output_dir,
        output_dir / "combined.xlsx",
    )

    xl = pd.ExcelFile(workbook_path)
    assert set(xl.sheet_names) == {"Resumo", "Carteira Modelo", "Todos os Itens"}

    summary = xl.parse("Resumo")
    assert list(summary["Screener"]) == ["S&P 500", "Mercado Amplo", "ADR"]
    assert summary["Candidatos"].tolist() == [1, 1, 1]

    positions = xl.parse("Carteira Modelo")
    assert len(positions) == 3  # 1 posição x 3 screeners
    assert set(positions["Screener"]) == {"S&P 500", "Mercado Amplo", "ADR"}

    companies = xl.parse("Todos os Itens")
    assert len(companies) == 6  # 2 empresas x 3 screeners
    assert set(companies["Screener"]) == {"S&P 500", "Mercado Amplo", "ADR"}
    aaa_rows = companies[companies["Símbolo"] == "AAA"]
    assert (aaa_rows["Status"] == "Candidato #1").all()


def test_missing_screener_is_omitted_not_an_error(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _write_screener(output_dir, "")  # só S&P 500, sem market/adr

    workbook_path = build_combined_workbook(
        (("", "S&P 500"), ("market", "Mercado Amplo"), ("adr", "ADR")),
        output_dir,
        output_dir / "combined.xlsx",
    )
    summary = pd.ExcelFile(workbook_path).parse("Resumo")
    assert list(summary["Screener"]) == ["S&P 500"]


def test_no_screener_collected_raises() -> None:
    with pytest.raises(FileNotFoundError):
        build_combined_workbook(
            (("", "S&P 500"),),
            Path("/definitely/does/not/exist"),
            Path("/definitely/does/not/exist/combined.xlsx"),
        )

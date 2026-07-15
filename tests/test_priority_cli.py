"""
Tests for the priority CLI's file-loading glue (priority/cli.py).

Exercises reading real files from disk (ranking_report.json,
research_ranking_report.json, portfolio_report.json, portfolio.csv) -- the
part the pure pipeline tests in test_priority_pipeline.py cannot cover.
"""
from __future__ import annotations

import json
from pathlib import Path

from priority.cli import build_priority_from_files


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _ranking_report(companies: list[dict]) -> dict:
    return {"companies": companies}


def _company(symbol, score, deal_breakers=(), **kwargs) -> dict:
    return {
        "symbol": symbol,
        "sector": kwargs.get("sector", "Technology"),
        "safeguard_passed": kwargs.get("safeguard_passed", not deal_breakers),
        "candidate_rank": kwargs.get("candidate_rank"),
        "investment_score": score,
        "opportunity_score": score,
        "conviction_score": score,
        "confidence_score": 100.0,
        "deal_breakers": list(deal_breakers),
    }


def test_build_priority_reads_sell_side_from_disk(tmp_path: Path) -> None:
    ranking_path = tmp_path / "ranking_report.json"
    portfolio_path = tmp_path / "portfolio.csv"

    _write_json(
        ranking_path,
        _ranking_report(
            [
                _company("AAA", 80.0),
                _company("BBB", 30.0, deal_breakers=["Piotroski baixo"]),
            ]
        ),
    )
    portfolio_path.write_text(
        "symbol,quantity,average_price\nAAA,1,10\nBBB,1,10\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / "portfolio_report.json",
        {
            "allocation": {"by_symbol": {"AAA": 0.6, "BBB": 0.4}},
            "rebalance": {
                "actions": [
                    {
                        "symbol": "BBB",
                        "action": "REVISAR",
                        "current_weight": 0.4,
                        "reason": "Tese ausente",
                        "priority": 20,
                    },
                    {
                        "symbol": "AAA",
                        "action": "HOLD",
                        "current_weight": 0.6,
                        "reason": "Nenhuma regra acionada",
                        "priority": 50,
                    },
                ]
            },
        },
    )

    report = build_priority_from_files(
        ranking_report_path=ranking_path,
        research_ranking_report_path=tmp_path / "missing.json",
        portfolio_path=portfolio_path,
    )

    assert [item.symbol for item in report.sell.items] == ["BBB", "AAA"]
    assert report.sell.items[0].action == "REVISAR"
    assert report.sell.items[0].reason == "Tese ausente"
    assert report.buy is None


def test_build_priority_reads_buy_side_when_present(tmp_path: Path) -> None:
    ranking_path = tmp_path / "ranking_report.json"
    research_path = tmp_path / "research_ranking_report.json"
    portfolio_path = tmp_path / "portfolio.csv"

    _write_json(ranking_path, _ranking_report([]))
    _write_json(
        research_path,
        _ranking_report(
            [_company("NEW", 90.0, candidate_rank=1)]
        ),
    )
    portfolio_path.write_text(
        "symbol,quantity,average_price\n",
        encoding="utf-8",
    )

    report = build_priority_from_files(
        ranking_report_path=ranking_path,
        research_ranking_report_path=research_path,
        portfolio_path=portfolio_path,
    )

    assert report.buy is not None
    assert report.buy.items[0].symbol == "NEW"


def test_build_priority_handles_missing_portfolio_file(tmp_path: Path) -> None:
    ranking_path = tmp_path / "ranking_report.json"
    _write_json(ranking_path, _ranking_report([_company("AAA", 50.0)]))

    report = build_priority_from_files(
        ranking_report_path=ranking_path,
        research_ranking_report_path=tmp_path / "missing.json",
        portfolio_path=tmp_path / "also_missing.csv",
    )

    # Sem PortfolioReport não existe uma fonte oficial de decisão de venda.
    assert report.sell.items == ()


def test_build_priority_applies_top_n_and_exclude_held(tmp_path: Path) -> None:
    ranking_path = tmp_path / "ranking_report.json"
    research_path = tmp_path / "research_ranking_report.json"
    portfolio_path = tmp_path / "portfolio.csv"

    _write_json(ranking_path, _ranking_report([]))
    _write_json(
        research_path,
        _ranking_report(
            [
                _company("HELD", 90.0, candidate_rank=1),
                _company("NEW", 80.0, candidate_rank=2),
                _company("OTHER", 70.0, candidate_rank=3),
            ]
        ),
    )
    portfolio_path.write_text(
        "symbol,quantity,average_price\nHELD,1,10\n",
        encoding="utf-8",
    )

    report = build_priority_from_files(
        ranking_report_path=ranking_path,
        research_ranking_report_path=research_path,
        portfolio_path=portfolio_path,
        exclude_held=True,
        top_n=1,
    )

    assert [item.symbol for item in report.buy.items] == ["NEW"]

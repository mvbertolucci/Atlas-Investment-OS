from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import run_all
from portfolio.report import PortfolioReport
from ranking.models import RankedCompany, RankingPolicy, RankingReport


def _ranking_report() -> RankingReport:
    return RankingReport(
        policy=RankingPolicy(name="Test"),
        companies=(
            RankedCompany(
                symbol="AAA",
                sector="Technology",
                universe_eligible=True,
                safeguard_passed=True,
                safeguard_reasons=(),
                market_rank=1,
                sector_rank=1,
                candidate_rank=1,
                investment_score=80.0,
                opportunity_score=80.0,
                conviction_score=80.0,
                confidence_score=100.0,
                deal_breakers=(),
            ),
            RankedCompany(
                symbol="BBB",
                sector="Technology",
                universe_eligible=True,
                safeguard_passed=False,
                safeguard_reasons=("DEAL_BREAKER_TRIGGERED",),
                market_rank=2,
                sector_rank=2,
                candidate_rank=None,
                investment_score=20.0,
                opportunity_score=20.0,
                conviction_score=20.0,
                confidence_score=95.0,
                deal_breakers=("Piotroski baixo",),
            ),
        ),
    )


def _portfolio_report() -> PortfolioReport:
    return PortfolioReport(
        portfolio_name="Test",
        generated_at=datetime(2026, 7, 15),
        summary={},
        allocation={"by_symbol": {"AAA": 0.6, "BBB": 0.4}},
        concentration={},
        quality={},
        rebalance={
            "actions": [
                {
                    "symbol": "AAA",
                    "action": "TRIM",
                    "current_weight": 0.6,
                    "reason": "fundamental_decay acionada",
                    "priority": 10,
                    "triggered_rules": ["fundamental_decay"],
                    "missing_data": [],
                },
                {
                    "symbol": "BBB",
                    "action": "HOLD",
                    "current_weight": 0.4,
                    "reason": "Nenhuma regra de venda acionada",
                    "priority": 50,
                    "triggered_rules": [],
                    "missing_data": [],
                },
            ]
        },
    )


def test_generate_priority_report_writes_official_rebalance_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "priority_report.json"
    monkeypatch.setattr(run_all, "PRIORITY_REPORT_FILE", output)
    monkeypatch.setattr(
        run_all,
        "RESEARCH_RANKING_REPORT_FILE",
        tmp_path / "absent.json",
    )

    path, report = run_all.generate_priority_report(
        {"priority_enabled": True},
        ranking_report=_ranking_report(),
        portfolio_report=_portfolio_report(),
    )

    assert path == output
    assert report.buy is None
    data = json.loads(output.read_text(encoding="utf-8"))
    symbols = [item["symbol"] for item in data["sell"]["items"]]
    assert symbols == ["AAA", "BBB"]
    assert data["sell"]["items"][0]["action"] == "TRIM"
    assert data["sell"]["items"][0]["triggered_rules"] == [
        "fundamental_decay"
    ]
    # BBB tem Deal Breaker no ranking, mas a voz oficial do rebalance é HOLD.
    assert data["sell"]["items"][1]["action"] == "HOLD"
    assert data["buy"] is None


def test_generate_priority_report_has_no_sell_voice_without_portfolio_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "priority_report.json"
    monkeypatch.setattr(run_all, "PRIORITY_REPORT_FILE", output)
    monkeypatch.setattr(
        run_all,
        "RESEARCH_RANKING_REPORT_FILE",
        tmp_path / "absent.json",
    )

    _, report = run_all.generate_priority_report(
        {"priority_enabled": True},
        ranking_report=_ranking_report(),
        portfolio_report=None,
    )

    assert report.sell.items == ()


def test_generate_priority_report_reads_buy_side_when_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "priority_report.json"
    research_path = tmp_path / "research_ranking_report.json"
    research_path.write_text(
        json.dumps(_ranking_report().to_dict()),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_all, "PRIORITY_REPORT_FILE", output)
    monkeypatch.setattr(
        run_all,
        "RESEARCH_RANKING_REPORT_FILE",
        research_path,
    )

    run_all.generate_priority_report(
        {"priority_enabled": True},
        ranking_report=None,
        portfolio_report=None,
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["buy"] is not None
    assert data["buy"]["items"][0]["symbol"] == "AAA"


def test_generate_priority_report_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "priority_report.json"
    monkeypatch.setattr(run_all, "PRIORITY_REPORT_FILE", output)

    result = run_all.generate_priority_report(
        {"priority_enabled": False},
        ranking_report=_ranking_report(),
        portfolio_report=None,
    )

    assert result is None
    assert not output.exists()

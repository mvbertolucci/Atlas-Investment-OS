from __future__ import annotations

import json
from pathlib import Path

import run_all
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


def test_generate_priority_report_writes_sell_classification(
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
        portfolio_report=None,
    )

    assert path == output
    assert report.buy is None
    data = json.loads(output.read_text(encoding="utf-8"))
    symbols = [item["symbol"] for item in data["sell"]["items"]]
    assert symbols == ["AAA", "BBB"]
    assert data["sell"]["items"][1]["action"] == "SELL"
    assert data["buy"] is None


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

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio.model_portfolio import (
    ModelPortfolioPolicy,
    PortfolioConstructionError,
    build_model_portfolio,
    load_model_portfolio_policy,
    write_model_portfolio_report,
)
from ranking.models import RankedCompany, RankingPolicy, RankingReport


def _ranking(count: int = 24) -> RankingReport:
    companies = []
    sectors = ["Technology", "Financials", "Industrials", "Health", "Energy", "Utilities"]
    for index in range(count):
        companies.append(
            RankedCompany(
                symbol=f"S{index:02d}",
                sector=sectors[index // 4],
                universe_eligible=True,
                safeguard_passed=True,
                safeguard_reasons=(),
                market_rank=index + 1,
                sector_rank=index % 4 + 1,
                candidate_rank=index + 1,
                investment_score=90.0 - index,
                opportunity_score=80.0,
                conviction_score=75.0,
                confidence_score=90.0,
                deal_breakers=(),
            )
        )
    return RankingReport(RankingPolicy("Test"), tuple(companies))


def test_canonical_model_portfolio_policy_is_pinned() -> None:
    policy = load_model_portfolio_policy("config/model_portfolio.yaml")
    assert policy.to_dict() == {
        "name": "Atlas Equal-Weight Research Portfolio",
        "target_positions": 20,
        "weighting_method": "equal",
        "max_position_weight": 0.05,
        "max_sector_weight": 0.20,
        "cash_weight": 0.0,
        "max_initial_turnover": 1.0,
    }


def test_builder_selects_ranked_candidates_under_sector_cap() -> None:
    report = build_model_portfolio(
        _ranking(),
        ModelPortfolioPolicy("Test"),
        metadata={"S00": {"name": "First", "price": 123.45}},
        universe_snapshot_date="2026-07-13",
    )
    assert len(report.positions) == 20
    assert report.invested_weight == 1.0
    assert max(report.sector_weights.values()) <= 0.20
    assert all(position.target_weight == 0.05 for position in report.positions)
    assert report.positions[0].symbol == "S00"
    assert report.positions[0].name == "First"
    assert report.positions[0].reference_price == 123.45
    assert report.to_dict()["advisory_only"] is True


def test_sector_cap_skips_higher_ranked_concentration() -> None:
    base = _ranking()
    concentrated = tuple(
        RankedCompany(
            **{
                **company.__dict__,
                "sector": "Technology" if index < 8 else company.sector,
            }
        )
        for index, company in enumerate(base.companies)
    )
    ranking = RankingReport(base.policy, concentrated)
    report = build_model_portfolio(ranking, ModelPortfolioPolicy("Test"))
    assert [item.symbol for item in report.positions[:5]] == [
        "S00", "S01", "S02", "S03", "S08"
    ]
    assert report.warnings == (
        "4 candidato(s) superior(es) ignorado(s) pelo limite setorial.",
    )


def test_insufficient_diversified_candidates_fails_explicitly() -> None:
    with pytest.raises(PortfolioConstructionError, match="Candidatos insuficientes"):
        build_model_portfolio(
            _ranking(4),
            ModelPortfolioPolicy("Test"),
        )


def test_policy_rejects_incompatible_constraints() -> None:
    with pytest.raises(ValueError, match="max_position_weight"):
        ModelPortfolioPolicy("Invalid", max_position_weight=0.04)
    with pytest.raises(ValueError, match="weighting_method"):
        ModelPortfolioPolicy("Invalid", weighting_method="score")
    with pytest.raises(ValueError, match="max_initial_turnover"):
        ModelPortfolioPolicy("Invalid", max_initial_turnover=0.50)


def test_report_writer_serializes_contract(tmp_path: Path) -> None:
    report = build_model_portfolio(_ranking(), ModelPortfolioPolicy("Test"))
    output = write_model_portfolio_report(report, tmp_path / "model.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["position_count"] == 20
    assert payload["summary"]["invested_weight"] == 1.0
    assert payload["summary"]["expected_initial_turnover"] == 1.0


def test_builder_contract_validation() -> None:
    with pytest.raises(TypeError, match="RankingReport"):
        build_model_portfolio(object(), ModelPortfolioPolicy("Test"))  # type: ignore[arg-type]

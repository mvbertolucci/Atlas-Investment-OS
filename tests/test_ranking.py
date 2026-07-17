from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import csv

from ranking import (
    RankingPolicy,
    load_ranking_policy,
    rank_companies,
    write_candidate_ranking_csv,
    write_ranking_report,
)
from ranking.models import RankedCompany, RankingReport
from universe import UniversePolicy, evaluate_universe


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "AAA", "sector": "Technology", "Investment Score": 80,
             "Opportunity Score": 70, "Conviction Score": 90,
             "Confidence Score": 100, "Deal Breakers": "Nenhum"},
            {"symbol": "BBB", "sector": "Technology", "Investment Score": 80,
             "Opportunity Score": 75, "Conviction Score": 80,
             "Confidence Score": 100, "Deal Breakers": "Nenhum"},
            {"symbol": "CCC", "sector": "Financials", "Investment Score": 60,
             "Opportunity Score": 90, "Conviction Score": 90,
             "Confidence Score": 60, "Deal Breakers": "Nenhum"},
            {"symbol": "DDD", "sector": "Industrials", "Investment Score": 70,
             "Opportunity Score": 80, "Conviction Score": 80,
             "Confidence Score": 100, "Deal Breakers": "Altman Z baixo"},
        ]
    )


def _universe(frame: pd.DataFrame):
    metadata = frame[["symbol", "sector"]].copy()
    metadata["quote_type"] = "EQUITY"
    metadata["currency"] = "USD"
    metadata["country"] = "United States"
    metadata["price"] = 100.0
    metadata["market_cap"] = 10_000_000_000.0
    metadata["volume"] = 1_000_000.0
    return evaluate_universe(
        metadata,
        UniversePolicy("US", "S&P 500", "monthly"),
    )


def test_canonical_ranking_policy_is_pinned() -> None:
    policy = load_ranking_policy("config/ranking.yaml")
    assert policy.to_dict() == {
        "name": "Atlas Analytical Ranking",
        "primary_score": "Investment Score",
        "tie_breakers": ["Opportunity Score", "Conviction Score"],
        "min_confidence_score": 70.0,
        "min_data_coverage_score": 70.0,
        "min_source_quality_score": 70.0,
        "min_data_freshness_score": 70.0,
        "require_required_features": True,
        "require_no_deal_breakers": True,
    }


def test_market_and_sector_ranking_are_deterministic() -> None:
    frame = _frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    by_symbol = {company.symbol: company for company in report.companies}

    assert by_symbol["BBB"].market_rank == 1
    assert by_symbol["BBB"].sector_rank == 1
    assert by_symbol["AAA"].market_rank == 2
    assert by_symbol["AAA"].sector_rank == 2
    assert by_symbol["BBB"].candidate_rank == 1
    assert by_symbol["AAA"].candidate_rank == 2


def test_safeguards_reuse_confidence_and_deal_breakers() -> None:
    frame = _frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    by_symbol = {company.symbol: company for company in report.companies}

    assert by_symbol["CCC"].safeguard_reasons == ("CONFIDENCE_BELOW_MINIMUM",)
    assert by_symbol["DDD"].safeguard_reasons == ("DEAL_BREAKER_TRIGGERED",)
    assert report.candidate_count == 2
    assert report.blocked_by_reason == {
        "CONFIDENCE_BELOW_MINIMUM": 1,
        "DEAL_BREAKER_TRIGGERED": 1,
    }


def test_universe_ineligible_company_has_no_market_rank() -> None:
    frame = _frame()
    universe = _universe(frame)
    member = universe.members[0]
    altered = type(universe)(
        policy=universe.policy,
        members=(
            type(member)(**{**member.__dict__, "eligible": False,
                            "exclusion_reasons": ("TEST",)}),
            *universe.members[1:],
        ),
    )

    report = rank_companies(frame, altered, RankingPolicy("Test"))
    aaa = next(company for company in report.companies if company.symbol == "AAA")
    assert aaa.market_rank is None
    assert aaa.safeguard_reasons == ("UNIVERSE_INELIGIBLE",)


def test_missing_confidence_is_explicit() -> None:
    frame = _frame()
    frame.loc[0, "Confidence Score"] = None
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    aaa = next(company for company in report.companies if company.symbol == "AAA")
    assert aaa.safeguard_reasons == ("MISSING_CONFIDENCE_SCORE",)


def test_missing_primary_score_is_explicit() -> None:
    frame = _frame()
    frame.loc[0, "Investment Score"] = None
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    aaa = next(company for company in report.companies if company.symbol == "AAA")
    assert aaa.safeguard_reasons == ("MISSING_PRIMARY_SCORE",)
    assert aaa.candidate_rank is None


def test_canonical_quality_gates_block_missing_critical_feature() -> None:
    frame = _frame()
    frame["Data Coverage"] = 90.0
    frame["Source Quality"] = 80.0
    frame["Data Freshness"] = 100.0
    frame["Missing Required Features"] = "Nenhum"
    frame.loc[0, "Missing Required Features"] = "valuation:pe"
    policy = load_ranking_policy("config/ranking.yaml")
    report = rank_companies(frame, _universe(frame), policy)
    aaa = next(company for company in report.companies if company.symbol == "AAA")
    assert "MISSING_REQUIRED_FEATURES" in aaa.safeguard_reasons
    assert aaa.missing_required_features == ("valuation:pe",)


def test_canonical_quality_gates_are_independent() -> None:
    frame = _frame()
    frame["Data Coverage"] = 90.0
    frame["Source Quality"] = 80.0
    frame["Data Freshness"] = 100.0
    frame["Missing Required Features"] = "Nenhum"
    frame.loc[0, "Data Coverage"] = 60.0
    frame.loc[1, "Source Quality"] = 50.0
    frame.loc[2, "Data Freshness"] = 0.0
    report = rank_companies(
        frame,
        _universe(frame),
        load_ranking_policy("config/ranking.yaml"),
    )
    by_symbol = {company.symbol: company for company in report.companies}
    assert "DATA_COVERAGE_BELOW_MINIMUM" in by_symbol["AAA"].safeguard_reasons
    assert "SOURCE_QUALITY_BELOW_MINIMUM" in by_symbol["BBB"].safeguard_reasons
    assert "DATA_FRESHNESS_BELOW_MINIMUM" in by_symbol["CCC"].safeguard_reasons


def test_report_serialization(tmp_path: Path) -> None:
    frame = _frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    output = write_ranking_report(report, tmp_path / "ranking.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["candidate_count"] == 2


def test_already_held_reflects_portfolio_origin_never_watchlist_or_absent() -> None:
    """
    already_held comes from the `origin` column run_all.merge_watchlist_with_portfolio
    tags each row with. A frame without that column (point-in-time replay,
    broad research collection) must default to False, never crash or guess.
    """
    frame = _frame()
    frame["origin"] = ["portfolio", "watchlist", "portfolio", "watchlist"]
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    by_symbol = {company.symbol: company for company in report.companies}

    assert by_symbol["AAA"].already_held is True
    assert by_symbol["BBB"].already_held is False
    assert by_symbol["CCC"].already_held is True
    assert by_symbol["DDD"].already_held is False

    frame_without_origin = _frame()
    report_without_origin = rank_companies(
        frame_without_origin, _universe(frame_without_origin), RankingPolicy("Test")
    )
    assert all(
        company.already_held is False for company in report_without_origin.companies
    )


def test_contract_validation() -> None:
    with pytest.raises(ValueError, match="entre 0 e 100"):
        RankingPolicy("Invalid", min_confidence_score=101)
    with pytest.raises(TypeError, match="DataFrame"):
        rank_companies([], None, None)  # type: ignore[arg-type]


def _candidate(symbol: str, sector: str, rank: int) -> RankedCompany:
    return RankedCompany(
        symbol=symbol,
        sector=sector,
        universe_eligible=True,
        safeguard_passed=True,
        safeguard_reasons=(),
        market_rank=rank,
        sector_rank=1,
        candidate_rank=rank,
        investment_score=90.0 - rank,
        opportunity_score=80.0,
        conviction_score=75.0,
        confidence_score=95.0,
        deal_breakers=(),
    )


def test_candidate_csv_lists_all_candidates_in_buy_order(tmp_path: Path) -> None:
    blocked = RankedCompany(
        symbol="ZZZ",
        sector="Energy",
        universe_eligible=True,
        safeguard_passed=False,
        safeguard_reasons=("CONFIDENCE",),
        market_rank=None,
        sector_rank=None,
        candidate_rank=None,
        investment_score=50.0,
        opportunity_score=None,
        conviction_score=None,
        confidence_score=40.0,
        deal_breakers=(),
    )
    report = RankingReport(
        RankingPolicy("Test"),
        (_candidate("BBB", "Technology", 2), _candidate("AAA", "Technology", 1), blocked),
    )
    path = write_candidate_ranking_csv(
        report,
        tmp_path / "research_candidates.csv",
        metadata={"AAA": {"name": "Alpha Co", "price": 12.5, "market_cap": 1e9}},
    )
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    # Só os candidatos (o bloqueado ZZZ fica de fora), em ordem de candidate_rank.
    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]
    assert rows[0]["candidate_rank"] == "1"
    assert rows[0]["name"] == "Alpha Co"
    assert rows[0]["price"] == "12.5"
    # Sem metadata, nome/preço ficam vazios mas o candidato continua listado.
    assert rows[1]["name"] == ""
    assert rows[1]["price"] == ""

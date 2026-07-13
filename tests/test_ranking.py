from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ranking import (
    RankingPolicy,
    load_ranking_policy,
    rank_companies,
    write_ranking_report,
)
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


def test_report_serialization(tmp_path: Path) -> None:
    frame = _frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    output = write_ranking_report(report, tmp_path / "ranking.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["candidate_count"] == 2


def test_contract_validation() -> None:
    with pytest.raises(ValueError, match="entre 0 e 100"):
        RankingPolicy("Invalid", min_confidence_score=101)
    with pytest.raises(TypeError, match="DataFrame"):
        rank_companies([], None, None)  # type: ignore[arg-type]

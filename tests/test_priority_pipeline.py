"""
Tests for the priority classification layer (sell/buy).

Pure functions over already-computed ranking data -- no scoring, no
portfolio-weight construction. Tests lock: sorting by quality, the
SELL/HOLD split on Deal Breaker presence, buy-side safeguard filtering,
held/exclude-held/sector/top_n filters, and that neither builder assigns
any target weight.
"""
from __future__ import annotations

from priority.models import BuyPriorityReport, SellPriorityReport
from priority.pipeline import build_buy_priority, build_sell_priority


def _ranked(symbol, score, deal_breakers=(), **kwargs):
    return {
        "symbol": symbol,
        "sector": kwargs.get("sector", "Technology"),
        "safeguard_passed": kwargs.get("safeguard_passed", not deal_breakers),
        "candidate_rank": kwargs.get("candidate_rank"),
        "investment_score": score,
        "opportunity_score": kwargs.get("opportunity_score", score),
        "conviction_score": kwargs.get("conviction_score", score),
        "confidence_score": kwargs.get("confidence_score", 100.0),
        "deal_breakers": list(deal_breakers),
    }


def test_sell_priority_sorts_by_score_descending() -> None:
    companies = [
        _ranked("AAA", 40.0),
        _ranked("BBB", 80.0),
        _ranked("CCC", 60.0),
    ]

    report = build_sell_priority(companies)

    assert isinstance(report, SellPriorityReport)
    assert [item.symbol for item in report.items] == ["BBB", "CCC", "AAA"]


def test_sell_priority_flags_action_by_deal_breaker_presence() -> None:
    companies = [
        _ranked("CLEAN", 70.0),
        _ranked("RISKY", 30.0, deal_breakers=["Altman Z baixo"]),
    ]

    report = build_sell_priority(companies)
    by_symbol = {item.symbol: item for item in report.items}

    assert by_symbol["CLEAN"].action == "HOLD"
    assert by_symbol["RISKY"].action == "SELL"
    assert by_symbol["RISKY"].deal_breakers == ("Altman Z baixo",)


def test_sell_priority_assigns_no_target_weight() -> None:
    """This is a classification, not a portfolio construction."""
    report = build_sell_priority([_ranked("AAA", 50.0)])

    assert not hasattr(report.items[0], "target_weight")


def test_sell_priority_filters_to_held_symbols() -> None:
    companies = [_ranked("AAA", 50.0), _ranked("BBB", 90.0)]

    report = build_sell_priority(
        companies,
        held_symbols=frozenset({"AAA"}),
    )

    assert [item.symbol for item in report.items] == ["AAA"]


def test_sell_priority_attaches_current_weight_when_given() -> None:
    report = build_sell_priority(
        [_ranked("AAA", 50.0)],
        weights_by_symbol={"AAA": 0.123},
    )

    assert report.items[0].current_weight == 0.123


def test_sell_priority_missing_score_sorts_last() -> None:
    companies = [
        _ranked("HASSCORE", 10.0),
        {"symbol": "NOSCORE", "deal_breakers": []},
    ]

    report = build_sell_priority(companies)

    assert [item.symbol for item in report.items] == ["HASSCORE", "NOSCORE"]


def test_buy_priority_sorts_by_candidate_rank() -> None:
    companies = [
        _ranked("BBB", 70.0, candidate_rank=2),
        _ranked("AAA", 90.0, candidate_rank=1),
    ]

    report = build_buy_priority(companies)

    assert isinstance(report, BuyPriorityReport)
    assert [item.symbol for item in report.items] == ["AAA", "BBB"]


def test_buy_priority_excludes_companies_that_failed_safeguard() -> None:
    companies = [
        _ranked("PASSED", 80.0, candidate_rank=1, safeguard_passed=True),
        _ranked(
            "BLOCKED",
            30.0,
            deal_breakers=["Piotroski baixo"],
            candidate_rank=None,
            safeguard_passed=False,
        ),
    ]

    report = build_buy_priority(companies)

    assert [item.symbol for item in report.items] == ["PASSED"]
    assert report.total_candidate_count == 1


def test_buy_priority_flags_already_held() -> None:
    companies = [_ranked("AAA", 80.0, candidate_rank=1)]

    report = build_buy_priority(companies, held_symbols=frozenset({"AAA"}))

    assert report.items[0].already_held is True


def test_buy_priority_exclude_held_drops_the_item() -> None:
    companies = [
        _ranked("AAA", 80.0, candidate_rank=1),
        _ranked("BBB", 70.0, candidate_rank=2),
    ]

    report = build_buy_priority(
        companies,
        held_symbols=frozenset({"AAA"}),
        exclude_held=True,
    )

    assert [item.symbol for item in report.items] == ["BBB"]
    # total_candidate_count reflects the full eligible pool, not the filter.
    assert report.total_candidate_count == 2


def test_buy_priority_filters_by_sector() -> None:
    companies = [
        _ranked("TECH", 80.0, candidate_rank=1, sector="Technology"),
        _ranked("ENERGY", 70.0, candidate_rank=2, sector="Energy"),
    ]

    report = build_buy_priority(companies, sector="Energy")

    assert [item.symbol for item in report.items] == ["ENERGY"]


def test_buy_priority_respects_top_n() -> None:
    companies = [
        _ranked("AAA", 90.0, candidate_rank=1),
        _ranked("BBB", 80.0, candidate_rank=2),
        _ranked("CCC", 70.0, candidate_rank=3),
    ]

    report = build_buy_priority(companies, top_n=2)

    assert [item.symbol for item in report.items] == ["AAA", "BBB"]
    assert report.total_candidate_count == 3


def test_buy_priority_assigns_no_target_weight() -> None:
    report = build_buy_priority([_ranked("AAA", 80.0, candidate_rank=1)])

    assert not hasattr(report.items[0], "target_weight")


def test_reports_are_serializable() -> None:
    sell = build_sell_priority([_ranked("AAA", 50.0)])
    buy = build_buy_priority([_ranked("BBB", 80.0, candidate_rank=1)])

    sell_data = sell.to_dict()
    buy_data = buy.to_dict()

    assert sell_data["items"][0]["symbol"] == "AAA"
    assert buy_data["items"][0]["symbol"] == "BBB"
    assert "target_weight" not in sell_data["items"][0]
    assert "target_weight" not in buy_data["items"][0]

"""
Tests for the priority classification layer (sell/buy).

Pure functions over already-computed ranking/rebalance data -- no scoring,
sell-rule evaluation or portfolio-weight construction. Tests lock: the
rebalance as the single source of sell actions, sorting by official priority,
buy-side safeguard filtering, held/exclude-held/sector/top_n filters, and that
neither builder assigns any target weight.
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


def _action(symbol, action="HOLD", priority=50, **kwargs):
    return {
        "symbol": symbol,
        "action": action,
        "current_weight": kwargs.get("current_weight", 0.1),
        "reason": kwargs.get("reason", f"Ação oficial: {action}"),
        "priority": priority,
        "triggered_rules": kwargs.get("triggered_rules", []),
        "missing_data": kwargs.get("missing_data", []),
    }


def test_sell_priority_sorts_by_official_priority_then_score() -> None:
    companies = [
        _ranked("AAA", 40.0),
        _ranked("BBB", 80.0),
        _ranked("CCC", 60.0),
    ]

    report = build_sell_priority(
        companies,
        rebalance_actions=[
            _action("AAA", "HOLD", 50),
            _action("BBB", "HOLD", 50),
            _action("CCC", "TRIM", 10),
        ],
    )

    assert isinstance(report, SellPriorityReport)
    assert [item.symbol for item in report.items] == ["CCC", "BBB", "AAA"]


def test_sell_priority_copies_action_instead_of_deriving_from_deal_breakers() -> None:
    companies = [
        _ranked("CLEAN", 70.0),
        _ranked("RISKY", 30.0, deal_breakers=["Altman Z baixo"]),
    ]

    report = build_sell_priority(
        companies,
        rebalance_actions=[
            _action("CLEAN", "TRIM", 10, triggered_rules=["fundamental_decay"]),
            _action("RISKY", "HOLD", 50),
        ],
    )
    by_symbol = {item.symbol: item for item in report.items}

    assert by_symbol["CLEAN"].action == "TRIM"
    assert by_symbol["CLEAN"].triggered_rules == ("fundamental_decay",)
    assert by_symbol["RISKY"].action == "HOLD"
    assert by_symbol["RISKY"].deal_breakers == ("Altman Z baixo",)


def test_sell_priority_preserves_blocked_engine_review_action() -> None:
    report = build_sell_priority(
        [_ranked("AAA", 50.0)],
        rebalance_actions=[
            _action(
                "AAA",
                "REVISAR",
                20,
                reason="Motor de venda bloqueado: tese ausente.",
                missing_data=["thesis"],
            )
        ],
    )

    assert report.items[0].action == "REVISAR"
    assert report.items[0].reason == "Motor de venda bloqueado: tese ausente."
    assert report.items[0].missing_data == ("thesis",)


def test_sell_priority_does_not_invent_action_without_rebalance() -> None:
    report = build_sell_priority(
        [_ranked("RISKY", 30.0, deal_breakers=["Altman Z baixo"])]
    )

    assert report.items == ()


def test_sell_priority_assigns_no_target_weight() -> None:
    """This is a classification, not a portfolio construction."""
    report = build_sell_priority(
        [_ranked("AAA", 50.0)],
        rebalance_actions=[_action("AAA")],
    )

    assert not hasattr(report.items[0], "target_weight")


def test_sell_priority_filters_to_held_symbols() -> None:
    companies = [_ranked("AAA", 50.0), _ranked("BBB", 90.0)]

    report = build_sell_priority(
        companies,
        rebalance_actions=[_action("AAA"), _action("BBB")],
        held_symbols=frozenset({"AAA"}),
    )

    assert [item.symbol for item in report.items] == ["AAA"]


def test_sell_priority_attaches_current_weight_when_given() -> None:
    report = build_sell_priority(
        [_ranked("AAA", 50.0)],
        rebalance_actions=[_action("AAA", current_weight=0.123)],
        weights_by_symbol={"AAA": 0.123},
    )

    assert report.items[0].current_weight == 0.123


def test_sell_priority_missing_score_sorts_last() -> None:
    companies = [
        _ranked("HASSCORE", 10.0),
        {"symbol": "NOSCORE", "deal_breakers": []},
    ]

    report = build_sell_priority(
        companies,
        rebalance_actions=[_action("NOSCORE"), _action("HASSCORE")],
    )

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
    sell = build_sell_priority(
        [_ranked("AAA", 50.0)],
        rebalance_actions=[_action("AAA", "SELL", 0)],
    )
    buy = build_buy_priority([_ranked("BBB", 80.0, candidate_rank=1)])

    sell_data = sell.to_dict()
    buy_data = buy.to_dict()

    assert sell_data["items"][0]["symbol"] == "AAA"
    assert sell_data["items"][0]["action"] == "SELL"
    assert sell_data["items"][0]["reason"] == "Ação oficial: SELL"
    assert buy_data["items"][0]["symbol"] == "BBB"
    assert "target_weight" not in sell_data["items"][0]
    assert "target_weight" not in buy_data["items"][0]

from __future__ import annotations

from decision.policy import (
    decision_priority,
    evaluate_decision,
    normalize_score,
)


def test_strong_buy_requires_high_opportunity_and_conviction() -> None:
    decision = evaluate_decision(
        opportunity_score=90,
        conviction_score=92,
        risk_penalty=0,
    )

    assert decision == "STRONG_BUY"


def test_high_opportunity_with_medium_conviction_is_buy() -> None:
    decision = evaluate_decision(
        opportunity_score=84,
        conviction_score=75,
        risk_penalty=0,
    )

    assert decision == "BUY"


def test_accumulate_decision() -> None:
    decision = evaluate_decision(
        opportunity_score=69,
        conviction_score=66,
        risk_penalty=5,
    )

    assert decision == "ACCUMULATE"


def test_hold_decision() -> None:
    decision = evaluate_decision(
        opportunity_score=60,
        conviction_score=56,
        risk_penalty=0,
    )

    assert decision == "HOLD"


def test_watch_decision() -> None:
    decision = evaluate_decision(
        opportunity_score=50,
        conviction_score=45,
        risk_penalty=0,
    )

    assert decision == "WATCH"


def test_low_scores_result_in_avoid() -> None:
    decision = evaluate_decision(
        opportunity_score=30,
        conviction_score=35,
        risk_penalty=0,
    )

    assert decision == "AVOID"


def test_deal_breaker_blocks_buy() -> None:
    decision = evaluate_decision(
        opportunity_score=95,
        conviction_score=95,
        risk_penalty=0,
        has_deal_breaker=True,
    )

    assert decision == "WATCH"


def test_high_risk_penalty_results_in_avoid() -> None:
    decision = evaluate_decision(
        opportunity_score=90,
        conviction_score=90,
        risk_penalty=25,
    )

    assert decision == "AVOID"


def test_score_normalization() -> None:
    assert normalize_score(120) == 100
    assert normalize_score(-10) == 0
    assert normalize_score(None) == 50
    assert normalize_score("invalid") == 50


def test_decision_priority() -> None:
    assert decision_priority("STRONG_BUY") < decision_priority("BUY")
    assert decision_priority("BUY") < decision_priority("HOLD")
    assert decision_priority("AVOID") < decision_priority("UNKNOWN")
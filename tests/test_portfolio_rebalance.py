from __future__ import annotations

import pytest

from portfolio.models import Holding, Portfolio
from portfolio.quality import calculate_portfolio_quality
from portfolio.rebalance import (
    RebalanceContext,
    RebalanceError,
    RebalancePolicy,
    build_rebalance_plan,
)
from reports.report_models import CompanyReport


def _report(
    symbol: str,
    decision: str,
    score: float,
) -> CompanyReport:
    return CompanyReport(
        symbol=symbol,
        decision=decision,
        investment_score=score,
        opportunity_score=score,
        conviction_score=score,
        decision_confidence=score,
    )


def test_explicit_targets_generate_buy_and_sell() -> None:
    portfolio = Portfolio(
        name="Explicit",
        cash=0,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=8,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "HOLD",
                    70,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=2,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "BBB",
                    "BUY",
                    90,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.01,
            minimum_trade_value=0,
            allow_sells=True,
            maximum_position_weight=0.80,
            minimum_cash_weight=0.0,
        ),
        context=RebalanceContext(
            target_weights={
                "AAA": 0.50,
                "BBB": 0.50,
            }
        ),
    )

    by_symbol = {
        action.symbol: action
        for action in plan.actions
    }

    assert by_symbol["AAA"].action == "SELL"
    assert by_symbol["BBB"].action == "BUY"
    assert plan.required_cash == 300.0
    assert plan.released_cash == 300.0
    assert plan.net_cash_requirement == 0.0


def test_automatic_targets_favor_high_quality() -> None:
    portfolio = Portfolio(
        name="Automatic",
        cash=100,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=5,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "STRONG_BUY",
                    95,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=5,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "BBB",
                    "AVOID",
                    30,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.0,
            minimum_trade_value=0,
            allow_sells=True,
            maximum_position_weight=0.80,
            minimum_cash_weight=0.10,
        ),
    )

    by_symbol = {
        action.symbol: action
        for action in plan.actions
    }

    assert (
        by_symbol["AAA"].target_weight
        > by_symbol["BBB"].target_weight
    )
    assert by_symbol["AAA"].action == "BUY"
    assert by_symbol["BBB"].action == "SELL"


def test_tolerance_creates_hold_action() -> None:
    portfolio = Portfolio(
        name="Tolerance",
        cash=0,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=5,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "HOLD",
                    70,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=5,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "BBB",
                    "HOLD",
                    70,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.05,
            minimum_trade_value=0,
            allow_sells=True,
            maximum_position_weight=0.50,
            minimum_cash_weight=0.0,
        ),
        context=RebalanceContext(
            target_weights={
                "AAA": 0.50,
                "BBB": 0.50,
            }
        ),
    )

    assert all(
        action.action == "HOLD"
        for action in plan.actions
    )


def test_minimum_trade_value_filters_small_trades() -> None:
    portfolio = Portfolio(
        name="Minimum Trade",
        cash=0,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=51,
                average_price=10,
                current_price=10,
                company_report=_report(
                    "AAA",
                    "HOLD",
                    70,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=49,
                average_price=10,
                current_price=10,
                company_report=_report(
                    "BBB",
                    "HOLD",
                    70,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.0,
            minimum_trade_value=50,
            allow_sells=True,
            maximum_position_weight=0.50,
            minimum_cash_weight=0.0,
        ),
        context=RebalanceContext(
            target_weights={
                "AAA": 0.50,
                "BBB": 0.50,
            }
        ),
    )

    assert all(
        action.action == "HOLD"
        for action in plan.actions
    )


def test_sell_can_be_disabled() -> None:
    portfolio = Portfolio(
        name="No Sells",
        cash=0,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=9,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "AVOID",
                    20,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "BBB",
                    "BUY",
                    90,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.0,
            minimum_trade_value=0,
            allow_sells=False,
            maximum_position_weight=0.80,
            minimum_cash_weight=0.0,
        ),
        context=RebalanceContext(
            target_weights={
                "AAA": 0.50,
                "BBB": 0.50,
            }
        ),
    )

    aaa = next(
        action
        for action in plan.actions
        if action.symbol == "AAA"
    )

    assert aaa.action == "HOLD"
    assert aaa.trade_value == 0.0


def test_cash_shortage_generates_warning() -> None:
    portfolio = Portfolio(
        name="Cash Warning",
        cash=0,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "BUY",
                    90,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(
        portfolio,
        policy=RebalancePolicy(
            tolerance=0.0,
            minimum_trade_value=0,
            allow_sells=False,
            maximum_position_weight=1.0,
            minimum_cash_weight=0.0,
        ),
        context=RebalanceContext(
            target_weights={"AAA": 1.0},
            available_cash=0,
        ),
    )

    assert plan.required_cash == 0.0
    assert not any(
        "Caixa insuficiente" in warning
        for warning in plan.warnings
    )


def test_missing_report_generates_warning() -> None:
    portfolio = Portfolio(
        name="Missing Report",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
            ),
        ),
    )

    plan = build_rebalance_plan(portfolio)

    assert any(
        "AAA" in warning
        for warning in plan.warnings
    )


def test_quality_warnings_are_inherited() -> None:
    portfolio = Portfolio(
        name="Quality Warnings",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
            ),
        ),
    )

    quality = calculate_portfolio_quality(
        portfolio
    )

    plan = build_rebalance_plan(
        portfolio,
        quality=quality,
    )

    assert any(
        "CompanyReport" in warning
        for warning in plan.warnings
    )


def test_zero_value_portfolio_is_rejected() -> None:
    portfolio = Portfolio(
        name="Zero",
        cash=0,
        holdings=(),
    )

    with pytest.raises(RebalanceError):
        build_rebalance_plan(portfolio)


def test_invalid_policy_is_rejected() -> None:
    portfolio = Portfolio(
        name="Invalid Policy",
        cash=1000,
    )

    with pytest.raises(RebalanceError):
        build_rebalance_plan(
            portfolio,
            policy=RebalancePolicy(
                tolerance=1.5,
            ),
        )


def test_plan_is_serializable() -> None:
    portfolio = Portfolio(
        name="Serializable",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    "BUY",
                    90,
                ),
            ),
        ),
    )

    plan = build_rebalance_plan(portfolio)
    data = plan.to_dict()

    assert isinstance(data["actions"], list)
    assert "estimated_turnover" in data
    assert isinstance(data["warnings"], list)

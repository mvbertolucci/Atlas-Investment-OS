from __future__ import annotations

import pytest

from portfolio.models import (
    AllocationSnapshot,
    Holding,
    Portfolio,
    PortfolioRisk,
    RebalanceAction,
    RebalancePlan,
)
from reports.report_models import CompanyReport


def test_holding_calculates_values() -> None:
    holding = Holding(
        symbol=" msft ",
        quantity=10,
        average_price=400,
        current_price=450,
    )

    assert holding.symbol == "MSFT"
    assert holding.invested_value == 4000.0
    assert holding.market_value == 4500.0
    assert holding.unrealized_result == 500.0
    assert holding.unrealized_return == 0.125


def test_holding_requires_positive_quantity() -> None:
    with pytest.raises(ValueError):
        Holding(
            symbol="AAA",
            quantity=0,
            average_price=10,
        )


def test_holding_validates_company_report_symbol() -> None:
    report = CompanyReport(symbol="BBB")

    with pytest.raises(ValueError):
        Holding(
            symbol="AAA",
            quantity=1,
            average_price=10,
            company_report=report,
        )


def test_portfolio_calculates_totals_and_weights() -> None:
    portfolio = Portfolio(
        name="Long Term",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=10,
                average_price=50,
                current_price=100,
            ),
            Holding(
                symbol="BBB",
                quantity=20,
                average_price=20,
                current_price=50,
            ),
        ),
    )

    assert portfolio.total_market_value == 2000.0
    assert portfolio.total_value == 3000.0

    weighted = portfolio.with_calculated_weights()

    assert weighted.holding("AAA") is not None
    assert weighted.holding("AAA").portfolio_weight == pytest.approx(
        1 / 3,
        abs=1e-6,
    )
    assert weighted.holding("BBB").portfolio_weight == pytest.approx(
        1 / 3,
        abs=1e-6,
    )


def test_portfolio_rejects_duplicate_symbols() -> None:
    with pytest.raises(ValueError):
        Portfolio(
            name="Duplicate",
            holdings=(
                Holding(
                    symbol="AAA",
                    quantity=1,
                    average_price=10,
                ),
                Holding(
                    symbol="AAA",
                    quantity=2,
                    average_price=20,
                ),
            ),
        )


def test_portfolio_tracks_missing_data() -> None:
    portfolio = Portfolio(
        name="Missing Data",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=10,
            ),
        ),
    )

    assert portfolio.missing_price_symbols == ("AAA",)
    assert portfolio.missing_report_symbols == ("AAA",)


def test_allocation_snapshot_requires_total_weight() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={
            "AAA": 0.60,
            "BBB": 0.30,
        },
        cash_weight=0.10,
    )

    assert snapshot.cash_weight == 0.10

    with pytest.raises(ValueError):
        AllocationSnapshot(
            by_symbol={
                "AAA": 0.80,
            },
            cash_weight=0.10,
        )


def test_portfolio_risk_normalizes_values() -> None:
    risk = PortfolioRisk(
        concentration_score=120,
        diversification_score=-5,
        largest_position_weight=0.25,
        top_5_weight=0.80,
        warnings="Tecnologia elevada; País concentrado",
    )

    assert risk.concentration_score == 100.0
    assert risk.diversification_score == 0.0
    assert risk.has_warnings is True
    assert risk.warnings == (
        "Tecnologia elevada",
        "País concentrado",
    )


def test_rebalance_action_validates_inputs() -> None:
    action = RebalanceAction(
        symbol="aaa",
        action="buy",
        current_weight=0.10,
        target_weight=0.15,
        target_value=1500,
        trade_value=500,
        reason="Opportunity superior",
        priority=1,
    )

    assert action.symbol == "AAA"
    assert action.action == "BUY"

    with pytest.raises(ValueError):
        RebalanceAction(
            symbol="AAA",
            action="EXECUTE",
            current_weight=0.10,
            target_weight=0.15,
            target_value=1500,
            trade_value=500,
            reason="Inválido",
        )


def test_rebalance_plan_groups_actions() -> None:
    buy = RebalanceAction(
        symbol="AAA",
        action="BUY",
        current_weight=0.10,
        target_weight=0.15,
        target_value=1500,
        trade_value=500,
        reason="Aumentar posição",
    )
    sell = RebalanceAction(
        symbol="BBB",
        action="SELL",
        current_weight=0.25,
        target_weight=0.20,
        target_value=2000,
        trade_value=-500,
        reason="Reduzir concentração",
    )

    plan = RebalancePlan(
        actions=(buy, sell),
        required_cash=500,
        released_cash=500,
        estimated_turnover=0.10,
    )

    assert plan.buy_actions == (buy,)
    assert plan.sell_actions == (sell,)
    assert plan.net_cash_requirement == 0.0


def test_acompanhar_is_valid_and_kept_out_of_review_actions() -> None:
    """ACOMPANHAR is a comparative-only signal (portfolio/sell_rules.py) --
    must be a valid action and must never count as `review_actions`
    (REVISAR, "needs your decision"), only its own `informational_actions`."""
    acompanhar = RebalanceAction(
        symbol="CCC",
        action="acompanhar",
        current_weight=0.10,
        target_weight=0.10,
        target_value=1000,
        trade_value=0,
        reason="Sinal exclusivamente relativo/informativo",
    )
    revisar = RebalanceAction(
        symbol="DDD",
        action="REVISAR",
        current_weight=0.05,
        target_weight=0.05,
        target_value=500,
        trade_value=0,
        reason="Gating de confiança",
    )

    assert acompanhar.action == "ACOMPANHAR"

    plan = RebalancePlan(
        actions=(acompanhar, revisar),
        required_cash=0,
        released_cash=0,
        estimated_turnover=0.0,
    )

    assert plan.informational_actions == (acompanhar,)
    assert plan.review_actions == (revisar,)


def test_models_are_serializable() -> None:
    portfolio = Portfolio(
        name="Serializable",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=2,
                average_price=10,
                current_price=15,
            ),
        ),
    )

    data = portfolio.to_dict()

    assert data["name"] == "Serializable"
    assert data["holdings"][0]["symbol"] == "AAA"
    assert isinstance(data["created_at"], str)

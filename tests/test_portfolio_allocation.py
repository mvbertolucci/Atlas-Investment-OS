from __future__ import annotations

import pytest

from portfolio.allocation import (
    AllocationError,
    build_allocation_snapshot,
    calculate_allocation,
)
from portfolio.metrics import (
    UNKNOWN_COUNTRY,
    UNKNOWN_SECTOR,
)
from portfolio.models import Holding, Portfolio


def _portfolio() -> Portfolio:
    return Portfolio(
        name="Allocation Test",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=10,
                average_price=80,
                current_price=100,
                sector="Technology",
                country="USA",
                currency="USD",
            ),
            Holding(
                symbol="BBB",
                quantity=20,
                average_price=40,
                current_price=50,
                sector="Financials",
                country="Brazil",
                currency="BRL",
            ),
        ),
    )


def test_allocation_by_symbol_includes_cash() -> None:
    result = calculate_allocation(_portfolio())
    snapshot = result.snapshot

    assert snapshot.by_symbol["AAA"] == pytest.approx(
        1 / 3,
        abs=1e-6,
    )
    assert snapshot.by_symbol["BBB"] == pytest.approx(
        1 / 3,
        abs=1e-6,
    )
    assert snapshot.cash_weight == pytest.approx(
        1 / 3,
        abs=1e-6,
    )

    assert (
        sum(snapshot.by_symbol.values())
        + snapshot.cash_weight
    ) == pytest.approx(1.0, abs=1e-6)


def test_allocation_by_sector_country_and_currency() -> None:
    snapshot = build_allocation_snapshot(_portfolio())

    assert snapshot.by_sector == {
        "Financials": pytest.approx(1 / 3, abs=1e-6),
        "Technology": pytest.approx(1 / 3, abs=1e-6),
    }
    assert snapshot.by_country == {
        "Brazil": pytest.approx(1 / 3, abs=1e-6),
        "USA": pytest.approx(1 / 3, abs=1e-6),
    }
    assert snapshot.by_currency == {
        "BRL": pytest.approx(1 / 3, abs=1e-6),
        "USD": pytest.approx(1 / 3, abs=1e-6),
    }


def test_calculated_portfolio_contains_holding_weights() -> None:
    result = calculate_allocation(_portfolio())

    aaa = result.portfolio.holding("AAA")
    bbb = result.portfolio.holding("BBB")

    assert aaa is not None
    assert bbb is not None

    assert aaa.portfolio_weight == pytest.approx(
        1 / 3,
        abs=1e-6,
    )
    assert bbb.portfolio_weight == pytest.approx(
        1 / 3,
        abs=1e-6,
    )


def test_missing_price_generates_warning_and_zero_weight() -> None:
    portfolio = Portfolio(
        name="Missing Price",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=10,
                average_price=10,
                current_price=None,
            ),
        ),
    )

    result = calculate_allocation(portfolio)

    assert result.snapshot.by_symbol == {}
    assert result.snapshot.cash_weight == 1.0
    assert any(
        "AAA" in warning
        for warning in result.warnings
    )


def test_unknown_dimensions_use_explicit_fallbacks() -> None:
    portfolio = Portfolio(
        name="Unknown Dimensions",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=10,
                average_price=10,
                current_price=20,
                sector="",
                country="",
                currency="USD",
            ),
        ),
    )

    snapshot = build_allocation_snapshot(portfolio)

    assert snapshot.by_sector == {
        UNKNOWN_SECTOR: 1.0,
    }
    assert snapshot.by_country == {
        UNKNOWN_COUNTRY: 1.0,
    }


def test_empty_zero_value_portfolio_is_rejected() -> None:
    portfolio = Portfolio(
        name="Empty",
        cash=0,
        holdings=(),
    )

    with pytest.raises(AllocationError):
        calculate_allocation(portfolio)


def test_cash_only_portfolio_is_supported() -> None:
    portfolio = Portfolio(
        name="Cash Only",
        cash=5000,
        holdings=(),
    )

    result = calculate_allocation(portfolio)

    assert result.snapshot.by_symbol == {}
    assert result.snapshot.cash_weight == 1.0
    assert result.portfolio.total_value == 5000.0


def test_allocation_result_is_serializable() -> None:
    result = calculate_allocation(_portfolio())
    data = result.to_dict()

    assert data["portfolio"]["name"] == "Allocation Test"
    assert data["snapshot"]["cash_weight"] == pytest.approx(
        1 / 3,
        abs=1e-6,
    )
    assert isinstance(data["warnings"], list)

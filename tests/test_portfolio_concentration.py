from __future__ import annotations

import pytest

from portfolio.allocation import calculate_allocation
from portfolio.concentration import (
    ConcentrationError,
    ConcentrationPolicy,
    analyze_allocation_concentration,
    analyze_concentration,
)
from portfolio.models import (
    AllocationSnapshot,
    Holding,
    Portfolio,
)


def test_single_position_is_highly_concentrated() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={"AAA": 0.90},
        by_sector={"Technology": 0.90},
        by_country={"USA": 0.90},
        by_currency={"USD": 0.90},
        cash_weight=0.10,
    )

    result = analyze_concentration(snapshot)

    assert result.risk.largest_position_weight == 0.90
    assert result.risk.top_5_weight == 0.90
    assert result.risk.concentration_score == 100.0
    assert result.risk.diversification_score == 0.0
    assert result.has_breaches is True
    assert any(
        "Maior posição" in breach
        for breach in result.breaches
    )


def test_equal_weight_portfolio_has_lower_concentration() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={
            "AAA": 0.20,
            "BBB": 0.20,
            "CCC": 0.20,
            "DDD": 0.20,
        },
        by_sector={
            "Technology": 0.20,
            "Financials": 0.20,
            "Healthcare": 0.20,
            "Industrials": 0.20,
        },
        by_country={
            "USA": 0.40,
            "Brazil": 0.20,
            "Germany": 0.20,
        },
        by_currency={
            "USD": 0.40,
            "BRL": 0.20,
            "EUR": 0.20,
        },
        cash_weight=0.20,
    )

    result = analyze_concentration(snapshot)

    assert result.risk.concentration_score == 25.0
    assert result.risk.diversification_score == 75.0
    assert result.risk.largest_position_weight == 0.20


def test_dimension_limits_generate_breaches() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={
            "AAA": 0.40,
            "BBB": 0.30,
            "CCC": 0.20,
        },
        by_sector={
            "Technology": 0.70,
            "Healthcare": 0.20,
        },
        by_country={
            "USA": 0.90,
        },
        by_currency={
            "USD": 0.90,
        },
        cash_weight=0.10,
    )

    result = analyze_concentration(snapshot)

    assert any(
        "Setor acima do limite" in item
        for item in result.breaches
    )
    assert any(
        "País acima do limite" in item
        for item in result.breaches
    )
    assert any(
        "Moeda acima do limite" in item
        for item in result.breaches
    )


def test_low_cash_generates_breach() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={
            "AAA": 0.50,
            "BBB": 0.49,
        },
        by_sector={
            "Technology": 0.50,
            "Financials": 0.49,
        },
        by_country={
            "USA": 0.50,
            "Brazil": 0.49,
        },
        by_currency={
            "USD": 0.50,
            "BRL": 0.49,
        },
        cash_weight=0.01,
    )

    policy = ConcentrationPolicy(
        max_position_weight=0.60,
        max_top_5_weight=1.0,
        max_sector_weight=0.60,
        max_country_weight=0.60,
        max_currency_weight=0.60,
        minimum_cash_weight=0.05,
    )

    result = analyze_concentration(
        snapshot,
        policy=policy,
    )

    assert any(
        "Caixa abaixo do mínimo" in item
        for item in result.breaches
    )


def test_allocation_warnings_are_inherited() -> None:
    portfolio = Portfolio(
        name="Warnings",
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

    allocation = calculate_allocation(portfolio)

    result = analyze_allocation_concentration(
        allocation
    )

    assert any(
        "AAA" in warning
        for warning in result.risk.warnings
    )


def test_invalid_policy_is_rejected() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={"AAA": 1.0},
        by_sector={"Technology": 1.0},
        by_country={"USA": 1.0},
        by_currency={"USD": 1.0},
        cash_weight=0.0,
    )

    with pytest.raises(ConcentrationError):
        analyze_concentration(
            snapshot,
            policy=ConcentrationPolicy(
                max_position_weight=1.20,
            ),
        )


def test_result_is_serializable() -> None:
    snapshot = AllocationSnapshot(
        by_symbol={
            "AAA": 0.50,
            "BBB": 0.40,
        },
        by_sector={
            "Technology": 0.50,
            "Financials": 0.40,
        },
        by_country={
            "USA": 0.50,
            "Brazil": 0.40,
        },
        by_currency={
            "USD": 0.50,
            "BRL": 0.40,
        },
        cash_weight=0.10,
    )

    result = analyze_concentration(snapshot)
    data = result.to_dict()

    assert "risk" in data
    assert "policy" in data
    assert isinstance(data["breaches"], list)

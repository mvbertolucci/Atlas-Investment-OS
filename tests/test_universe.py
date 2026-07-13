from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from universe import UniversePolicy, evaluate_universe, load_universe_policy


def _policy() -> UniversePolicy:
    return UniversePolicy(
        name="US Test Universe",
        benchmark="S&P 500",
        rebalance_frequency="monthly",
    )


def _eligible_row(symbol: str = "AAA") -> dict:
    return {
        "symbol": symbol,
        "quote_type": "EQUITY",
        "currency": "USD",
        "country": "United States",
        "sector": "Technology",
        "industry": "Software",
        "price": 100.0,
        "market_cap": 10_000_000_000.0,
        "volume": 1_000_000.0,
    }


def test_load_canonical_universe_policy() -> None:
    policy = load_universe_policy(Path("config/universe.yaml"))

    assert policy.to_dict() == {
        "name": "Atlas US Liquid Equities",
        "benchmark": "S&P 500",
        "rebalance_frequency": "monthly",
        "allowed_quote_types": ["EQUITY"],
        "allowed_currencies": ["USD"],
        "allowed_countries": ["United States"],
        "min_market_cap": 1_000_000_000.0,
        "min_price": 5.0,
        "min_volume": 100_000.0,
        "required_fields": [
            "symbol",
            "quote_type",
            "currency",
            "country",
            "sector",
            "price",
            "market_cap",
            "volume",
        ],
    }


def test_policy_rejects_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="min_price"):
        UniversePolicy(
            name="Invalid",
            benchmark="Benchmark",
            rebalance_frequency="monthly",
            min_price=-1,
        )


def test_eligible_member_and_report_summary() -> None:
    report = evaluate_universe(
        pd.DataFrame([_eligible_row()]),
        _policy(),
    )

    assert report.total_count == 1
    assert report.eligible_count == 1
    assert report.excluded_count == 0
    assert report.average_data_coverage_pct == 100.0
    assert report.eligible_by_sector == {"Technology": 1}
    assert report.to_dict()["members"][0]["eligible"] is True


def test_filters_are_additive_and_auditable() -> None:
    row = _eligible_row("LOW")
    row.update(
        {
            "quote_type": "ETF",
            "currency": "BRL",
            "country": "Brazil",
            "price": 2.0,
            "market_cap": 500_000_000.0,
            "volume": 50_000.0,
        }
    )

    member = evaluate_universe(pd.DataFrame([row]), _policy()).members[0]

    assert member.eligible is False
    assert set(member.exclusion_reasons) == {
        "UNSUPPORTED_QUOTE_TYPE",
        "UNSUPPORTED_CURRENCY",
        "UNSUPPORTED_COUNTRY",
        "MARKET_CAP_BELOW_MINIMUM",
        "PRICE_BELOW_MINIMUM",
        "VOLUME_BELOW_MINIMUM",
    }


def test_missing_fields_reduce_coverage_and_report_reason() -> None:
    row = _eligible_row()
    row["sector"] = None

    report = evaluate_universe(pd.DataFrame([row]), _policy())
    member = report.members[0]

    assert member.data_coverage_pct == 87.5
    assert member.exclusion_reasons == (
        "MISSING_REQUIRED_FIELD:sector",
    )
    assert report.exclusions_by_reason == {
        "MISSING_REQUIRED_FIELD:sector": 1,
    }


def test_duplicate_symbols_are_explicitly_excluded() -> None:
    report = evaluate_universe(
        pd.DataFrame([_eligible_row("dup"), _eligible_row("DUP")]),
        _policy(),
    )

    assert report.eligible_count == 0
    assert all(
        member.exclusion_reasons == ("DUPLICATE_SYMBOL",)
        for member in report.members
    )


def test_empty_universe_has_zero_coverage() -> None:
    report = evaluate_universe(pd.DataFrame(), _policy())

    assert report.total_count == 0
    assert report.average_data_coverage_pct == 0.0


def test_evaluate_universe_validates_contract_types() -> None:
    with pytest.raises(TypeError, match="DataFrame"):
        evaluate_universe([], _policy())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="UniversePolicy"):
        evaluate_universe(pd.DataFrame(), {})  # type: ignore[arg-type]

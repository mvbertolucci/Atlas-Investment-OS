"""
Tests for the offline, versioned total-return adapter: converts
already-acquired Yahoo-shaped daily bars (Close/Dividends) into the
AssetPeriodReturn rows backtesting.portfolio_validation.validate_portfolio
already consumes, including PR-032 terminal-event treatment for delistings.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from backtesting.point_in_time import DelistingRecord
from backtesting.portfolio_validation import (
    PortfolioValidationManifest,
    PortfolioValidationPolicy,
    PortfolioRebalance,
    validate_portfolio,
)
from backtesting.total_return_evidence import (
    TotalReturnEvidence,
    extract_total_return_observations,
    load_total_return_evidence,
    write_total_return_evidence,
)


def _history(rows: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """rows: date -> (close, dividend)."""
    index = pd.to_datetime(list(rows))
    return pd.DataFrame(
        {
            "Close": [value[0] for value in rows.values()],
            "Dividends": [value[1] for value in rows.values()],
        },
        index=index,
    )


def _approx(value, expected, tol=1e-9) -> bool:
    return value is not None and not math.isnan(value) and abs(value - expected) < tol


def _delisting(**overrides) -> DelistingRecord:
    base = dict(
        symbol="AAA",
        effective_on="2025-02-01",
        known_at="2025-02-01T00:00:00Z",
        last_trade_on="2025-01-31",
        return_treatment="zero",
        source="test_delisting",
    )
    base.update(overrides)
    return DelistingRecord(**base)


def test_no_dividend_return_matches_close_ratio() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-15": (105.0, 0.0),
            "2025-02-01": (110.0, 0.0),
        }
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-01"]
    )

    assert len(returns) == 1
    row = returns[0]
    assert row.symbol == "AAA"
    assert row.period_start.isoformat() == "2025-01-01"
    assert row.period_end.isoformat() == "2025-02-01"
    assert _approx(row.total_return, 110.0 / 100.0 - 1.0)
    assert row.terminal_treatment is None
    assert row.dividends_included is True


def test_dividend_reinvested_return_compounds_day_over_day() -> None:
    # 100 -> 102 (div 1.0 on 01-10) -> 105
    # multiplier = (102 + 1.0) / 100 * (105 / 102)
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-10": (102.0, 1.0),
            "2025-02-01": (105.0, 0.0),
        }
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-01"]
    )

    expected = (102.0 + 1.0) / 100.0 * (105.0 / 102.0) - 1.0
    assert _approx(returns[0].total_return, expected)


def test_multiple_consecutive_periods_from_more_than_two_boundaries() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-02-01": (110.0, 0.0),
            "2025-03-01": (99.0, 0.0),
        }
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-01", "2025-03-01"]
    )

    assert len(returns) == 2
    assert _approx(returns[0].total_return, 0.10)
    assert _approx(returns[1].total_return, 99.0 / 110.0 - 1.0)


def test_missing_close_on_period_start_omits_the_period_not_invents_one() -> None:
    history = _history({"2025-02-01": (110.0, 0.0)})  # no bar on 2025-01-01

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-01"]
    )

    assert returns == ()


def test_fewer_than_two_boundaries_produces_no_periods() -> None:
    history = _history({"2025-01-01": (100.0, 0.0)})
    assert extract_total_return_observations("AAA", history, ["2025-01-01"]) == ()


def test_zero_delisting_forces_exactly_minus_one() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-31": (5.0, 0.0),
        }
    )
    delisting = _delisting(return_treatment="zero")

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-15"], delistings=[delisting]
    )

    assert len(returns) == 1
    row = returns[0]
    assert row.total_return == -1.0
    assert row.terminal_treatment == "zero"
    assert row.source == "test_delisting"


def test_cash_delisting_uses_cash_proceeds_over_last_traded_close() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-31": (20.0, 0.0),
        }
    )
    delisting = _delisting(return_treatment="cash", cash_proceeds=15.0)

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-15"], delistings=[delisting]
    )

    row = returns[0]
    # multiplier to last trade = 20/100 = 0.2 -> nav 1.2; cash settles at
    # 15/20 of the last traded close -> total_return = 1.2 * (15/20) - 1
    expected = (20.0 / 100.0) * (15.0 / 20.0) - 1.0
    assert _approx(row.total_return, expected)
    assert row.terminal_treatment == "cash"


def test_cash_delisting_without_a_valid_last_trade_close_is_unresolved() -> None:
    """
    Defensive fallback: if the last observed close before delisting is
    somehow non-positive (a degenerate data point, not NaN), cash_proceeds
    cannot be normalized into a return -- report unresolved rather than
    dividing by a bad price.
    """
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-15": (0.0, 0.0),
        }
    )
    delisting = _delisting(
        return_treatment="cash", cash_proceeds=15.0, last_trade_on="2025-01-15"
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-15"], delistings=[delisting]
    )

    row = returns[0]
    assert row.terminal_treatment == "unresolved"
    assert row.total_return is None


def test_successor_delisting_is_reported_unresolved_never_fabricated() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-31": (20.0, 0.0),
        }
    )
    delisting = _delisting(
        return_treatment="successor", successor_symbol="BBB", cash_proceeds=None
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-15"], delistings=[delisting]
    )

    row = returns[0]
    assert row.total_return is None
    assert row.terminal_treatment == "unresolved"


def test_unresolved_delisting_passes_through_unresolved() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-01-31": (20.0, 0.0),
        }
    )
    delisting = _delisting(return_treatment="unresolved")

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-15"], delistings=[delisting]
    )

    row = returns[0]
    assert row.total_return is None
    assert row.terminal_treatment == "unresolved"


def test_delisting_in_a_different_period_does_not_leak_into_this_one() -> None:
    history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-02-01": (110.0, 0.0),
        }
    )
    # last_trade_on is well before this window's periods -- must not match.
    delisting = _delisting(
        last_trade_on="2024-06-01",
        effective_on="2024-06-02",
        known_at="2024-06-02T00:00:00Z",
    )

    returns = extract_total_return_observations(
        "AAA", history, ["2025-01-01", "2025-02-01"], delistings=[delisting]
    )

    assert returns[0].terminal_treatment is None
    assert _approx(returns[0].total_return, 0.10)


def test_same_adapter_works_for_a_benchmark_symbol() -> None:
    spy_history = _history(
        {
            "2025-01-01": (400.0, 0.0),
            "2025-02-01": (420.0, 1.5),
        }
    )
    returns = extract_total_return_observations(
        "SPY", spy_history, ["2025-01-01", "2025-02-01"]
    )
    assert returns[0].symbol == "SPY"
    assert _approx(returns[0].total_return, (420.0 + 1.5) / 400.0 - 1.0)


def test_evidence_roundtrips_and_feeds_the_validation_runner(tmp_path: Path) -> None:
    aaa_history = _history(
        {
            "2025-01-01": (100.0, 0.0),
            "2025-02-01": (110.0, 0.0),
        }
    )
    spy_history = _history(
        {
            "2025-01-01": (400.0, 0.0),
            "2025-02-01": (408.0, 0.0),
        }
    )
    returns = (
        extract_total_return_observations("AAA", aaa_history, ["2025-01-01", "2025-02-01"])
        + extract_total_return_observations("SPY", spy_history, ["2025-01-01", "2025-02-01"])
    )
    evidence = TotalReturnEvidence(retrieved_at="2025-02-02T00:00:00Z", returns=returns)
    path = write_total_return_evidence(evidence, tmp_path / "total_return.json")

    loaded = load_total_return_evidence(path)
    assert loaded == evidence

    report = validate_portfolio(
        rebalances=[PortfolioRebalance(effective_on="2025-01-01", target_weights={"AAA": 1.0})],
        returns=loaded.returns,
        policy=PortfolioValidationPolicy(name="Test", benchmark_symbol="SPY"),
        manifest=PortfolioValidationManifest(
            dataset_name="test",
            dataset_version="1",
            portfolio_source="test",
            return_source="test_total_return_evidence",
            benchmark_source="test",
            period_convention="monthly",
            terminal_event_source="test",
            atlas_code_revision="deadbeef",
        ),
    )

    assert report.summary is not None
    assert len(report.periods) == 1
    assert _approx(report.periods[0].gross_return, 0.10)


def test_load_rejects_tampered_or_malformed_artifact(tmp_path: Path) -> None:
    history = _history({"2025-01-01": (100.0, 0.0), "2025-02-01": (110.0, 0.0)})
    returns = extract_total_return_observations("AAA", history, ["2025-01-01", "2025-02-01"])
    evidence = TotalReturnEvidence(retrieved_at="2025-02-02T00:00:00Z", returns=returns)
    payload = evidence.to_dict()

    tampered = dict(payload)
    tampered["manifest"] = dict(payload["manifest"])
    tampered["manifest"]["calculation_method"] = "something_else"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="calculation_method"):
        load_total_return_evidence(path)

    with pytest.raises(TypeError, match="objeto"):
        TotalReturnEvidence.from_dict([])
    with pytest.raises(TypeError, match="objeto"):
        TotalReturnEvidence.from_dict({"manifest": "not a mapping"})
    with pytest.raises(TypeError, match="lista"):
        TotalReturnEvidence.from_dict(
            {"manifest": {"calculation_method": "day_over_day_dividend_reinvested"}, "returns": "nope"}
        )


def test_evidence_rejects_duplicate_and_premature_retrieval() -> None:
    history = _history({"2025-01-01": (100.0, 0.0), "2025-02-01": (110.0, 0.0)})
    returns = extract_total_return_observations("AAA", history, ["2025-01-01", "2025-02-01"])

    with pytest.raises(ValueError, match="não pode ser vazio"):
        TotalReturnEvidence(retrieved_at="2025-02-02T00:00:00Z", returns=())

    with pytest.raises(ValueError, match="Retorno duplicado"):
        TotalReturnEvidence(
            retrieved_at="2025-02-02T00:00:00Z", returns=returns + returns
        )

    with pytest.raises(ValueError, match="retrieved_at"):
        TotalReturnEvidence(retrieved_at="2025-01-01T00:00:00Z", returns=returns)

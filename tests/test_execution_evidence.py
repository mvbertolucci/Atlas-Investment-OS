from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from backtesting.execution_evidence import (
    HistoricalExecutionEvidence,
    build_execution_evidence,
    extract_observed_us_sessions,
    extract_opening_price_observations,
    load_execution_evidence,
    regular_us_open_at,
    write_execution_evidence,
)
from backtesting.historical_execution import (
    HistoricalExecutionPolicy,
    execute_historical_target,
)
from backtesting.historical_portfolio import HistoricalTargetPortfolio


def _history(
    rows: dict[str, tuple[float | None, float]],
    *,
    splits: dict[str, float] | None = None,
) -> pd.DataFrame:
    index = pd.to_datetime(list(rows))
    return pd.DataFrame(
        {
            "Open": [value[0] for value in rows.values()],
            "Close": [value[1] for value in rows.values()],
            "Stock Splits": [
                (splits or {}).get(day, 0.0) for day in rows
            ],
        },
        index=index,
    )


def _target() -> HistoricalTargetPortfolio:
    return HistoricalTargetPortfolio(
        decision_at=datetime.fromisoformat("2025-01-01T00:00:00+00:00"),
        target_weights={"AAA": 1.0},
        sectors={"AAA": "Technology"},
        incomplete_decisions=(),
        universe_member_count=1,
        universe_eligible_count=1,
        candidate_count=1,
        governed_config_hashes={"model": "a" * 64},
    )


def test_regular_us_open_handles_daylight_saving_time() -> None:
    assert regular_us_open_at("2025-01-02").isoformat() == (
        "2025-01-02T14:30:00+00:00"
    )
    assert regular_us_open_at("2025-07-02").isoformat() == (
        "2025-07-02T13:30:00+00:00"
    )


def test_sessions_are_observed_from_valid_reference_bars_only() -> None:
    history = _history(
        {
            "2025-01-02": (100.0, 101.0),
            "2025-01-03": (None, 102.0),
            "2025-01-06": (103.0, 104.0),
        }
    )

    sessions = extract_observed_us_sessions(history)

    assert [item.session_date.isoformat() for item in sessions] == [
        "2025-01-02",
        "2025-01-06",
    ]
    assert all(item.source == "yahoo_reference_daily_bars" for item in sessions)


def test_historical_open_is_restored_to_as_traded_split_units() -> None:
    history = _history(
        {
            "2020-08-28": (25.0, 25.5),
            "2020-08-31": (26.0, 26.5),
        },
        splits={"2020-08-31": 4.0},
    )

    observations = extract_opening_price_observations("aaa", history)

    assert [item.symbol for item in observations] == ["AAA", "AAA"]
    assert observations[0].price == 100.0
    assert observations[1].price == 26.0
    assert observations[0].observed_at.isoformat() == (
        "2020-08-28T13:30:00+00:00"
    )


def test_build_evidence_uses_reference_sessions_and_filters_other_dates() -> None:
    reference = _history(
        {
            "2025-01-02": (500.0, 501.0),
            "2025-01-03": (502.0, 503.0),
        }
    )
    aaa = _history(
        {
            "2025-01-02": (100.0, 101.0),
            "2025-01-03": (102.0, 103.0),
            "2025-01-04": (104.0, 105.0),
        }
    )

    evidence = build_execution_evidence(
        reference_symbol="spy",
        reference_history=reference,
        symbol_histories={"AAA": aaa},
        retrieved_at="2025-01-05T00:00:00Z",
    )

    assert evidence.reference_symbol == "SPY"
    assert len(evidence.sessions) == 2
    assert len(evidence.prices) == 2
    assert {item.observed_at for item in evidence.prices} == {
        item.opens_at for item in evidence.sessions
    }


def test_versioned_evidence_roundtrips_and_runs_execution(tmp_path: Path) -> None:
    reference = _history({"2025-01-02": (500.0, 501.0)})
    aaa = _history({"2025-01-02": (100.0, 101.0)})
    evidence = build_execution_evidence(
        reference_symbol="SPY",
        reference_history=reference,
        symbol_histories={"AAA": aaa},
        retrieved_at="2025-01-03T00:00:00Z",
    )
    path = write_execution_evidence(evidence, tmp_path / "execution.json")

    loaded = load_execution_evidence(path)
    result = execute_historical_target(
        _target(),
        loaded.sessions,
        loaded.prices,
        HistoricalExecutionPolicy("Test"),
    )

    assert loaded == evidence
    assert result.executed is True
    assert result.rebalance.effective_on.isoformat() == "2025-01-02"
    assert loaded.to_dict()["manifest"]["calendar_method"] == (
        "observed_reference_daily_bars"
    )


def test_manifest_tampering_and_off_session_prices_are_rejected(
    tmp_path: Path,
) -> None:
    reference = _history({"2025-01-02": (500.0, 501.0)})
    aaa = _history({"2025-01-02": (100.0, 101.0)})
    evidence = build_execution_evidence(
        reference_symbol="SPY",
        reference_history=reference,
        symbol_histories={"AAA": aaa},
        retrieved_at="2025-01-03T00:00:00Z",
    )
    payload = evidence.to_dict()
    payload["manifest"]["price_field"] = "Close"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="price_field"):
        load_execution_evidence(path)

    off_session_price = extract_opening_price_observations(
        "AAA", _history({"2025-01-03": (100.0, 101.0)})
    )
    with pytest.raises(ValueError, match="coincidir"):
        HistoricalExecutionEvidence(
            reference_symbol="SPY",
            retrieved_at="2025-01-03T00:00:00Z",
            sessions=evidence.sessions,
            prices=off_session_price,
        )
    with pytest.raises(ValueError, match="retrieved_at"):
        HistoricalExecutionEvidence(
            reference_symbol="SPY",
            retrieved_at="2025-01-01T00:00:00Z",
            sessions=evidence.sessions,
            prices=evidence.prices,
        )


def test_missing_columns_and_wrong_types_are_explicit() -> None:
    empty = pd.DataFrame({"Close": [1.0]})
    assert extract_observed_us_sessions(empty) == ()
    assert extract_opening_price_observations("AAA", empty) == ()
    with pytest.raises(TypeError, match="DataFrame"):
        extract_observed_us_sessions([])  # type: ignore[arg-type]

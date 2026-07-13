from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backtesting.historical_execution import (
    ExecutionPriceObservation,
    HistoricalExecutionPolicy,
    TradingSession,
    execute_historical_target,
    execute_historical_targets,
    load_historical_execution_policy,
)
from backtesting.historical_portfolio import HistoricalTargetPortfolio


def _policy(**overrides) -> HistoricalExecutionPolicy:
    values = {
        "name": "Test next-session execution",
        "execution_timing": "next_session_open",
        "max_wait_calendar_days": 7,
        "base_currency": "USD",
        "require_all_prices": True,
    }
    values.update(overrides)
    return HistoricalExecutionPolicy(**values)


def _target(
    decision_at: str = "2025-02-01T00:00:00Z",
    *,
    constructed: bool = True,
) -> HistoricalTargetPortfolio:
    return HistoricalTargetPortfolio(
        decision_at=datetime.fromisoformat(decision_at.replace("Z", "+00:00")),
        target_weights={"AAA": 0.5, "BBB": 0.5} if constructed else {},
        sectors={"AAA": "Technology", "BBB": "Health"} if constructed else {},
        incomplete_decisions=(),
        universe_member_count=2,
        universe_eligible_count=2,
        candidate_count=2,
        governed_config_hashes={"model": "a" * 64},
        construction_error=None if constructed else "INSUFFICIENT_CANDIDATES",
    )


def _session(
    session_date: str,
    opens_at: str,
) -> TradingSession:
    return TradingSession(
        session_date=session_date,
        opens_at=opens_at,
        venue="XNYS/XNAS",
        source="synthetic-exchange-calendar",
    )


def _price(
    symbol: str,
    observed_at: str,
    *,
    currency: str = "USD",
) -> ExecutionPriceObservation:
    return ExecutionPriceObservation(
        symbol=symbol,
        observed_at=observed_at,
        price=100.0,
        currency=currency,
        source="synthetic-opening-price",
    )


def test_canonical_execution_policy_is_pinned() -> None:
    policy = load_historical_execution_policy("config/historical_execution.yaml")

    assert policy.to_dict() == {
        "name": "Atlas Next-Session Open Execution",
        "execution_timing": "next_session_open",
        "max_wait_calendar_days": 7,
        "base_currency": "USD",
        "require_all_prices": True,
    }


def test_first_session_open_after_decision_is_selected() -> None:
    sessions = (
        _session("2025-01-31", "2025-01-31T14:30:00Z"),
        _session("2025-02-03", "2025-02-03T14:30:00Z"),
        _session("2025-02-04", "2025-02-04T14:30:00Z"),
    )
    prices = (
        _price("AAA", "2025-02-03T14:30:00Z"),
        _price("BBB", "2025-02-03T14:30:00Z"),
    )

    result = execute_historical_target(_target(), sessions, prices, _policy())

    assert result.executed is True
    assert result.session == sessions[1]
    assert result.rebalance is not None
    assert result.rebalance.effective_on.isoformat() == "2025-02-03"
    assert set(result.execution_prices) == {"AAA", "BBB"}
    assert result.to_dict()["executed"] is True
    assert result.to_dict()["policy"] == _policy().to_dict()


def test_missing_price_blocks_whole_execution_without_partial_rebalance() -> None:
    session = _session("2025-02-03", "2025-02-03T14:30:00Z")
    result = execute_historical_target(
        _target(),
        (session,),
        (_price("AAA", "2025-02-03T14:30:00Z"),),
        _policy(),
    )

    assert result.executed is False
    assert result.rebalance is None
    assert set(result.execution_prices) == {"AAA"}
    assert result.failure_reasons == ("MISSING_EXECUTION_PRICE:BBB",)


def test_currency_mismatch_is_visible_and_blocks_execution() -> None:
    session = _session("2025-02-03", "2025-02-03T14:30:00Z")
    result = execute_historical_target(
        _target(),
        (session,),
        (
            _price("AAA", "2025-02-03T14:30:00Z", currency="EUR"),
            _price("BBB", "2025-02-03T14:30:00Z"),
        ),
        _policy(),
    )

    assert result.executed is False
    assert result.failure_reasons == ("EXECUTION_CURRENCY_MISMATCH:AAA",)


def test_no_session_and_excessive_wait_are_explicit() -> None:
    no_session = execute_historical_target(_target(), (), (), _policy())
    assert no_session.failure_reasons == ("NO_SESSION_AFTER_DECISION",)

    late_session = _session("2025-02-10", "2025-02-10T14:30:00Z")
    too_late = execute_historical_target(
        _target(),
        (late_session,),
        (),
        _policy(max_wait_calendar_days=3),
    )
    assert too_late.failure_reasons == ("SESSION_OUTSIDE_MAX_WAIT",)


def test_unconstructed_target_never_becomes_execution() -> None:
    result = execute_historical_target(_target(constructed=False), (), (), _policy())

    assert result.executed is False
    assert result.session is None
    assert result.failure_reasons == (
        "TARGET_NOT_CONSTRUCTED:INSUFFICIENT_CANDIDATES",
    )


def test_execution_sequence_uses_each_targets_next_session() -> None:
    sessions = (
        _session("2025-02-03", "2025-02-03T14:30:00Z"),
        _session("2025-02-04", "2025-02-04T14:30:00Z"),
    )
    prices = tuple(
        _price(symbol, observed_at)
        for observed_at in (
            "2025-02-03T14:30:00Z",
            "2025-02-04T14:30:00Z",
        )
        for symbol in ("AAA", "BBB")
    )
    results = execute_historical_targets(
        (
            _target("2025-02-01T00:00:00Z"),
            _target("2025-02-03T15:00:00Z"),
        ),
        sessions,
        prices,
        _policy(),
    )

    assert [item.rebalance.effective_on.isoformat() for item in results] == [
        "2025-02-03",
        "2025-02-04",
    ]


def test_duplicate_evidence_and_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="fuso horário"):
        TradingSession(
            "2025-02-03",
            datetime(2025, 2, 3, 9, 30),
            "XNYS",
            "fixture",
        )
    session = _session("2025-02-03", "2025-02-03T14:30:00Z")
    with pytest.raises(ValueError, match="Sessão duplicada"):
        execute_historical_target(
            _target(), (session, session), (), _policy()
        )
    price = _price("AAA", "2025-02-03T14:30:00Z")
    with pytest.raises(ValueError, match="Preço de execução duplicado"):
        execute_historical_target(
            _target(), (session,), (price, price), _policy()
        )


def test_policy_rejects_hidden_or_partial_execution_conventions() -> None:
    with pytest.raises(ValueError, match="next_session_open"):
        _policy(execution_timing="same_close")
    with pytest.raises(ValueError, match="require_all_prices"):
        _policy(require_all_prices=False)
    with pytest.raises(ValueError, match="positivo"):
        ExecutionPriceObservation(
            symbol="AAA",
            observed_at=datetime.now(timezone.utc),
            price=0,
            currency="USD",
            source="fixture",
        )

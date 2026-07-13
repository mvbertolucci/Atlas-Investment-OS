"""
Tests for the checkpointed, resumable multi-ticker SEC EDGAR collector.

Mirrors universe/collector.py's own test suite and design: atomic
checkpoint writes, resumability (already-collected symbols are skipped),
explicit failure tracking (never silently dropped), and batch selection.
All offline -- fetchers/CIK maps are injected fakes, no live network call.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.point_in_time import HistoricalObservation
from backtesting.sec_edgar_collector import (
    SecEdgarCollectionState,
    collect_ticker_batch,
    load_collection_state,
    select_next_incomplete_batch,
    select_ticker_batch,
    write_collection_state,
)


def _facts_for(symbol: str) -> dict:
    return {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "val": 100.0,
                                "filed": "2026-02-01",
                                "accn": f"0000000000-26-{symbol}",
                                "form": "10-K",
                            }
                        ]
                    }
                }
            }
        }
    }


CIK_MAP = {"AAA": "0000000001", "BBB": "0000000002", "CCC": "0000000003"}


def test_batch_checkpoint_is_atomic_and_resume_skips_successes(
    tmp_path: Path,
) -> None:
    batch = select_ticker_batch(["AAA", "BBB", "CCC"], batch_size=2, batch_number=1)
    state_path = tmp_path / "collection.json"
    calls: list[str] = []

    def fetcher(cik: str, **_kwargs) -> dict:
        symbol = next(sym for sym, c in CIK_MAP.items() if c == cik)
        calls.append(symbol)
        return _facts_for(symbol)

    first = collect_ticker_batch(
        batch,
        cik_by_ticker=CIK_MAP,
        state_path=state_path,
        user_agent="test-agent (contact: test@example.com)",
        fetcher=fetcher,
        now=lambda: "2026-07-13T12:00:00+00:00",
    )
    second = collect_ticker_batch(
        batch,
        cik_by_ticker=CIK_MAP,
        state_path=state_path,
        user_agent="test-agent (contact: test@example.com)",
        fetcher=fetcher,
        now=lambda: "2026-07-13T12:01:00+00:00",
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert calls == ["AAA", "BBB"]
    assert first.succeeded == 2
    assert first.remaining_total == 1
    assert second.attempted == 0
    assert second.skipped == 2
    assert len(payload["observations_by_symbol"]["AAA"]) == 1
    assert not state_path.with_suffix(".json.tmp").exists()


def test_ticker_without_cik_is_an_explicit_failure_not_a_skip(
    tmp_path: Path,
) -> None:
    batch = select_ticker_batch(["ZZZ"], batch_size=1, batch_number=1)
    state_path = tmp_path / "collection.json"

    result = collect_ticker_batch(
        batch,
        cik_by_ticker={},  # no CIK known for ZZZ
        state_path=state_path,
        user_agent="test-agent",
        fetcher=lambda cik, **_kwargs: _facts_for("ZZZ"),
    )

    state = load_collection_state(state_path)
    assert result.failed == 1
    assert result.attempted == 0  # never reached the fetcher at all
    assert "CIK" in state.failures["ZZZ"]["last_error"]


def test_failures_are_retried_and_replaced_by_later_success(
    tmp_path: Path,
) -> None:
    batch = select_ticker_batch(["AAA"], batch_size=1, batch_number=1)
    state_path = tmp_path / "collection.json"
    attempts = 0

    def failing_fetcher(*_args, **_kwargs) -> dict:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("provider unavailable")

    failed = collect_ticker_batch(
        batch,
        cik_by_ticker=CIK_MAP,
        state_path=state_path,
        user_agent="test-agent",
        fetcher=failing_fetcher,
        retries=2,
    )
    state = load_collection_state(state_path)
    assert attempts == 3
    assert failed.failed == 1
    assert state.failures["AAA"]["attempts"] == 3

    recovered = collect_ticker_batch(
        batch,
        cik_by_ticker=CIK_MAP,
        state_path=state_path,
        user_agent="test-agent",
        fetcher=lambda cik, **_kwargs: _facts_for("AAA"),
    )
    state = load_collection_state(state_path)
    assert recovered.succeeded == 1
    assert "AAA" not in state.failures
    assert "AAA" in state.observations_by_symbol


def test_next_batch_uses_first_incomplete_boundary() -> None:
    batch = select_next_incomplete_batch(
        ["AAA", "BBB", "CCC"],
        batch_size=2,
        completed_symbols={"AAA", "BBB"},
    )
    assert batch is not None
    assert batch.batch_number == 2
    assert batch.tickers == ("CCC",)
    assert select_next_incomplete_batch(
        ["AAA", "BBB", "CCC"],
        batch_size=2,
        completed_symbols={"AAA", "BBB", "CCC"},
    ) is None


def test_state_observations_deserialize_to_real_historical_observations(
    tmp_path: Path,
) -> None:
    batch = select_ticker_batch(["AAA"], batch_size=1, batch_number=1)
    state_path = tmp_path / "collection.json"

    collect_ticker_batch(
        batch,
        cik_by_ticker=CIK_MAP,
        state_path=state_path,
        user_agent="test-agent",
        fetcher=lambda cik, **_kwargs: _facts_for("AAA"),
    )

    state = load_collection_state(state_path)
    observations = state.observations()
    assert len(observations) == 1
    assert isinstance(observations[0], HistoricalObservation)
    assert observations[0].symbol == "AAA"
    assert observations[0].value == 100.0


def test_newer_temporary_checkpoint_is_recovered(tmp_path: Path) -> None:
    state_path = tmp_path / "collection.json"
    base = SecEdgarCollectionState(
        created_at="2026-07-13T12:00:00+00:00",
        updated_at="2026-07-13T12:00:00+00:00",
        observations_by_symbol={"AAA": []},
    )
    write_collection_state(base, state_path)
    newer = SecEdgarCollectionState(
        created_at=base.created_at,
        updated_at="2026-07-13T12:01:00+00:00",
        observations_by_symbol={"AAA": [], "BBB": []},
    )
    state_path.with_suffix(".json.tmp").write_text(
        json.dumps(newer.to_dict()), encoding="utf-8"
    )

    recovered = load_collection_state(state_path)
    assert set(recovered.observations_by_symbol) == {"AAA", "BBB"}


def test_atomic_replace_retries_transient_permission_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "collection.json"
    state = SecEdgarCollectionState(created_at="now", updated_at="now")
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(path: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("OneDrive lock")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    write_collection_state(
        state, state_path, retry_delay=0, sleeper=lambda _delay: None
    )
    assert attempts == 3
    assert state_path.exists()


def test_invalid_retry_and_batch_size_are_rejected(tmp_path: Path) -> None:
    batch = select_ticker_batch(["AAA"], batch_size=1, batch_number=1)
    with pytest.raises(ValueError, match="retries"):
        collect_ticker_batch(
            batch,
            cik_by_ticker=CIK_MAP,
            state_path=tmp_path / "state.json",
            user_agent="test-agent",
            retries=-1,
        )
    with pytest.raises(ValueError, match="batch_size"):
        select_next_incomplete_batch(
            ["AAA"], batch_size=0, completed_symbols=set()
        )


def test_incompatible_checkpoint_schema_is_rejected(tmp_path: Path) -> None:
    state_path = tmp_path / "collection.json"
    state_path.write_text(
        json.dumps({"schema_version": 999}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="incompat"):
        load_collection_state(state_path)

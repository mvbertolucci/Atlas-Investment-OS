from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import universe.collector as collector

from universe.collector import (
    CollectionBatchResult,
    CollectionState,
    collect_constituent_batch,
    load_collection_state,
    select_next_incomplete_batch,
    write_collection_state,
)
from universe.sources import (
    select_constituent_batch,
    write_constituent_snapshot,
)


def _records() -> list[dict[str, str]]:
    return [
        {
            "symbol": symbol,
            "source_symbol": symbol,
            "name": f"Company {symbol}",
            "snapshot_date": "2026-07-13",
        }
        for symbol in ["AAA", "BBB", "CCC"]
    ]


def _observation(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 10.0,
        "history": [],
        "non_finite": float("nan"),
        "_private": "discarded",
    }


def test_batch_checkpoint_is_atomic_and_resume_skips_successes(
    tmp_path: Path,
) -> None:
    records = _records()
    batch = select_constituent_batch(records, batch_size=2, batch_number=1)
    state_path = tmp_path / "collection.json"
    calls: list[str] = []

    def fetcher(symbol: str, _name: str, **_kwargs) -> dict:
        calls.append(symbol)
        return _observation(symbol)

    first = collect_constituent_batch(
        batch,
        snapshot_date="2026-07-13",
        state_path=state_path,
        fetcher=fetcher,
        now=lambda: "2026-07-13T12:00:00+00:00",
    )
    second = collect_constituent_batch(
        batch,
        snapshot_date="2026-07-13",
        state_path=state_path,
        fetcher=fetcher,
        now=lambda: "2026-07-13T12:01:00+00:00",
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert calls == ["AAA", "BBB"]
    assert first.succeeded == 2
    assert first.remaining_total == 1
    assert second.attempted == 0
    assert second.skipped == 2
    assert payload["observations"]["AAA"]["non_finite"] is None
    assert "history" not in payload["observations"]["AAA"]
    assert "_private" not in payload["observations"]["AAA"]
    assert not state_path.with_suffix(".json.tmp").exists()


def test_failures_are_retried_and_replaced_by_later_success(
    tmp_path: Path,
) -> None:
    records = _records()
    batch = select_constituent_batch(records, batch_size=1, batch_number=1)
    state_path = tmp_path / "collection.json"
    attempts = 0

    def failing_fetcher(*_args, **_kwargs) -> dict:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("provider unavailable")

    failed = collect_constituent_batch(
        batch,
        snapshot_date="2026-07-13",
        state_path=state_path,
        fetcher=failing_fetcher,
        retries=2,
    )
    state = load_collection_state(
        state_path,
        snapshot_date="2026-07-13",
        total_constituents=3,
    )
    assert attempts == 3
    assert failed.failed == 1
    assert state.failures["AAA"]["attempts"] == 3

    recovered = collect_constituent_batch(
        batch,
        snapshot_date="2026-07-13",
        state_path=state_path,
        fetcher=lambda symbol, _name, **_kwargs: _observation(symbol),
    )
    state = load_collection_state(
        state_path,
        snapshot_date="2026-07-13",
        total_constituents=3,
    )
    assert recovered.succeeded == 1
    assert "AAA" not in state.failures
    assert "AAA" in state.observations


def test_next_batch_uses_first_incomplete_boundary() -> None:
    records = _records()
    batch = select_next_incomplete_batch(
        records,
        batch_size=2,
        completed_symbols={"AAA", "BBB"},
    )
    assert batch is not None
    assert batch.batch_number == 2
    assert [row["symbol"] for row in batch.frame_rows] == ["CCC"]
    assert select_next_incomplete_batch(
        records,
        batch_size=2,
        completed_symbols={"AAA", "BBB", "CCC"},
    ) is None


def test_next_batch_advances_past_failure_with_exhausted_retry_budget() -> None:
    records = _records()

    batch = select_next_incomplete_batch(
        records,
        batch_size=2,
        completed_symbols={"AAA"},
        failed_attempts={"BBB": 3},
        failure_attempt_budget=3,
    )

    assert batch is not None
    assert batch.batch_number == 2
    assert [row["symbol"] for row in batch.frame_rows] == ["CCC"]

    retryable = select_next_incomplete_batch(
        records,
        batch_size=2,
        completed_symbols={"AAA"},
        failed_attempts={"BBB": 2},
        failure_attempt_budget=3,
    )
    assert retryable is not None
    assert retryable.batch_number == 1


@pytest.mark.parametrize("market_mode", [False, True])
def test_main_without_batch_number_advances_past_permanent_failure(
    tmp_path: Path,
    monkeypatch,
    market_mode: bool,
) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    config.mkdir()
    data.mkdir()
    snapshot_path = config / "research_universe.csv"
    state_path = data / "collection.json"
    write_constituent_snapshot(_records(), snapshot_path)
    (config / "settings.json").write_text(
        json.dumps(
            {
                "research_universe_path": str(snapshot_path),
                "research_universe_batch_size": 2,
                "research_collection_state_path": str(state_path),
                "research_universe_market_path": str(snapshot_path),
                "research_universe_market_batch_size": 2,
                "research_collection_market_state_path": str(state_path),
                "research_collection_retries": 2,
            }
        ),
        encoding="utf-8",
    )
    state = CollectionState(
        snapshot_date="2026-07-13",
        total_constituents=3,
        created_at="2026-07-13T12:00:00+00:00",
        updated_at="2026-07-13T12:01:00+00:00",
        observations={"AAA": _observation("AAA")},
        failures={
            "BBB": {
                "attempts": 3,
                "last_error": "404 permanently delisted",
                "updated_at": "2026-07-13T12:01:00+00:00",
            }
        },
    )
    write_collection_state(state, state_path)
    selected_batches = []

    def fake_collect(batch, **_kwargs):
        selected_batches.append(batch)
        return CollectionBatchResult(
            batch_number=batch.batch_number,
            total_batches=batch.total_batches,
            attempted=1,
            succeeded=1,
            failed=0,
            skipped=0,
            completed_total=2,
            remaining_total=1,
        )

    monkeypatch.setattr(collector, "ROOT", tmp_path)
    monkeypatch.setattr(collector, "collect_constituent_batch", fake_collect)
    argv = ["universe.collector"]
    if market_mode:
        argv.append("--market")
    monkeypatch.setattr(sys, "argv", argv)

    collector.main()

    assert len(selected_batches) == 1
    assert selected_batches[0].batch_number == 2
    assert [
        row["symbol"] for row in selected_batches[0].frame_rows
    ] == ["CCC"]
    persisted = load_collection_state(
        state_path,
        snapshot_date="2026-07-13",
        total_constituents=3,
    )
    assert persisted.failures["BBB"]["last_error"] == (
        "404 permanently delisted"
    )


def test_main_reports_exhausted_failures_when_no_batch_remains(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    config.mkdir()
    data.mkdir()
    snapshot_path = config / "research_universe.csv"
    state_path = data / "collection.json"
    write_constituent_snapshot(_records(), snapshot_path)
    (config / "settings.json").write_text(
        json.dumps(
            {
                "research_universe_path": str(snapshot_path),
                "research_universe_batch_size": 2,
                "research_collection_state_path": str(state_path),
                "research_collection_retries": 2,
            }
        ),
        encoding="utf-8",
    )
    write_collection_state(
        CollectionState(
            snapshot_date="2026-07-13",
            total_constituents=3,
            created_at="2026-07-13T12:00:00+00:00",
            updated_at="2026-07-13T12:01:00+00:00",
            observations={
                "AAA": _observation("AAA"),
                "CCC": _observation("CCC"),
            },
            failures={
                "BBB": {
                    "attempts": 3,
                    "last_error": "404 permanently delisted",
                    "updated_at": "2026-07-13T12:01:00+00:00",
                }
            },
        ),
        state_path,
    )
    monkeypatch.setattr(collector, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["universe.collector"])

    collector.main()

    output = capsys.readouterr().out
    assert "1 falha(s)" in output
    assert "permanecem visíveis no checkpoint" in output
    assert "--batch-number" in output


def test_checkpoint_rejects_different_snapshot(tmp_path: Path) -> None:
    state_path = tmp_path / "collection.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshot_date": "2026-07-12",
                "total_constituents": 3,
                "created_at": "now",
                "updated_at": "now",
                "observations": {},
                "failures": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outro snapshot"):
        load_collection_state(
            state_path,
            snapshot_date="2026-07-13",
            total_constituents=3,
        )


def test_newer_temporary_checkpoint_is_recovered(tmp_path: Path) -> None:
    state_path = tmp_path / "collection.json"
    base = CollectionState(
        snapshot_date="2026-07-13",
        total_constituents=3,
        created_at="2026-07-13T12:00:00+00:00",
        updated_at="2026-07-13T12:00:00+00:00",
        observations={"AAA": _observation("AAA")},
    )
    write_collection_state(base, state_path)
    newer = CollectionState(
        snapshot_date=base.snapshot_date,
        total_constituents=base.total_constituents,
        created_at=base.created_at,
        updated_at="2026-07-13T12:01:00+00:00",
        observations={
            "AAA": _observation("AAA"),
            "BBB": _observation("BBB"),
        },
    )
    state_path.with_suffix(".json.tmp").write_text(
        json.dumps(newer.to_dict()),
        encoding="utf-8",
    )

    recovered = load_collection_state(
        state_path,
        snapshot_date="2026-07-13",
        total_constituents=3,
    )
    assert set(recovered.observations) == {"AAA", "BBB"}


def test_atomic_replace_retries_transient_permission_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "collection.json"
    state = CollectionState(
        snapshot_date="2026-07-13",
        total_constituents=1,
        created_at="now",
        updated_at="now",
    )
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
        state,
        state_path,
        retry_delay=0,
        sleeper=lambda _delay: None,
    )
    assert attempts == 3
    assert state_path.exists()


def test_invalid_retry_and_batch_size_are_rejected(tmp_path: Path) -> None:
    records = _records()
    batch = select_constituent_batch(records, batch_size=1, batch_number=1)
    with pytest.raises(ValueError, match="retries"):
        collect_constituent_batch(
            batch,
            snapshot_date="2026-07-13",
            state_path=tmp_path / "state.json",
            retries=-1,
        )
    with pytest.raises(ValueError, match="batch_size"):
        select_next_incomplete_batch(
            records,
            batch_size=0,
            completed_symbols=set(),
        )

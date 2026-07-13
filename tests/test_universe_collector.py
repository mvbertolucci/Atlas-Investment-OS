from __future__ import annotations

import json
from pathlib import Path

import pytest

from universe.collector import (
    CollectionState,
    collect_constituent_batch,
    load_collection_state,
    select_next_incomplete_batch,
    write_collection_state,
)
from universe.sources import select_constituent_batch


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

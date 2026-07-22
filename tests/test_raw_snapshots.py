from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from storage.raw_snapshots import (
    RAW_SNAPSHOT_PATH_ENV,
    canonical_snapshot_bytes,
    resolve_raw_snapshot_path,
    store_raw_snapshot,
)


def test_raw_snapshot_path_defaults_to_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(RAW_SNAPSHOT_PATH_ENV, raising=False)

    assert resolve_raw_snapshot_path(tmp_path) == tmp_path / "data/raw_snapshots"


def test_raw_snapshot_path_accepts_workstation_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external" / "raw_snapshots"
    monkeypatch.setenv(RAW_SNAPSHOT_PATH_ENV, str(external))

    assert resolve_raw_snapshot_path(tmp_path / "project") == external


def test_raw_snapshot_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    payload = {
        "symbol": "AAA",
        "values": {"price": 10.0, "missing": float("nan")},
        "statement": pd.DataFrame({"2025": [1.0]}, index=["Revenue"]),
    }
    first = store_raw_snapshot(
        payload,
        tmp_path,
        provider="Test Provider",
        symbol="AAA",
        collected_at="2026-07-17T12:00:00+00:00",
    )
    second = store_raw_snapshot(
        payload,
        tmp_path,
        provider="Test Provider",
        symbol="AAA",
        collected_at="2026-07-17T12:01:00+00:00",
    )

    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.read_bytes() == canonical_snapshot_bytes(payload)
    assert json.loads(first.path.read_text(encoding="utf-8"))["values"]["missing"] is None


def test_existing_snapshot_is_never_overwritten(tmp_path: Path) -> None:
    payload = {"symbol": "AAA", "price": 10.0}
    receipt = store_raw_snapshot(
        payload,
        tmp_path,
        provider="Test",
        symbol="AAA",
        collected_at="2026-07-17T12:00:00+00:00",
    )
    receipt.path.write_text("corrupted", encoding="utf-8")

    with pytest.raises(RuntimeError, match="imutável"):
        store_raw_snapshot(
            payload,
            tmp_path,
            provider="Test",
            symbol="AAA",
            collected_at="2026-07-17T12:00:00+00:00",
        )

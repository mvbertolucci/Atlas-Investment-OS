from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from storage.raw_snapshots import canonical_snapshot_bytes, store_raw_snapshot


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

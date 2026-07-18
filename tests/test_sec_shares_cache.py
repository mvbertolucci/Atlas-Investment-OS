from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from providers.sec_shares_cache import SecSharesCache


def test_sec_shares_cache_is_atomic_normalized_and_expires(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 18, tzinfo=timezone.utc)]
    cache = SecSharesCache(
        tmp_path / "sec_shares.json", clock=lambda: current[0]
    )

    cache.put("aapl", {"shares_outstanding": 100.0, "observed_at": "2026-04-17"})

    assert cache.get("AAPL", max_age_days=30) == {
        "shares_outstanding": 100.0,
        "observed_at": "2026-04-17",
    }
    assert cache.path.exists()
    assert not cache.path.with_suffix(".json.tmp").exists()
    current[0] += timedelta(days=31)
    assert cache.get("AAPL", max_age_days=30) is None


def test_sec_shares_cache_recovers_from_malformed_or_incompatible_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sec_shares.json"
    path.write_text("not-json", encoding="utf-8")
    assert SecSharesCache(path).load()["records"] == {}

    path.write_text('{"version": 999}', encoding="utf-8")
    assert SecSharesCache(path).load()["version"] == 1

    path.write_text('{"version": 1, "records": []}', encoding="utf-8")
    assert SecSharesCache(path).load()["records"] == {}

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from providers.massive_cache import MassiveTickerDetailsCache


def test_massive_cache_is_atomic_normalized_and_expires(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 17, tzinfo=timezone.utc)]
    cache = MassiveTickerDetailsCache(
        tmp_path / "massive.json", clock=lambda: current[0]
    )

    cache.put("aapl", {"results": {"market_cap": 100}})

    assert cache.get("AAPL", max_age_days=7) == {
        "results": {"market_cap": 100}
    }
    assert cache.path.exists()
    assert not cache.path.with_suffix(".json.tmp").exists()
    current[0] += timedelta(days=8)
    assert cache.get("AAPL", max_age_days=7) is None


def test_massive_cache_recovers_from_malformed_or_incompatible_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "massive.json"
    path.write_text("not-json", encoding="utf-8")
    assert MassiveTickerDetailsCache(path).load()["records"] == {}

    path.write_text('{"version": 999}', encoding="utf-8")
    assert MassiveTickerDetailsCache(path).load()["version"] == 1

    path.write_text('{"version": 1, "records": []}', encoding="utf-8")
    assert MassiveTickerDetailsCache(path).load()["records"] == {}

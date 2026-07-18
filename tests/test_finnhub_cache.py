from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from providers.finnhub_cache import FinnhubMetricCache


def test_finnhub_cache_is_atomic_normalized_and_expires(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 18, tzinfo=timezone.utc)]
    cache = FinnhubMetricCache(
        tmp_path / "finnhub.json", clock=lambda: current[0]
    )

    cache.put("aapl", {"metric": {"marketCapitalization": 100}})

    assert cache.get("AAPL", max_age_days=2) == {
        "metric": {"marketCapitalization": 100}
    }
    assert cache.path.exists()
    assert not cache.path.with_suffix(".json.tmp").exists()
    current[0] += timedelta(days=3)
    assert cache.get("AAPL", max_age_days=2) is None


def test_finnhub_cache_recovers_from_malformed_or_incompatible_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "finnhub.json"
    path.write_text("not-json", encoding="utf-8")
    assert FinnhubMetricCache(path).load()["records"] == {}

    path.write_text('{"version": 999}', encoding="utf-8")
    assert FinnhubMetricCache(path).load()["version"] == 1

    path.write_text('{"version": 1, "records": []}', encoding="utf-8")
    assert FinnhubMetricCache(path).load()["records"] == {}

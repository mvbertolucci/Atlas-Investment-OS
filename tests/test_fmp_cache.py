from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from providers.fmp_cache import FmpCacheStore, FmpQuotaExceeded


def test_fmp_cache_persists_fresh_values_and_expires_old_ones(
    tmp_path: Path,
) -> None:
    current = [datetime(2026, 7, 17, tzinfo=timezone.utc)]
    cache = FmpCacheStore(tmp_path / "fmp.json", clock=lambda: current[0])

    cache.put("aapl", "market_cap", [{"marketCap": 10}])

    assert cache.get("AAPL", "market_cap", max_age_days=2) == [
        {"marketCap": 10}
    ]
    current[0] += timedelta(days=3)
    assert cache.get("AAPL", "market_cap", max_age_days=2) is None
    assert (tmp_path / "fmp.json").exists()
    assert not (tmp_path / "fmp.json.tmp").exists()


def test_fmp_cache_put_many_writes_one_snapshot(tmp_path: Path) -> None:
    cache = FmpCacheStore(tmp_path / "fmp.json")

    cache.put_many(
        "float",
        {
            "AAA": [{"floatShares": 1}],
            "BBB": [{"floatShares": 2}],
        },
    )

    assert cache.get("AAA", "float", max_age_days=1) == [
        {"floatShares": 1}
    ]
    assert cache.get("BBB", "float", max_age_days=1) == [
        {"floatShares": 2}
    ]


def test_fmp_quota_reserves_calls_and_rolls_over_by_utc_date(
    tmp_path: Path,
) -> None:
    current = [datetime(2026, 7, 17, 23, tzinfo=timezone.utc)]
    cache = FmpCacheStore(tmp_path / "fmp.json", clock=lambda: current[0])

    assert cache.reserve_call(daily_limit=3, reserve_calls=1) == 1
    assert cache.reserve_call(daily_limit=3, reserve_calls=1) == 2
    with pytest.raises(FmpQuotaExceeded, match="reserved") as captured:
        cache.reserve_call(daily_limit=3, reserve_calls=1)
    assert captured.value.retryable is False
    assert cache.remaining(daily_limit=3) == 1
    assert cache.quota_path.exists()

    current[0] += timedelta(days=1)
    assert cache.calls_used_today() == 0
    assert cache.reserve_call(daily_limit=3) == 1


def test_fmp_cache_recovers_from_malformed_or_incompatible_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fmp.json"
    path.write_text("not-json", encoding="utf-8")
    assert FmpCacheStore(path).load()["records"] == {}

    path.write_text('{"version": 999}', encoding="utf-8")
    assert FmpCacheStore(path).load()["version"] == 1


def test_fmp_quota_rejects_invalid_boundaries(tmp_path: Path) -> None:
    cache = FmpCacheStore(tmp_path / "fmp.json")

    with pytest.raises(ValueError, match="daily_limit"):
        cache.reserve_call(daily_limit=0)
    with pytest.raises(ValueError, match="reserve_calls"):
        cache.reserve_call(daily_limit=10, reserve_calls=10)

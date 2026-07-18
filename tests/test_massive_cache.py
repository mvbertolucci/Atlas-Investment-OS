from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from providers.massive_cache import (
    MassiveFloatSnapshotCache,
    MassiveGroupedDailyCache,
    MassiveTickerDetailsCache,
)


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


def test_massive_float_cache_checkpoints_pages_without_credentials(
    tmp_path: Path,
) -> None:
    cache = MassiveFloatSnapshotCache(tmp_path / "float.json")

    cache.append_page(
        [{"ticker": "aapl", "free_float": 10}],
        ("/stocks/vX/float", {"cursor": "next-cursor"}),
    )

    row, complete = cache.lookup("AAPL", max_age_days=7)
    assert row == {"ticker": "aapl", "free_float": 10}
    assert complete is False
    assert cache.next_request(initial_limit=1000) == (
        "/stocks/vX/float",
        {"cursor": "next-cursor"},
    )
    assert "apiKey" not in cache.path.read_text(encoding="utf-8")

    cache.append_page(
        [
            {"ticker": "MSFT", "free_float": 20},
            {"ticker": "BRK.B", "free_float": 30},
        ],
        None,
    )
    assert cache.lookup("BRK-B", max_age_days=7)[0] == {
        "ticker": "BRK.B",
        "free_float": 30,
    }
    assert cache.lookup("UNKNOWN", max_age_days=7) == (None, True)
    assert cache.next_request(initial_limit=1000) is None


def test_massive_grouped_daily_cache_never_expires_a_past_date(
    tmp_path: Path,
) -> None:
    current = [datetime(2026, 7, 17, tzinfo=timezone.utc)]
    cache = MassiveGroupedDailyCache(
        tmp_path / "grouped.json", clock=lambda: current[0]
    )

    cache.put_date("2026-07-16", {"AAPL": {"close": 150.0}})
    current[0] += timedelta(days=400)

    assert cache.get_date("2026-07-16") == {"AAPL": {"close": 150.0}}
    assert cache.lookup("2026-07-16", "aapl") == {"close": 150.0}
    assert cache.get_date("2026-07-15") is None
    assert cache.path.exists()
    assert not cache.path.with_suffix(".json.tmp").exists()


def test_massive_grouped_daily_cache_matches_hyphenated_share_classes(
    tmp_path: Path,
) -> None:
    cache = MassiveGroupedDailyCache(tmp_path / "grouped.json")
    cache.put_date("2026-07-16", {"BRK.B": {"close": 400.0}})

    assert cache.lookup("2026-07-16", "BRK-B") == {"close": 400.0}


def test_massive_grouped_daily_cache_recovers_from_malformed_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "grouped.json"
    path.write_text("not-json", encoding="utf-8")
    assert MassiveGroupedDailyCache(path).load()["dates"] == {}

    path.write_text('{"version": 999}', encoding="utf-8")
    assert MassiveGroupedDailyCache(path).load()["version"] == 1


def test_massive_float_cache_expires_stale_snapshot(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 17, tzinfo=timezone.utc)]
    cache = MassiveFloatSnapshotCache(
        tmp_path / "float.json", clock=lambda: current[0]
    )
    cache.append_page([{"ticker": "AAA", "free_float": 1}], None)
    current[0] += timedelta(days=8)

    state = cache.prepare(max_age_days=7)

    assert state["records"] == {}
    assert state["complete"] is False
    assert cache.next_request(initial_limit=500) == (
        "/stocks/vX/float",
        {"limit": "500", "sort": "ticker.asc"},
    )

    empty = MassiveFloatSnapshotCache(
        tmp_path / "empty-float.json", clock=lambda: current[0]
    )
    empty.append_page([], None)
    current[0] += timedelta(days=8)
    assert empty.prepare(max_age_days=7)["complete"] is False

from __future__ import annotations

import json
from pathlib import Path

import pytest

import providers.market_cap_composition_prefetch as prefetch_module
from providers.massive_cache import MassiveGroupedDailyCache


def _fake_sec_provider(records: dict[str, dict]):
    def provider(symbol: str, *_args, **_kwargs) -> dict:
        normalized = symbol.strip().upper()
        if normalized not in records:
            raise KeyError(normalized)
        return records[normalized]

    return provider


def _sec_record(shares: float, observed_at: str) -> dict:
    return {
        "shares_outstanding": shares,
        "field_evidence": {
            "shares_outstanding": {"observed_at": observed_at}
        },
    }


def test_composition_cli_writes_coverage_and_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T11:00:00",
                "members": [
                    {"symbol": "AAPL", "eligible": True},
                    {"symbol": "MSFT", "eligible": True},
                    {"symbol": "ZZZZ", "eligible": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    grouped_daily_path = tmp_path / "grouped.json"
    grouped_cache = MassiveGroupedDailyCache(grouped_daily_path)
    grouped_cache.put_date(
        "2026-07-16",
        {
            "AAPL": {"trade_date": "2026-07-16", "close": 200.0},
            "MSFT": {"trade_date": "2026-07-16", "close": 400.0},
            "ZZZZ": {"trade_date": "2026-07-16", "close": 10.0},
        },
    )
    coverage_report = tmp_path / "coverage.json"
    snapshot_path = tmp_path / "snapshot.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_grouped_daily_cache_path": str(grouped_daily_path),
                "sec_shares_cache_path": str(tmp_path / "sec_shares.json"),
                "market_cap_composition_report_path": str(coverage_report),
                "market_cap_composition_snapshot_path": str(snapshot_path),
            }
        ),
        encoding="utf-8",
    )
    provider = _fake_sec_provider(
        {
            "AAPL": _sec_record(15_000_000_000.0, "2026-04-17"),
            "MSFT": _sec_record(7_000_000_000.0, "2026-04-20"),
            # ZZZZ absent -> shares_unavailable
        }
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_sec_secondary_provider",
        lambda root, settings_payload: provider,
    )

    exit_code = prefetch_module.main(["--settings", str(settings), "--all"])

    assert exit_code == 0
    report = json.loads(coverage_report.read_text(encoding="utf-8"))
    assert report["trade_date"] == "2026-07-16"
    assert report["composed"] == 2
    assert report["status_counts"]["shares_unavailable"] == 1
    assert report["coverage_pct"] == pytest.approx(66.67)

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["records"]["AAPL"]["market_cap"] == pytest.approx(
        3_000_000_000_000.0
    )
    assert snapshot["records"]["ZZZZ"]["status"] == "shares_unavailable"


def test_composition_cli_requires_grouped_daily_cache(
    tmp_path: Path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps({"generated_at": "2026-07-18", "members": []}),
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_grouped_daily_cache_path": str(
                    tmp_path / "missing_grouped.json"
                ),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="Grouped Daily"):
        prefetch_module.main(["--settings", str(settings)])


def test_composition_cli_requires_sec_provider(
    tmp_path: Path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps({"generated_at": "2026-07-18", "members": []}),
        encoding="utf-8",
    )
    grouped_daily_path = tmp_path / "grouped.json"
    MassiveGroupedDailyCache(grouped_daily_path).put_date("2026-07-16", {})
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_grouped_daily_cache_path": str(grouped_daily_path),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_sec_secondary_provider",
        lambda root, settings_payload: None,
    )

    with pytest.raises(RuntimeError, match="SEC"):
        prefetch_module.main(["--settings", str(settings)])

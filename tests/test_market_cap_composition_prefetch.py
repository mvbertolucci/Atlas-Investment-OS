from __future__ import annotations

import json
from pathlib import Path

import pytest

import providers.market_cap_composition_prefetch as prefetch_module
from providers.market_cap_composition_prefetch import _fetch_massive_shares
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


class _FakeMassiveProvider:
    def __init__(self, results: dict[str, dict | Exception]):
        self._results = results
        self.calls: list[str] = []

    def fetch_ticker_details(self, symbol: str):
        self.calls.append(symbol)
        outcome = self._results.get(symbol)
        if isinstance(outcome, Exception):
            raise outcome
        return {"results": outcome or {}}


def test_fetch_massive_shares_extracts_share_class_shares_outstanding() -> None:
    provider = _FakeMassiveProvider(
        {"ABNB": {"share_class_shares_outstanding": 417930233}}
    )

    shares, observed_at, error = _fetch_massive_shares("ABNB", provider)

    assert shares == pytest.approx(417930233.0)
    assert observed_at is not None
    assert error is None


def test_fetch_massive_shares_returns_none_without_inventing_a_value() -> None:
    provider = _FakeMassiveProvider({"XYZ": {}})

    shares, observed_at, error = _fetch_massive_shares("XYZ", provider)

    assert shares is None
    assert observed_at is None
    assert error is None


def test_fetch_massive_shares_reports_provider_errors() -> None:
    provider = _FakeMassiveProvider({"BAD": RuntimeError("Massive HTTP 404")})

    shares, observed_at, error = _fetch_massive_shares("BAD", provider)

    assert shares is None
    assert error == "RuntimeError"


def test_composition_cli_falls_back_to_massive_when_sec_has_no_shares(
    tmp_path: Path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T11:00:00",
                "members": [{"symbol": "ABNB", "eligible": True}],
            }
        ),
        encoding="utf-8",
    )
    grouped_daily_path = tmp_path / "grouped.json"
    MassiveGroupedDailyCache(grouped_daily_path).put_date(
        "2026-07-16", {"ABNB": {"trade_date": "2026-07-16", "close": 120.0}}
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
    sec_provider = _fake_sec_provider({"ABNB": _sec_record(None, None)})
    massive_provider = _FakeMassiveProvider(
        {"ABNB": {"share_class_shares_outstanding": 400_000_000.0}}
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_sec_secondary_provider",
        lambda root, settings_payload: sec_provider,
    )
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, settings_payload: massive_provider,
    )

    exit_code = prefetch_module.main(["--settings", str(settings), "--all"])

    assert exit_code == 0
    assert massive_provider.calls == ["ABNB"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    record = snapshot["records"]["ABNB"]
    assert record["status"] == "composed"
    assert record["shares_source"] == "Massive Ticker Details"
    assert record["market_cap"] == pytest.approx(120.0 * 400_000_000.0)
    report = json.loads(coverage_report.read_text(encoding="utf-8"))
    assert report["massive_sourced"] == 1
    assert report["massive_fallback_attempted"] == 1


def test_composition_cli_respects_massive_fallback_batch_limit(
    tmp_path: Path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-18T11:00:00",
                "members": [
                    {"symbol": "AAA", "eligible": True},
                    {"symbol": "BBB", "eligible": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    grouped_daily_path = tmp_path / "grouped.json"
    MassiveGroupedDailyCache(grouped_daily_path).put_date(
        "2026-07-16",
        {
            "AAA": {"trade_date": "2026-07-16", "close": 10.0},
            "BBB": {"trade_date": "2026-07-16", "close": 20.0},
        },
    )
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_grouped_daily_cache_path": str(grouped_daily_path),
                "sec_shares_cache_path": str(tmp_path / "sec_shares.json"),
                "market_cap_composition_report_path": str(
                    tmp_path / "coverage.json"
                ),
                "market_cap_composition_snapshot_path": str(
                    tmp_path / "snapshot.json"
                ),
                "market_cap_composition_massive_fallback_batch_size": 1,
            }
        ),
        encoding="utf-8",
    )
    sec_provider = _fake_sec_provider(
        {"AAA": _sec_record(None, None), "BBB": _sec_record(None, None)}
    )
    massive_provider = _FakeMassiveProvider(
        {
            "AAA": {"share_class_shares_outstanding": 1.0},
            "BBB": {"share_class_shares_outstanding": 1.0},
        }
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_sec_secondary_provider",
        lambda root, settings_payload: sec_provider,
    )
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, settings_payload: massive_provider,
    )

    prefetch_module.main(["--settings", str(settings), "--limit", "10"])

    assert len(massive_provider.calls) == 1


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

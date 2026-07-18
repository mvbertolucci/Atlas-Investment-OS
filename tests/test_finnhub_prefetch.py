from __future__ import annotations

import json
from pathlib import Path

import pytest

import providers.finnhub_prefetch as prefetch_module
from providers.finnhub_cache import FinnhubMetricCache


class _FakeProvider:
    def __init__(self, cache: FinnhubMetricCache, available: set[str], cache_days: float = 2.0):
        self.cache = cache
        self.cache_days = cache_days
        self._available = available
        self.calls: list[str] = []

    def __call__(self, symbol: str):
        self.calls.append(symbol)
        market_cap = 1.0 if symbol in self._available else None
        self.cache.put(
            symbol, {"metric": {"marketCapitalization": market_cap}}
        )


def test_finnhub_prefetch_cli_writes_coverage_report_and_skips_cached(
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
    report = tmp_path / "finnhub_coverage.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "finnhub_prefetch_universe_path": str(universe),
                "finnhub_coverage_report_path": str(report),
            }
        ),
        encoding="utf-8",
    )
    cache = FinnhubMetricCache(tmp_path / "finnhub.json")
    cache.put("MSFT", {"metric": {"marketCapitalization": 3.0}})
    provider = _FakeProvider(cache, available={"AAPL", "MSFT"})
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_finnhub_secondary_provider",
        lambda root, payload: provider,
    )

    exit_code = prefetch_module.main(
        ["--settings", str(settings), "--all"]
    )

    assert exit_code == 0
    assert provider.calls == ["AAPL", "ZZZZ"]
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["cached"] == 3
    assert payload["available"] == 2
    assert payload["missing"] == 1
    assert payload["coverage_pct"] == pytest.approx(66.67)
    assert payload["requested_this_run"] == 2


def test_finnhub_prefetch_cli_respects_batch_limit(
    tmp_path: Path, monkeypatch
) -> None:
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nAAA\nBBB\nCCC\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    cache = FinnhubMetricCache(tmp_path / "finnhub.json")
    provider = _FakeProvider(cache, available={"AAA", "BBB", "CCC"})
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_finnhub_secondary_provider",
        lambda root, payload: provider,
    )

    prefetch_module.main(
        ["--settings", str(settings), "--symbols", str(symbols), "--limit", "2"]
    )

    assert provider.calls == ["AAA", "BBB"]


def test_finnhub_prefetch_cli_requires_provider(
    tmp_path: Path, monkeypatch
) -> None:
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nAAPL\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_finnhub_secondary_provider",
        lambda root, payload: None,
    )

    with pytest.raises(RuntimeError, match="desabilitada"):
        prefetch_module.main(
            ["--settings", str(settings), "--symbols", str(symbols)]
        )

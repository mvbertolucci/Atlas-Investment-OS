from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import providers.massive_prefetch as prefetch_module


def test_massive_prefetch_cli_writes_resumable_coverage_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-13T12:00:00",
                "members": [
                    {"symbol": "AAPL", "eligible": True},
                    {"symbol": "MSFT", "eligible": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "coverage.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_coverage_report_path": str(report),
                "massive_prefetch_batch_size": 1,
                "scoring_reference_universe_id": "US_MARKET_ELIGIBLE",
            }
        ),
        encoding="utf-8",
    )
    received = {}
    provider = SimpleNamespace(
        prefetch_ticker_details=lambda symbols, max_symbols: received.update(
            symbols=symbols, max_symbols=max_symbols
        )
        or {"requested": len(symbols), "cached": 1, "available": 1}
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, payload: provider,
    )

    assert prefetch_module.main(["--settings", str(settings)]) == 0

    assert received == {"symbols": ["AAPL", "MSFT"], "max_symbols": 1}
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["reference_date"] == "2026-07-13"
    assert payload["reference_universe"] == "US_MARKET_ELIGIBLE"
    assert json.loads(capsys.readouterr().out)["available"] == 1


def test_massive_prefetch_cli_all_and_missing_provider(
    tmp_path: Path, monkeypatch
) -> None:
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nAAPL\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, payload: None,
    )

    with pytest.raises(RuntimeError, match="desabilitada"):
        prefetch_module.main(
            [
                "--settings",
                str(settings),
                "--symbols",
                str(symbols),
                "--all",
            ]
        )

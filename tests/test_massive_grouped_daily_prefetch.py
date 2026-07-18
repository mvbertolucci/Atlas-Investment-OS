from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import providers.massive_grouped_daily_prefetch as prefetch_module


def test_massive_grouped_daily_cli_writes_coverage_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-17T11:00:00",
                "members": [
                    {"symbol": "AAPL", "eligible": True},
                    {"symbol": "MSFT", "eligible": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "grouped_coverage.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_grouped_daily_coverage_report_path": str(report),
            }
        ),
        encoding="utf-8",
    )
    received = {}
    provider = SimpleNamespace(
        fetch_grouped_daily=lambda trade_date: received.update(
            trade_date=trade_date
        )
        or {"AAPL": {"close": 210.0}}
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, payload: provider,
    )

    exit_code = prefetch_module.main(
        ["--settings", str(settings), "--date", "2026-07-16"]
    )

    assert exit_code == 0
    assert received == {"trade_date": "2026-07-16"}
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload == {
        "generated_at": payload["generated_at"],
        "reference_universe": "US_MARKET_ELIGIBLE",
        "reference_date": "2026-07-17",
        "trade_date": "2026-07-16",
        "market_record_count": 1,
        "requested": 2,
        "matched": 1,
        "missing": 1,
        "coverage_pct": 50.0,
    }
    assert json.loads(capsys.readouterr().out)["matched"] == 1


def test_massive_grouped_daily_cli_defaults_to_yesterday_and_matches_hyphenated(
    tmp_path: Path, monkeypatch
) -> None:
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nBRK-B\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    received = {}
    provider = SimpleNamespace(
        fetch_grouped_daily=lambda trade_date: received.update(
            trade_date=trade_date
        )
        or {"BRK.B": {"close": 400.5}}
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, payload: provider,
    )

    prefetch_module.main(["--settings", str(settings), "--symbols", str(symbols)])

    assert received["trade_date"]
    import datetime as _dt

    _dt.date.fromisoformat(received["trade_date"])


def test_massive_grouped_daily_cli_requires_provider(
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
            ["--settings", str(settings), "--symbols", str(symbols)]
        )

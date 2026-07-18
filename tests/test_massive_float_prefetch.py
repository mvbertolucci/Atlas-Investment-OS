from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import providers.massive_float_prefetch as prefetch_module


def test_massive_float_cli_writes_eligible_coverage_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-17T11:00:00",
                "members": [{"symbol": "AAPL", "eligible": True}],
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "float_coverage.json"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "massive_prefetch_universe_path": str(universe),
                "massive_float_coverage_report_path": str(report),
                "massive_float_max_pages_per_run": 9,
            }
        ),
        encoding="utf-8",
    )
    received = {}
    provider = SimpleNamespace(
        prefetch_float_universe=lambda symbols, max_pages: received.update(
            symbols=symbols, max_pages=max_pages
        )
        or {"requested": 1, "available": 1, "complete": True}
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_massive_secondary_provider",
        lambda root, payload: provider,
    )

    assert prefetch_module.main(["--settings", str(settings)]) == 0

    assert received == {"symbols": ["AAPL"], "max_pages": 9}
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["reference_date"] == "2026-07-17"
    assert json.loads(capsys.readouterr().out)["complete"] is True


def test_massive_float_cli_requires_provider(
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

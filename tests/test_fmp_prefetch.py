from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import providers.fmp_prefetch as prefetch_module
from providers.fmp_prefetch import load_symbols


def test_load_symbols_normalizes_deduplicates_and_accepts_bom(
    tmp_path: Path,
) -> None:
    source = tmp_path / "symbols.csv"
    source.write_text(
        "\ufeffSymbol,name\naapl,Apple\nMSFT,Microsoft\nAAPL,Apple\n",
        encoding="utf-8",
    )

    assert load_symbols(source) == ["AAPL", "MSFT"]


def test_load_symbols_requires_symbol_column(tmp_path: Path) -> None:
    source = tmp_path / "symbols.csv"
    source.write_text("ticker\nAAPL\n", encoding="utf-8")

    with pytest.raises(ValueError, match="coluna symbol"):
        load_symbols(source)


def test_load_symbols_reads_only_eligible_universe_members(
    tmp_path: Path,
) -> None:
    source = tmp_path / "universe.json"
    source.write_text(
        json.dumps(
            {
                "members": [
                    {"symbol": "AAPL", "eligible": True},
                    {"symbol": "MSFT", "eligible": False},
                    {"symbol": "NVDA", "eligible": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_symbols(source) == ["AAPL", "NVDA"]


def test_prefetch_cli_uses_governed_default_snapshot(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    symbols = config / "market.csv"
    symbols.write_text("symbol\nAAPL\nMSFT\n", encoding="utf-8")
    settings = config / "settings.json"
    settings.write_text(
        json.dumps({"fmp_prefetch_universe_path": "config/market.csv"}),
        encoding="utf-8",
    )
    received: list[str] = []
    provider = SimpleNamespace(
        prefetch=lambda values: (
            received.extend(values)
            or {"requested": len(values), "enterprise_missing": 1}
        )
    )
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_fmp_secondary_provider",
        lambda root, payload: provider,
    )

    assert prefetch_module.main([]) == 0
    assert received == ["AAPL", "MSFT"]
    assert json.loads(capsys.readouterr().out)["enterprise_missing"] == 1


def test_prefetch_cli_rejects_missing_provider(
    tmp_path: Path, monkeypatch
) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    symbols = tmp_path / "symbols.csv"
    symbols.write_text("symbol\nAAPL\n", encoding="utf-8")
    monkeypatch.setattr(prefetch_module, "ROOT", tmp_path)
    monkeypatch.setattr(
        prefetch_module,
        "build_fmp_secondary_provider",
        lambda root, payload: None,
    )

    with pytest.raises(RuntimeError, match="desabilitada"):
        prefetch_module.main(
            ["--settings", str(settings), "--symbols", str(symbols)]
        )

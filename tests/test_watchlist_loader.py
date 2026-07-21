from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from watchlist.exceptions import (
    WatchlistFileNotFoundError,
    WatchlistRowError,
    WatchlistSchemaError,
)
from watchlist.loader import entries_from_dataframe, load_watchlist_csv


def _write_csv(path: Path, rows: str) -> Path:
    path.write_text(rows, encoding="utf-8")
    return path


def test_legacy_csv_with_only_symbol_and_name_loads_with_empty_metadata(
    tmp_path: Path,
) -> None:
    """Retrocompatibilidade: o formato atual de config/watchlist.csv."""
    path = _write_csv(
        tmp_path / "watchlist.csv",
        "symbol,name\nADBE,Adobe\nMSFT,Microsoft\n",
    )
    entries = load_watchlist_csv(path)

    assert len(entries) == 2
    adbe = next(entry for entry in entries if entry.symbol == "ADBE")
    assert adbe.name == "Adobe"
    assert adbe.included_at is None
    assert adbe.note == ""
    assert adbe.trigger_condition == ""


def test_csv_without_source_column_defaults_every_entry_to_manual(
    tmp_path: Path,
) -> None:
    """As 41 linhas reais de config/watchlist.csv não têm coluna `source`
    hoje -- todas devem carregar como "manual" sem migração em lote."""
    path = _write_csv(
        tmp_path / "watchlist.csv",
        "symbol,name\nADBE,Adobe\nMSFT,Microsoft\n",
    )
    entries = load_watchlist_csv(path)

    assert all(entry.source == "manual" for entry in entries)


def test_csv_with_source_column_round_trips(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "watchlist.csv",
        "symbol,name,source\nADBE,Adobe,manual\nNEM,Newmont,auto\n",
    )
    entries = load_watchlist_csv(path)

    by_symbol = {entry.symbol: entry for entry in entries}
    assert by_symbol["ADBE"].source == "manual"
    assert by_symbol["NEM"].source == "auto"


def test_invalid_source_value_raises_row_error() -> None:
    frame = pd.DataFrame({"symbol": ["AAA"], "source": ["robot"]})
    with pytest.raises(WatchlistRowError):
        entries_from_dataframe(frame)


def test_full_metadata_round_trips(tmp_path: Path) -> None:
    path = _write_csv(
        tmp_path / "watchlist.csv",
        "symbol,name,included_at,note,trigger_condition\n"
        "NEM,Newmont,2026-07-14,Ouro com margem forte,score > 75\n",
    )
    entries = load_watchlist_csv(path)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.included_at.isoformat() == "2026-07-14"
    assert entry.note == "Ouro com margem forte"
    assert entry.trigger_condition == "score > 75"


def test_missing_file_raises_specific_error(tmp_path: Path) -> None:
    with pytest.raises(WatchlistFileNotFoundError):
        load_watchlist_csv(tmp_path / "nope.csv")


def test_missing_symbol_column_raises_schema_error() -> None:
    frame = pd.DataFrame({"name": ["Adobe"]})
    with pytest.raises(WatchlistSchemaError):
        entries_from_dataframe(frame)


def test_duplicate_symbols_raise_schema_error() -> None:
    frame = pd.DataFrame({"symbol": ["AAA", "AAA"]})
    with pytest.raises(WatchlistSchemaError):
        entries_from_dataframe(frame)


def test_invalid_included_at_raises_row_error() -> None:
    frame = pd.DataFrame(
        {"symbol": ["AAA"], "included_at": ["not-a-date"]}
    )
    with pytest.raises(WatchlistRowError):
        entries_from_dataframe(frame)


def test_portuguese_aliases_are_recognized() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "data_inclusao": ["2026-01-01"],
            "motivo": ["Acompanhar earnings"],
            "condicao": ["earnings_passed"],
        }
    )
    entries = entries_from_dataframe(frame)
    assert entries[0].note == "Acompanhar earnings"
    assert entries[0].trigger_condition == "earnings_passed"


def test_watchlist_report_writer_serializes_contract(tmp_path: Path) -> None:
    from watchlist.models import WatchlistReport, WatchlistTriggerResult
    from watchlist.report import write_watchlist_report

    report = WatchlistReport(
        results=(
            WatchlistTriggerResult(
                symbol="AAA",
                trigger_condition="score > 75",
                status="triggered",
                message="x",
                cleanup_suggested=False,
            ),
            WatchlistTriggerResult(
                symbol="BBB",
                trigger_condition="",
                status="no_condition",
                message="x",
                age_days=200,
                cleanup_suggested=True,
            ),
        )
    )
    output = write_watchlist_report(report, tmp_path / "watchlist_report.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["triggered_count"] == 1
    assert payload["cleanup_candidate_count"] == 1
    assert len(payload["results"]) == 2

    with pytest.raises(TypeError):
        write_watchlist_report(object(), tmp_path / "bad.json")

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import watchlist.apply_candidates_workbook as apply_module
from watchlist.apply_candidates_workbook import apply_workbook, main
from watchlist.loader import load_watchlist_csv


def _watchlist(path: Path, rows: str = "symbol,name\nADBE,Adobe\n") -> Path:
    path.write_text(rows, encoding="utf-8")
    return path


def test_apply_workbook_promotes_only_marked_rows(tmp_path: Path) -> None:
    watchlist_path = _watchlist(tmp_path / "watchlist.csv")
    frame = pd.DataFrame(
        [
            {
                "Incluir": "x",
                "Symbol": "NEM",
                "Name": "Newmont",
                "Nota": "",
                "Motivo Sugerido": "confidence >= 70",
                "Gatilho Sugerido": "confidence >= 70",
            },
            {
                "Incluir": "",  # not marked -- must be skipped
                "Symbol": "IGNORE",
                "Name": "",
                "Nota": "",
                "Motivo Sugerido": "",
                "Gatilho Sugerido": "",
            },
        ]
    )

    summary = apply_workbook(
        frame, watchlist_path=watchlist_path, today=date(2026, 7, 18)
    )

    assert summary == {"added": ["NEM"], "skipped": [], "failed": []}
    entries = {entry.symbol: entry for entry in load_watchlist_csv(watchlist_path)}
    assert set(entries) == {"ADBE", "NEM"}
    assert entries["NEM"].name == "Newmont"
    assert entries["NEM"].note == "confidence >= 70"
    assert entries["NEM"].trigger_condition == "confidence >= 70"


def test_apply_workbook_uses_manual_note_when_present(tmp_path: Path) -> None:
    watchlist_path = _watchlist(tmp_path / "watchlist.csv")
    frame = pd.DataFrame(
        [
            {
                "Incluir": "sim",
                "Symbol": "NEM",
                "Name": "",
                "Nota": "recomendação de um amigo",
                "Motivo Sugerido": "confidence >= 70",
                "Gatilho Sugerido": "",
            }
        ]
    )

    apply_workbook(frame, watchlist_path=watchlist_path, today=date(2026, 7, 18))

    entries = {entry.symbol: entry for entry in load_watchlist_csv(watchlist_path)}
    assert entries["NEM"].note == "recomendação de um amigo"


def test_apply_workbook_falls_back_to_default_note_when_both_empty(
    tmp_path: Path,
) -> None:
    watchlist_path = _watchlist(tmp_path / "watchlist.csv")
    frame = pd.DataFrame(
        [{"Incluir": "1", "Symbol": "ZZZZ", "Name": "", "Nota": "", "Motivo Sugerido": ""}]
    )

    apply_workbook(frame, watchlist_path=watchlist_path, today=date(2026, 7, 18))

    entries = {entry.symbol: entry for entry in load_watchlist_csv(watchlist_path)}
    assert entries["ZZZZ"].note == "adicionado manualmente via planilha"


def test_apply_workbook_skips_already_watched_and_blank_symbol_rows(
    tmp_path: Path,
) -> None:
    watchlist_path = _watchlist(tmp_path / "watchlist.csv")
    frame = pd.DataFrame(
        [
            {"Incluir": "x", "Symbol": "ADBE", "Name": "", "Nota": "", "Motivo Sugerido": ""},
            {"Incluir": "x", "Symbol": "", "Name": "", "Nota": "", "Motivo Sugerido": ""},
        ]
    )

    summary = apply_workbook(frame, watchlist_path=watchlist_path)

    assert summary == {"added": [], "skipped": ["ADBE"], "failed": []}


def test_apply_workbook_handles_empty_frame(tmp_path: Path) -> None:
    watchlist_path = _watchlist(tmp_path / "watchlist.csv")
    frame = pd.DataFrame(columns=["Incluir", "Symbol", "Name", "Nota", "Motivo Sugerido"])

    summary = apply_workbook(frame, watchlist_path=watchlist_path)

    assert summary == {"added": [], "skipped": [], "failed": []}


def test_main_reads_workbook_and_reports_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(apply_module, "ROOT", tmp_path)
    watchlist = tmp_path / "config" / "watchlist.csv"
    watchlist.parent.mkdir(parents=True)
    _watchlist(watchlist)
    settings = tmp_path / "settings.json"
    settings.write_text(
        '{"watchlist_path": "config/watchlist.csv"}', encoding="utf-8"
    )
    workbook_path = tmp_path / "candidates.xlsx"
    frame = pd.DataFrame(
        [{"Incluir": "x", "Symbol": "NEM", "Name": "Newmont", "Nota": "boa"}]
    )
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Candidatos", index=False)

    exit_code = main(["--settings", str(settings), str(workbook_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Adicionados (1): ['NEM']" in out
    entries = {entry.symbol for entry in load_watchlist_csv(watchlist)}
    assert entries == {"ADBE", "NEM"}


def test_main_requires_existing_workbook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(apply_module, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="não encontrada"):
        main(["--settings", str(tmp_path / "missing_settings.json"), "missing.xlsx"])

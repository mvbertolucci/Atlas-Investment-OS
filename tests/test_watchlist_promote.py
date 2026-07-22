from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from watchlist.loader import load_watchlist_csv
from watchlist.promote import SymbolAlreadyInWatchlistError, promote_to_watchlist


def _write_watchlist(path: Path, rows: str) -> Path:
    path.write_text(rows, encoding="utf-8")
    return path


def _write_candidates_csv(path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["candidate_rank", "symbol", "name", "sector"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "candidate_rank": 1,
                "symbol": "NEM",
                "name": "Newmont Corporation",
                "sector": "Basic Materials",
            }
        )
    return path


def test_promotion_appends_row_with_included_at_and_note(
    tmp_path: Path,
) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    source_path = _write_candidates_csv(tmp_path / "research_candidates.csv")

    result = promote_to_watchlist(
        "NEM",
        "Ouro com margem forte",
        source_path=source_path,
        watchlist_path=watchlist_path,
        today=date(2026, 7, 14),
    )

    assert result.symbol == "NEM"
    assert result.name == "Newmont Corporation"
    assert result.included_at == "2026-07-14"

    entries = load_watchlist_csv(watchlist_path)
    symbols = {entry.symbol for entry in entries}
    assert symbols == {"ADBE", "NEM"}
    nem = next(entry for entry in entries if entry.symbol == "NEM")
    assert nem.note == "Ouro com margem forte"
    assert nem.included_at.isoformat() == "2026-07-14"

    # Linha pré-existente preservada intacta.
    adbe = next(entry for entry in entries if entry.symbol == "ADBE")
    assert adbe.name == "Adobe"


def test_duplicate_symbol_is_rejected(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    with pytest.raises(SymbolAlreadyInWatchlistError):
        promote_to_watchlist(
            "adbe",  # case-insensitive
            "motivo qualquer",
            watchlist_path=watchlist_path,
        )


def test_promotion_never_touches_portfolio_csv(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    portfolio_path = tmp_path / "portfolio.csv"
    portfolio_path.write_text(
        "symbol,quantity,average_price\nMSFT,10,400\n", encoding="utf-8"
    )

    promote_to_watchlist(
        "NEM",
        "motivo",
        watchlist_path=watchlist_path,
        today=date(2026, 7, 14),
    )

    assert portfolio_path.read_text(encoding="utf-8") == (
        "symbol,quantity,average_price\nMSFT,10,400\n"
    )


def test_symbol_not_found_in_source_still_promotes_with_empty_name(
    tmp_path: Path,
) -> None:
    """
    Ausência de dado no arquivo de origem não bloqueia a promoção -- só
    resulta em nome vazio (a promoção é assistida, não estritamente
    condicionada a um relatório existir).
    """
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    result = promote_to_watchlist(
        "ZZZZ",
        "motivo",
        source_path=tmp_path / "does_not_exist.json",
        watchlist_path=watchlist_path,
        today=date(2026, 7, 14),
    )
    assert result.name == ""


def test_name_override_skips_source_lookup(tmp_path: Path) -> None:
    """watchlist.apply_candidates_workbook already has the resolved name
    from the exported workbook and must not depend on source_path still
    matching by the time the workbook is applied."""
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    result = promote_to_watchlist(
        "NEM",
        "motivo",
        source_path=tmp_path / "does_not_exist.csv",
        watchlist_path=watchlist_path,
        name="Newmont Corporation",
        today=date(2026, 7, 14),
    )

    assert result.name == "Newmont Corporation"


def test_trigger_condition_is_persisted_when_provided(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    promote_to_watchlist(
        "NEM",
        "motivo",
        watchlist_path=watchlist_path,
        trigger_condition="confidence >= 70",
        today=date(2026, 7, 14),
    )

    entries = load_watchlist_csv(watchlist_path)
    nem = next(entry for entry in entries if entry.symbol == "NEM")
    assert nem.trigger_condition == "confidence >= 70"


def test_requires_non_empty_symbol_and_reason(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    with pytest.raises(ValueError):
        promote_to_watchlist("", "motivo", watchlist_path=watchlist_path)
    with pytest.raises(ValueError):
        promote_to_watchlist("NEM", "  ", watchlist_path=watchlist_path)


def test_source_defaults_to_manual_and_persists(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    result = promote_to_watchlist(
        "NEM", "motivo", watchlist_path=watchlist_path, today=date(2026, 7, 14)
    )
    assert result.source == "manual"

    entries = load_watchlist_csv(watchlist_path)
    nem = next(entry for entry in entries if entry.symbol == "NEM")
    assert nem.source == "manual"


def test_source_auto_persists_for_auto_curation_flow(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    result = promote_to_watchlist(
        "NEM",
        "Auto-inclusão: top 30 por Investment Score",
        watchlist_path=watchlist_path,
        source="auto",
        today=date(2026, 7, 14),
    )
    assert result.source == "auto"

    entries = load_watchlist_csv(watchlist_path)
    nem = next(entry for entry in entries if entry.symbol == "NEM")
    assert nem.source == "auto"


def test_promotion_persists_active_queue_metadata(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    promote_to_watchlist(
        "KGC",
        "ADR qualificado",
        watchlist_path=watchlist_path,
        trigger_condition="score > 80",
        source="auto",
        analytical_origin="adr",
        entry_rank=1,
        entry_score=72.2,
        review_sla_days=30,
        discard_condition="investment_score < 40",
        today=date(2026, 7, 22),
    )

    kgc = next(item for item in load_watchlist_csv(watchlist_path) if item.symbol == "KGC")
    assert kgc.lifecycle_state == "analyzing"
    assert kgc.analytical_origin == "adr"
    assert kgc.entry_rank == 1
    assert kgc.entry_score == 72.2
    assert kgc.review_due_at == date(2026, 8, 21)
    assert kgc.promotion_condition == "score > 80"
    assert kgc.discard_condition == "investment_score < 40"


def test_legacy_rows_without_source_column_backfill_to_manual(
    tmp_path: Path,
) -> None:
    """Toda linha pré-existente foi curada à mão, por definição -- o fluxo
    automático só passou a existir a partir desta mudança. A primeira
    escrita que toca o arquivo deixa isso explícito no CSV."""
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\nMSFT,Microsoft\n"
    )

    promote_to_watchlist(
        "NEM", "motivo", watchlist_path=watchlist_path, today=date(2026, 7, 14)
    )

    entries = load_watchlist_csv(watchlist_path)
    by_symbol = {entry.symbol: entry for entry in entries}
    assert by_symbol["ADBE"].source == "manual"
    assert by_symbol["MSFT"].source == "manual"
    assert by_symbol["NEM"].source == "manual"


def test_invalid_source_is_rejected(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    with pytest.raises(ValueError):
        promote_to_watchlist(
            "NEM", "motivo", watchlist_path=watchlist_path, source="robot"
        )


def test_promote_survives_transient_onedrive_lock(tmp_path: Path) -> None:
    """Prova que promote_to_watchlist está de fato roteado pelo writer
    compartilhado (ADR-032's replace_with_retry), não um open("w") cru."""
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    original_replace = Path.replace
    attempts = 0

    def flaky_replace(self: Path, destination: Path):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("OneDrive lock")
        return original_replace(self, destination)

    Path.replace = flaky_replace  # type: ignore[assignment]
    try:
        promote_to_watchlist(
            "NEM",
            "motivo",
            watchlist_path=watchlist_path,
            today=date(2026, 7, 14),
        )
    finally:
        Path.replace = original_replace  # type: ignore[assignment]

    assert attempts == 3
    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"ADBE", "NEM"}

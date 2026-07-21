from __future__ import annotations

from pathlib import Path

import pytest

from watchlist.loader import load_watchlist_csv
from watchlist.promote import SymbolNotInWatchlistError, remove_from_watchlist


def _write_watchlist(path: Path, rows: str) -> Path:
    path.write_text(rows, encoding="utf-8")
    return path


def test_remove_deletes_matching_row_and_preserves_others(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv",
        "symbol,name,source\nADBE,Adobe,manual\nNEM,Newmont,auto\n",
    )

    result = remove_from_watchlist(
        "NEM", "Investment Score 32.1 < 40.0", watchlist_path=watchlist_path
    )

    assert result.symbol == "NEM"
    assert result.reason == "Investment Score 32.1 < 40.0"

    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"ADBE"}


def test_remove_is_case_insensitive(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\nNEM,Newmont\n"
    )

    remove_from_watchlist("adbe", "motivo", watchlist_path=watchlist_path)

    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"NEM"}


def test_remove_absent_symbol_is_rejected(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )

    with pytest.raises(SymbolNotInWatchlistError):
        remove_from_watchlist("ZZZZ", "motivo", watchlist_path=watchlist_path)

    # Nada foi tocado -- arquivo continua intacto.
    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"ADBE"}


def test_remove_never_touches_portfolio_csv(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    portfolio_path = tmp_path / "portfolio.csv"
    portfolio_path.write_text(
        "symbol,quantity,average_price\nMSFT,10,400\n", encoding="utf-8"
    )

    remove_from_watchlist("ADBE", "motivo", watchlist_path=watchlist_path)

    assert portfolio_path.read_text(encoding="utf-8") == (
        "symbol,quantity,average_price\nMSFT,10,400\n"
    )


def test_requires_non_empty_symbol_and_reason(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\n"
    )
    with pytest.raises(ValueError):
        remove_from_watchlist("", "motivo", watchlist_path=watchlist_path)
    with pytest.raises(ValueError):
        remove_from_watchlist("ADBE", "  ", watchlist_path=watchlist_path)


def test_remove_survives_transient_onedrive_lock(tmp_path: Path) -> None:
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.csv", "symbol,name\nADBE,Adobe\nNEM,Newmont\n"
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
        remove_from_watchlist("NEM", "motivo", watchlist_path=watchlist_path)
    finally:
        Path.replace = original_replace  # type: ignore[assignment]

    assert attempts == 3
    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"ADBE"}

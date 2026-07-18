from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import watchlist.candidates_workbook as workbook_module
from watchlist.candidates_workbook import (
    MANUAL_ENTRY_ROWS,
    _held_symbols,
    _watchlist_symbols,
    build_candidates_frame,
    main,
    write_workbook,
)


def _broad_report(path: Path, companies: list[dict]) -> Path:
    path.write_text(json.dumps({"companies": companies}), encoding="utf-8")
    return path


def test_build_candidates_frame_lists_all_candidates_without_diversification_cap(
    tmp_path: Path,
) -> None:
    broad = _broad_report(
        tmp_path / "market.json",
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "candidate_rank": 1,
                "safeguard_passed": True,
                "investment_score": 82.0,
                "confidence_score": 75.0,
            },
            {
                "symbol": "BBB",
                "name": "Beta",
                "sector": "Tech",
                "candidate_rank": 2,
                "safeguard_passed": True,
                "investment_score": 80.0,
                "confidence_score": 74.0,
            },
        ],
    )

    frame = build_candidates_frame(
        broad_market_path=broad,
        adr_path=None,
        watchlist_symbols=set(),
        held_symbols=set(),
    )

    candidates = frame[frame["Symbol"] != ""]
    # Two candidates from the SAME sector: the report's own max_per_sector=2
    # would already keep both here, but this proves no tighter cap applies.
    assert set(candidates["Symbol"]) == {"AAA", "BBB"}
    assert candidates.iloc[0]["Incluir"] == ""
    assert candidates.iloc[0]["Nota"] == ""
    assert len(frame) == len(candidates) + MANUAL_ENTRY_ROWS


def test_build_candidates_frame_excludes_watched_and_held_symbols(
    tmp_path: Path,
) -> None:
    broad = _broad_report(
        tmp_path / "market.json",
        [
            {
                "symbol": "AAA",
                "sector": "Tech",
                "candidate_rank": 1,
                "safeguard_passed": True,
            },
            {
                "symbol": "BBB",
                "sector": "Tech",
                "candidate_rank": 2,
                "safeguard_passed": True,
            },
        ],
    )

    frame = build_candidates_frame(
        broad_market_path=broad,
        adr_path=None,
        watchlist_symbols={"AAA"},
        held_symbols={"BBB"},
    )

    candidates = frame[frame["Symbol"] != ""]
    assert candidates.empty


def test_watchlist_and_held_symbol_helpers_handle_missing_files(
    tmp_path: Path,
) -> None:
    assert _watchlist_symbols(tmp_path / "missing_watchlist.csv") == set()
    assert _held_symbols(tmp_path / "missing_portfolio.csv") == set()


def test_watchlist_symbols_returns_empty_for_header_only_csv(
    tmp_path: Path,
) -> None:
    """A fresh install's watchlist.csv can be header-only (zero rows);
    load_watchlist_csv itself treats that as an error, but exporting the
    candidates workbook must not crash on it -- it just means nothing is
    excluded as already-watched yet."""
    path = tmp_path / "watchlist.csv"
    path.write_text("symbol,name\n", encoding="utf-8")

    assert _watchlist_symbols(path) == set()


def test_watchlist_symbols_reads_real_csv(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.csv"
    path.write_text("symbol,name\nADBE,Adobe\n", encoding="utf-8")

    assert _watchlist_symbols(path) == {"ADBE"}


def test_held_symbols_reads_real_portfolio_csv(tmp_path: Path) -> None:
    path = tmp_path / "portfolio.csv"
    path.write_text(
        "symbol,quantity,average_price\nMSFT,10,400\n", encoding="utf-8"
    )

    assert _held_symbols(path) == {"MSFT"}


def test_held_symbols_returns_empty_on_invalid_portfolio_csv(
    tmp_path: Path,
) -> None:
    path = tmp_path / "portfolio.csv"
    path.write_text("not,a,valid,portfolio,schema\n", encoding="utf-8")

    assert _held_symbols(path) == set()


def test_main_writes_workbook_from_settings_and_prints_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(workbook_module, "ROOT", tmp_path)
    (tmp_path / "output" / "dados").mkdir(parents=True)
    broad = tmp_path / "output" / "dados" / "research_ranking_report_market.json"
    _broad_report(
        broad,
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "candidate_rank": 1,
                "safeguard_passed": True,
                "investment_score": 82.0,
                "confidence_score": 75.0,
            }
        ],
    )
    watchlist = tmp_path / "config" / "watchlist.csv"
    watchlist.parent.mkdir(parents=True)
    watchlist.write_text("symbol,name\n", encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"watchlist_path": "config/watchlist.csv"}), encoding="utf-8"
    )
    output_path = tmp_path / "candidates.xlsx"

    exit_code = main(
        ["--settings", str(settings), "--output", str(output_path)]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert "1 candidatos" in capsys.readouterr().out
    reloaded = pd.read_excel(output_path, engine="openpyxl")
    assert "AAA" in set(reloaded["Symbol"].dropna())


def test_write_workbook_round_trips_through_pandas(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [{"Incluir": "", "Symbol": "AAA", "Name": "Alpha"}]
    )
    output_path = tmp_path / "nested" / "candidates.xlsx"

    write_workbook(frame, output_path)

    assert output_path.exists()
    reloaded = pd.read_excel(output_path, engine="openpyxl")
    assert reloaded.iloc[0]["Symbol"] == "AAA"

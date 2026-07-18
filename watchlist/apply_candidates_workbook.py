from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from watchlist.exceptions import WatchlistError
from watchlist.promote import (
    DEFAULT_WATCHLIST_PATH,
    SymbolAlreadyInWatchlistError,
    promote_to_watchlist,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FALLBACK_NOTE = "adicionado manualmente via planilha"


def apply_workbook(
    frame: pd.DataFrame,
    *,
    watchlist_path: Path,
    today=None,
) -> dict[str, Any]:
    """
    Aplica as linhas marcadas com 'Incluir' (qualquer valor não vazio) na
    planilha exportada por `watchlist.candidates_workbook`. Linha sem
    'Symbol' ou sem marcação é ignorada silenciosamente -- é o estado
    default de toda linha não tocada pelo usuário. Nunca reescreve uma
    linha já presente na watchlist (mesma recusa de duplicata do CLI
    manual); símbolo já presente conta como "skipped", não erro.
    """
    added: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for _, row in frame.iterrows():
        symbol = str(row.get("Symbol", "") or "").strip().upper()
        marked = str(row.get("Incluir", "") or "").strip()
        if not symbol or not marked:
            continue

        note = (
            str(row.get("Nota", "") or "").strip()
            or str(row.get("Motivo Sugerido", "") or "").strip()
            or DEFAULT_FALLBACK_NOTE
        )
        name = str(row.get("Name", "") or "").strip() or None
        trigger_condition = str(row.get("Gatilho Sugerido", "") or "").strip()

        try:
            result = promote_to_watchlist(
                symbol,
                note,
                watchlist_path=watchlist_path,
                name=name,
                trigger_condition=trigger_condition,
                today=today,
            )
            added.append(result.symbol)
        except SymbolAlreadyInWatchlistError:
            skipped.append(symbol)
        except (ValueError, WatchlistError) as exc:
            failed.append({"symbol": symbol, "error": str(exc)})

    return {"added": added, "skipped": skipped, "failed": failed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aplica as marcações 'Incluir' de uma planilha gerada por "
            "watchlist.candidates_workbook em config/watchlist.csv."
        )
    )
    parser.add_argument(
        "workbook",
        nargs="?",
        default="output/relatorios/watchlist_candidates.xlsx",
        help="Planilha salva (default: %(default)s).",
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--watchlist")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )

    workbook_path = Path(args.workbook)
    if not workbook_path.is_absolute():
        workbook_path = ROOT / workbook_path
    if not workbook_path.exists():
        raise RuntimeError(
            f"Planilha não encontrada: {workbook_path}. Rode "
            "watchlist.candidates_workbook primeiro."
        )

    watchlist_path = Path(
        args.watchlist
        or settings.get("watchlist_path", "config/watchlist.csv")
    )
    if not watchlist_path.is_absolute():
        watchlist_path = ROOT / watchlist_path

    frame = pd.read_excel(
        workbook_path, engine="openpyxl", dtype=str, keep_default_na=False
    )
    summary = apply_workbook(frame, watchlist_path=watchlist_path)

    print(f"Adicionados ({len(summary['added'])}): {summary['added']}")
    print(f"Já presentes, ignorados ({len(summary['skipped'])}): {summary['skipped']}")
    if summary["failed"]:
        print(f"Falhas ({len(summary['failed'])}): {summary['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

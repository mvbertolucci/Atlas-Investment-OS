from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from watchlist.csv_schema import REQUIRED_COLUMNS, canonical_column_name
from watchlist.exceptions import (
    WatchlistFileNotFoundError,
    WatchlistRowError,
    WatchlistSchemaError,
)
from watchlist.models import WatchlistEntry


def _clean_optional_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _canonicalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()

    renamed = {
        column: canonical_column_name(column)
        for column in result.columns
    }
    result = result.rename(columns=renamed)

    duplicated = result.columns[result.columns.duplicated()].tolist()
    if duplicated:
        raise WatchlistSchemaError(
            "Colunas duplicadas após normalização: "
            + ", ".join(sorted(set(duplicated)))
        )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in result.columns
    ]
    if missing:
        raise WatchlistSchemaError(
            "Colunas obrigatórias ausentes: " + ", ".join(missing)
        )

    return result


def entries_from_dataframe(
    frame: pd.DataFrame,
) -> tuple[WatchlistEntry, ...]:
    """
    Converte um DataFrame em entradas validadas. Retrocompatível: um frame
    com só `symbol` (ou `symbol,name`) carrega normalmente, com
    `included_at`/`note`/`trigger_condition` vazios.
    """
    if frame.empty:
        return ()

    normalized = _canonicalize_columns(frame)
    entries: list[WatchlistEntry] = []
    errors: list[str] = []

    for index, row in normalized.iterrows():
        line_number = int(index) + 2
        try:
            entries.append(
                WatchlistEntry(
                    symbol=row.get("symbol"),
                    name=_clean_optional_text(row.get("name")),
                    included_at=_clean_optional_text(
                        row.get("included_at")
                    )
                    or None,
                    note=_clean_optional_text(row.get("note")),
                    trigger_condition=_clean_optional_text(
                        row.get("trigger_condition")
                    ),
                    source=_clean_optional_text(row.get("source")) or "manual",
                    lifecycle_state=_clean_optional_text(row.get("lifecycle_state")) or "monitoring",
                    analytical_origin=_clean_optional_text(row.get("analytical_origin")) or "manual",
                    entry_rank=_clean_optional_text(row.get("entry_rank")) or None,
                    entry_score=_clean_optional_text(row.get("entry_score")) or None,
                    review_due_at=_clean_optional_text(row.get("review_due_at")) or None,
                    promotion_condition=_clean_optional_text(row.get("promotion_condition")),
                    discard_condition=_clean_optional_text(row.get("discard_condition")),
                )
            )
        except Exception as exc:
            errors.append(f"Linha {line_number}: {exc}")

    if errors:
        raise WatchlistRowError(
            "Foram encontradas linhas inválidas:\n" + "\n".join(errors)
        )

    symbols = [entry.symbol for entry in entries]
    if len(symbols) != len(set(symbols)):
        raise WatchlistSchemaError(
            "Watchlist contém símbolos duplicados."
        )

    return tuple(entries)


def load_watchlist_csv(
    file_path: Path,
) -> tuple[WatchlistEntry, ...]:
    """Carrega um CSV e devolve as entradas validadas da watchlist."""
    path = Path(file_path)

    if not path.exists():
        raise WatchlistFileNotFoundError(
            f"Watchlist não encontrada: {path}"
        )

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise WatchlistSchemaError(
            f"Não foi possível ler o CSV: {path}"
        ) from exc

    if frame.empty:
        raise WatchlistRowError(f"A watchlist está vazia: {path}")

    return entries_from_dataframe(frame)

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from portfolio.csv_schema import (
    REQUIRED_COLUMNS,
    canonical_column_name,
)
from portfolio.exceptions import (
    PortfolioFileNotFoundError,
    PortfolioRowError,
    PortfolioSchemaError,
)
from portfolio.models import Holding, Portfolio


def _clean_optional_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    return str(value).strip()


def _clean_optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PortfolioRowError(
            f"Valor numérico inválido: {value!r}"
        ) from exc


def _canonicalize_columns(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    renamed = {
        column: canonical_column_name(column)
        for column in result.columns
    }

    result = result.rename(columns=renamed)

    duplicated = result.columns[
        result.columns.duplicated()
    ].tolist()

    if duplicated:
        raise PortfolioSchemaError(
            "Colunas duplicadas após normalização: "
            + ", ".join(sorted(set(duplicated)))
        )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in result.columns
    ]

    if missing:
        raise PortfolioSchemaError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(missing)
        )

    return result


def _merge_duplicate_holdings(
    holdings: Iterable[Holding],
) -> tuple[Holding, ...]:
    grouped: "OrderedDict[str, list[Holding]]" = OrderedDict()

    for holding in holdings:
        grouped.setdefault(
            holding.symbol,
            [],
        ).append(holding)

    merged: list[Holding] = []

    for symbol, items in grouped.items():
        if len(items) == 1:
            merged.append(items[0])
            continue

        total_quantity = sum(
            item.quantity
            for item in items
        )

        weighted_cost = sum(
            item.quantity * item.average_price
            for item in items
        )

        average_price = (
            weighted_cost / total_quantity
        )

        current_prices = [
            item.current_price
            for item in items
            if item.current_price is not None
        ]

        current_price = (
            current_prices[-1]
            if current_prices
            else None
        )

        first = items[0]

        merged.append(
            Holding(
                symbol=symbol,
                quantity=total_quantity,
                average_price=average_price,
                current_price=current_price,
                sector=next(
                    (
                        item.sector
                        for item in items
                        if item.sector
                    ),
                    first.sector,
                ),
                industry=next(
                    (
                        item.industry
                        for item in items
                        if item.industry
                    ),
                    first.industry,
                ),
                country=next(
                    (
                        item.country
                        for item in items
                        if item.country
                    ),
                    first.country,
                ),
                currency=next(
                    (
                        item.currency
                        for item in items
                        if item.currency
                    ),
                    first.currency,
                ),
                notes="; ".join(
                    dict.fromkeys(
                        item.notes
                        for item in items
                        if item.notes
                    )
                ),
            )
        )

    return tuple(merged)


def holdings_from_dataframe(
    frame: pd.DataFrame,
    *,
    merge_duplicates: bool = True,
) -> tuple[Holding, ...]:
    """
    Converte um DataFrame em holdings validadas.
    """

    if frame.empty:
        return ()

    normalized = _canonicalize_columns(frame)

    holdings: list[Holding] = []
    errors: list[str] = []

    for index, row in normalized.iterrows():
        line_number = int(index) + 2

        try:
            holding = Holding(
                symbol=row.get("symbol"),
                quantity=row.get("quantity"),
                average_price=row.get("average_price"),
                current_price=_clean_optional_float(
                    row.get("current_price")
                ),
                currency=(
                    _clean_optional_text(
                        row.get("currency")
                    )
                    or "USD"
                ),
                sector=_clean_optional_text(
                    row.get("sector")
                ),
                industry=_clean_optional_text(
                    row.get("industry")
                ),
                country=_clean_optional_text(
                    row.get("country")
                ),
                notes=_clean_optional_text(
                    row.get("notes")
                ),
            )

            holdings.append(holding)

        except Exception as exc:
            errors.append(
                f"Linha {line_number}: {exc}"
            )

    if errors:
        raise PortfolioRowError(
            "Foram encontradas linhas inválidas:\n"
            + "\n".join(errors)
        )

    if merge_duplicates:
        return _merge_duplicate_holdings(
            holdings
        )

    return tuple(holdings)


def load_portfolio_csv(
    file_path: Path,
    *,
    portfolio_name: str | None = None,
    cash: float = 0.0,
    currency: str = "BRL",
    merge_duplicates: bool = True,
) -> Portfolio:
    """
    Carrega um CSV e devolve um objeto Portfolio.
    """

    path = Path(file_path)

    if not path.exists():
        raise PortfolioFileNotFoundError(
            f"Arquivo de carteira não encontrado: {path}"
        )

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise PortfolioSchemaError(
            f"Não foi possível ler o CSV: {path}"
        ) from exc

    holdings = holdings_from_dataframe(
        frame,
        merge_duplicates=merge_duplicates,
    )

    name = (
        portfolio_name
        or path.stem.replace("_", " ").strip()
        or "Portfolio"
    )

    return Portfolio(
        name=name,
        holdings=holdings,
        cash=cash,
        currency=currency,
    )

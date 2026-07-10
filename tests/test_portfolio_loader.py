from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portfolio.exceptions import (
    PortfolioFileNotFoundError,
    PortfolioRowError,
    PortfolioSchemaError,
)
from portfolio.loader import (
    holdings_from_dataframe,
    load_portfolio_csv,
)


def test_load_portfolio_csv(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "portfolio.csv"

    pd.DataFrame(
        {
            "symbol": ["MSFT", "GOOGL"],
            "quantity": [10, 5],
            "average_price": [400, 170],
            "current_price": [450, 180],
            "currency": ["USD", "USD"],
        }
    ).to_csv(
        file_path,
        index=False,
    )

    portfolio = load_portfolio_csv(
        file_path,
        portfolio_name="Minha Carteira",
        cash=1000,
    )

    assert portfolio.name == "Minha Carteira"
    assert portfolio.holdings_count == 2
    assert portfolio.total_market_value == 5400.0
    assert portfolio.total_value == 6400.0


def test_loader_accepts_column_aliases() -> None:
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"],
            "quantidade": [2],
            "preco_medio": [10],
        }
    )

    holdings = holdings_from_dataframe(frame)

    assert len(holdings) == 1
    assert holdings[0].symbol == "AAA"
    assert holdings[0].quantity == 2.0


def test_loader_merges_duplicate_symbols() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "quantity": [10, 20],
            "average_price": [10, 20],
            "current_price": [30, 30],
            "notes": ["Lote 1", "Lote 2"],
        }
    )

    holdings = holdings_from_dataframe(
        frame,
        merge_duplicates=True,
    )

    assert len(holdings) == 1

    holding = holdings[0]

    assert holding.quantity == 30.0
    assert holding.average_price == pytest.approx(
        16.6666666667,
        abs=1e-8,
    )
    assert holding.current_price == 30.0
    assert holding.notes == "Lote 1; Lote 2"


def test_loader_can_keep_duplicates() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "quantity": [1, 2],
            "average_price": [10, 20],
        }
    )

    holdings = holdings_from_dataframe(
        frame,
        merge_duplicates=False,
    )

    assert len(holdings) == 2


def test_loader_rejects_missing_required_columns() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "quantity": [1],
        }
    )

    with pytest.raises(PortfolioSchemaError):
        holdings_from_dataframe(frame)


def test_loader_reports_invalid_rows() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", ""],
            "quantity": [1, 0],
            "average_price": [10, 20],
        }
    )

    with pytest.raises(PortfolioRowError) as exc_info:
        holdings_from_dataframe(frame)

    message = str(exc_info.value)

    assert "Linha 3" in message


def test_loader_rejects_missing_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        PortfolioFileNotFoundError
    ):
        load_portfolio_csv(
            tmp_path / "missing.csv"
        )

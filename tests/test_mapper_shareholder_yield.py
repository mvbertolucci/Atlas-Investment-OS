from __future__ import annotations

import pandas as pd
import pytest

from analytics.mapper import normalize_columns


def test_dividend_and_buyback_combine_in_same_scale() -> None:
    """
    Dividendo (dividend_rate/price) e buyback (buyback/market_cap) devem
    somar na mesma escala (fração). Preço 100, rate 4 -> 4% de dividendo;
    buyback 100 sobre market_cap 1000 -> 10%. Total = 14%.
    """

    df = pd.DataFrame(
        {
            "price": [100.0],
            "market_cap": [1000.0],
            "dividend_rate": [4.0],
            "buyback": [100.0],
        }
    )

    out = normalize_columns(df)

    assert out["shareholder_yield"].iloc[0] == pytest.approx(0.14)


def test_buyback_only_when_no_dividend() -> None:
    """Não-pagador de dividendo com recompra deixa de ser NaN."""

    df = pd.DataFrame(
        {
            "price": [50.0],
            "market_cap": [1000.0],
            "dividend_rate": [None],
            "buyback": [200.0],
        }
    )

    out = normalize_columns(df)

    assert out["shareholder_yield"].iloc[0] == pytest.approx(0.20)


def test_dividend_only_when_no_buyback() -> None:
    df = pd.DataFrame(
        {
            "price": [200.0],
            "market_cap": [5000.0],
            "dividend_rate": [8.0],
            "buyback": [None],
        }
    )

    out = normalize_columns(df)

    assert out["shareholder_yield"].iloc[0] == pytest.approx(0.04)


def test_neither_dividend_nor_buyback_is_zero_not_nan() -> None:
    """
    Empresa sem dividendo e sem recompra tem shareholder yield 0 real
    (não NaN) -- economicamente pior que um pagador, e deve rankear baixo,
    não neutro.
    """

    df = pd.DataFrame(
        {
            "price": [100.0],
            "market_cap": [1000.0],
            "dividend_rate": [None],
            "buyback": [None],
        }
    )

    out = normalize_columns(df)

    assert out["shareholder_yield"].iloc[0] == pytest.approx(0.0)

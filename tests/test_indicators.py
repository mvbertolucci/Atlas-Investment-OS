from __future__ import annotations

import pandas as pd
import pytest

from analytics.indicators import (
    enrich_technicals,
    momentum,
    rsi,
    sma,
)


def test_sma_handles_numeric_coercion_and_short_series() -> None:
    assert sma(pd.Series([1, "2", None, 3]), 3) == 2.0
    assert sma(pd.Series([1, 2]), 3) is None


def test_momentum_contract_and_edge_cases() -> None:
    assert momentum(pd.Series([100, 110, 121]), 2) == pytest.approx(10.0)
    assert momentum(pd.Series([100, 110]), 2) is None
    assert momentum(pd.Series([10, 0, 20]), 2) is None


def test_rsi_for_gains_losses_and_short_series() -> None:
    assert rsi(pd.Series(range(1, 17)), 14) == 100.0
    assert rsi(pd.Series(range(17, 1, -1)), 14) == 0.0
    assert rsi(pd.Series([1, 2, 3]), 14) is None


def test_enrich_technicals_preserves_invalid_history() -> None:
    empty = {"symbol": "AAA", "history": []}
    missing_close = {"history": [{"Open": 1.0}]}
    invalid_close = {"history": [{"Close": "invalid"}]}

    assert enrich_technicals(empty) is empty
    assert enrich_technicals(missing_close) is missing_close
    assert enrich_technicals(invalid_close) is invalid_close


def test_enrich_technicals_adds_expected_metrics() -> None:
    closes = list(range(1, 254))
    row = {
        "price": 253.0,
        "history": [
            {"Close": close}
            for close in closes
        ],
    }

    result = enrich_technicals(row)

    assert result is row
    assert result["sma_50"] == pytest.approx(228.5)
    assert result["sma_200"] == pytest.approx(153.5)
    assert result["rsi_14"] == 100.0
    assert result["momentum_12m"] == pytest.approx(
        (253 / 2 - 1) * 100
    )
    assert result["distance_52w_high"] == 0.0
    assert result["distance_52w_low"] == pytest.approx(25200.0)


def test_enrich_technicals_uses_latest_close_when_price_missing() -> None:
    row = {
        "price": 0,
        "history": [
            {"Close": 10.0},
            {"Close": 20.0},
        ],
    }

    result = enrich_technicals(row)

    assert result["distance_52w_high"] == 0.0
    assert result["distance_52w_low"] == 100.0

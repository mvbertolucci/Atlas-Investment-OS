"""
Tests for deriving market_cap and the valuation ratios that depend on it
(pe, pb, altman_z) from a paired point-in-time price and the raw/derived
fields backtesting.point_in_time_fundamentals already produces.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from backtesting.point_in_time_valuation import derive_point_in_time_valuation


def _row(**overrides) -> dict:
    base = {
        "symbol": "AAA",
        "price": 50.0,
        "shares_outstanding": 100.0,
        "net_income": 150.0,
        "total_equity": 1200.0,
        "total_assets": 2000.0,
        "total_liabilities": 800.0,
        "working_capital": 250.0,
        "retained_earnings": 900.0,
        "operating_income": 200.0,
        "total_revenue": 1000.0,
        "long_term_debt": 300.0,
        "cash_and_equivalents": 100.0,
        "operating_cash_flow": 220.0,
        "capital_expenditures": 60.0,
        "dividends_paid": 40.0,
        "repurchase_of_stock": 25.0,
    }
    base.update(overrides)
    return base


def _approx(value, expected, tol=1e-4) -> bool:
    return value is not None and not math.isnan(value) and abs(value - expected) < tol


def test_market_cap_is_price_times_shares_outstanding() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    assert _approx(result.iloc[0]["market_cap"], 5000.0)


def test_market_cap_uses_split_adjusted_share_count() -> None:
    frame = pd.DataFrame(
        [_row(shares_outstanding_split_factor=4.0)]
    )
    result = derive_point_in_time_valuation(frame)

    assert _approx(
        result.iloc[0]["shares_outstanding_split_adjusted"], 400.0
    )
    assert _approx(result.iloc[0]["market_cap"], 20_000.0)


def test_reverse_split_factor_reduces_share_count_consistently() -> None:
    frame = pd.DataFrame(
        [_row(shares_outstanding_split_factor=0.1)]
    )
    result = derive_point_in_time_valuation(frame)

    assert _approx(result.iloc[0]["market_cap"], 500.0)


def test_pe_matches_hand_computed_value() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # market_cap 5000 / net_income 150
    assert _approx(result.iloc[0]["pe"], 5000.0 / 150.0)


def test_pe_is_missing_not_negative_when_net_income_is_not_positive() -> None:
    frame = pd.DataFrame([_row(net_income=-40.0)])
    result = derive_point_in_time_valuation(frame)
    assert pd.isna(result.iloc[0]["pe"])


def test_pb_matches_hand_computed_value() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    assert _approx(result.iloc[0]["pb"], 5000.0 / 1200.0)


def test_altman_z_matches_hand_computed_value_mirroring_analytics_fundamentals() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)

    # a = 250/2000 = 0.125; b = 900/2000 = 0.45; c = 200/2000 = 0.1
    # d = 5000/800 = 6.25; e = 1000/2000 = 0.5
    expected = 1.2 * 0.125 + 1.4 * 0.45 + 3.3 * 0.1 + 0.6 * 6.25 + 1.0 * 0.5
    assert _approx(result.iloc[0]["altman_z"], expected)


def test_missing_price_leaves_market_cap_and_dependents_missing() -> None:
    frame = pd.DataFrame([_row(price=None)])
    result = derive_point_in_time_valuation(frame)
    row = result.iloc[0]

    assert pd.isna(row["market_cap"])
    assert pd.isna(row["pe"])
    assert pd.isna(row["pb"])
    assert pd.isna(row["altman_z"])


def test_missing_price_column_entirely_leaves_market_cap_missing() -> None:
    frame = pd.DataFrame([{k: v for k, v in _row().items() if k != "price"}])
    result = derive_point_in_time_valuation(frame)
    assert pd.isna(result.iloc[0]["market_cap"])


def test_zero_total_liabilities_yields_missing_altman_z_term_not_infinite() -> None:
    frame = pd.DataFrame([_row(total_liabilities=0.0)])
    result = derive_point_in_time_valuation(frame)
    assert pd.isna(result.iloc[0]["altman_z"])


def test_preexisting_market_cap_is_never_overwritten() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "market_cap": 999.0,
                "price": 50.0,
                "shares_outstanding": 100.0,
            }
        ]
    )
    result = derive_point_in_time_valuation(frame)
    assert result.iloc[0]["market_cap"] == 999.0


def test_preexisting_altman_z_is_never_overwritten() -> None:
    frame = pd.DataFrame([_row(altman_z=7.0)])
    result = derive_point_in_time_valuation(frame)
    assert result.iloc[0]["altman_z"] == 7.0


def test_does_not_mutate_or_drop_input_columns() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)

    assert result.iloc[0]["price"] == 50.0
    assert result.iloc[0]["shares_outstanding"] == 100.0
    assert "symbol" in result.columns


def test_enterprise_value_uses_long_term_debt_and_cash() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # market_cap 5000 + long_term_debt 300 - cash_and_equivalents 100
    assert _approx(result.iloc[0]["enterprise_value"], 5200.0)


def test_ev_ebit_matches_hand_computed_value_mirroring_analytics_mapper() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # enterprise_value 5200 / operating_income 200
    assert _approx(result.iloc[0]["ev_ebit"], 5200.0 / 200.0)


def test_ev_ebit_is_missing_not_infinite_when_operating_income_is_zero() -> None:
    frame = pd.DataFrame([_row(operating_income=0.0)])
    result = derive_point_in_time_valuation(frame)
    assert pd.isna(result.iloc[0]["ev_ebit"])


def test_free_cash_flow_is_operating_cash_flow_minus_capex() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # operating_cash_flow 220 - capital_expenditures 60
    assert _approx(result.iloc[0]["free_cash_flow"], 160.0)


def test_fcf_yield_matches_hand_computed_value_mirroring_analytics_mapper() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # free_cash_flow 160 / market_cap 5000
    assert _approx(result.iloc[0]["fcf_yield"], 160.0 / 5000.0)


def test_fcf_yield_is_missing_when_capex_is_absent() -> None:
    frame = pd.DataFrame(
        [{k: v for k, v in _row().items() if k != "capital_expenditures"}]
    )
    result = derive_point_in_time_valuation(frame)
    assert pd.isna(result.iloc[0]["free_cash_flow"])
    assert pd.isna(result.iloc[0]["fcf_yield"])


def test_shareholder_yield_is_dividends_plus_buybacks_over_market_cap() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_valuation(frame)
    # (dividends_paid 40 + repurchase_of_stock 25) / market_cap 5000
    assert _approx(result.iloc[0]["shareholder_yield"], 65.0 / 5000.0)


def test_shareholder_yield_treats_missing_dividend_tag_as_zero_distribution() -> None:
    """
    Mirrors analytics/mapper.py's fillna(0.0) per leg: an absent dividend
    tag means "no dividend distribution" (a genuine reading), not
    "unknown" -- the buyback leg alone still produces a real ratio.
    """
    frame = pd.DataFrame(
        [{k: v for k, v in _row().items() if k != "dividends_paid"}]
    )
    result = derive_point_in_time_valuation(frame)
    # (0 + repurchase_of_stock 25) / market_cap 5000
    assert _approx(result.iloc[0]["shareholder_yield"], 25.0 / 5000.0)


def test_missing_market_cap_leaves_new_yield_ratios_missing() -> None:
    frame = pd.DataFrame([_row(price=None)])
    result = derive_point_in_time_valuation(frame)
    row = result.iloc[0]

    assert pd.isna(row["ev_ebit"])
    assert pd.isna(row["fcf_yield"])
    assert pd.isna(row["shareholder_yield"])


def test_preexisting_ev_ebit_and_fcf_yield_are_never_overwritten() -> None:
    frame = pd.DataFrame([_row(ev_ebit=11.0, fcf_yield=0.05, shareholder_yield=0.02)])
    result = derive_point_in_time_valuation(frame)

    assert result.iloc[0]["ev_ebit"] == 11.0
    assert result.iloc[0]["fcf_yield"] == 0.05
    assert result.iloc[0]["shareholder_yield"] == 0.02

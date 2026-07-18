"""
Live (analytics/fundamentals.py) vs point-in-time (backtesting/
point_in_time_fundamentals.py) ROIC and Interest Coverage equivalence guard.

STATUS.md documents a measured, real divergence between the two paths (a
2-4 p.p. ROIC gap and, for low-debt companies, a large absolute Interest
Coverage gap) with "no automatic equivalence test between the two paths."
The root cause is documented as the EBIT (live, from Yahoo) vs
operating_income (point-in-time, SEC EDGAR has no EBIT tag) proxy fed into
both NOPAT and Interest Coverage's numerator -- not a formula bug in either
path.

This test isolates that hypothesis instead of chasing an unreproducible
real-world number: construct inputs for both paths describing the exact
same underlying company (EBIT == operating_income, and the point-in-time
debt/equity/cash components summing to the same dollar figure the live
path receives as a single "Invested Capital" line). If the two
independently-implemented formulas do not then agree exactly, one of them
changed structurally (tax-rate fallback, invested_capital composition,
proxy substitution) without the other being updated in step -- exactly the
drift STATUS.md asked to be guarded against.
"""
from __future__ import annotations

import pandas as pd
import pytest

from analytics.fundamentals import _compute_interest_coverage, _compute_roic
from backtesting.point_in_time_fundamentals import derive_point_in_time_ratios


def _live_statements() -> tuple[pd.DataFrame, pd.DataFrame]:
    column = pd.Timestamp("2025-12-31")
    income_stmt = pd.DataFrame(
        {
            "EBIT": [100.0],
            "Interest Expense": [20.0],
            "Pretax Income": [90.0],
            "Tax Provision": [18.0],
        },
        index=[column],
    ).T
    balance_sheet = pd.DataFrame(
        {"Invested Capital": [500.0]}, index=[column]
    ).T
    return balance_sheet, income_stmt


def _point_in_time_row() -> dict:
    return {
        "symbol": "AAA",
        # Same EBIT the live path reads above -- zero proxy gap by design.
        "operating_income": 100.0,
        "interest_expense": 20.0,
        "pretax_income": 90.0,
        "tax_provision": 18.0,
        # total_debt(100) + total_equity(400) - cash(0) == Invested
        # Capital(500) fed to the live path as a single reported figure.
        "long_term_debt": 100.0,
        "long_term_debt_current": 0.0,
        "short_term_debt": 0.0,
        "total_equity": 400.0,
        "cash_and_equivalents": 0.0,
    }


def test_roic_and_interest_coverage_agree_when_ebit_equals_operating_income() -> (
    None
):
    balance_sheet, income_stmt = _live_statements()
    live_roic = _compute_roic(balance_sheet, income_stmt)
    live_coverage = _compute_interest_coverage(income_stmt)

    point_in_time = derive_point_in_time_ratios(
        pd.DataFrame([_point_in_time_row()])
    ).iloc[0]

    # Hand-computed sanity check, same numbers as tests/test_fundamentals.py.
    assert live_roic == pytest.approx(0.16)
    assert live_coverage == pytest.approx(5.0)

    assert point_in_time["roic"] == pytest.approx(live_roic)
    assert point_in_time["interest_coverage"] == pytest.approx(live_coverage)


def test_roic_gap_tracks_only_the_documented_ebit_proxy_difference() -> None:
    """Same inputs, except operating_income now differs from EBIT (e.g. D&A
    or a non-operating item Yahoo's EBIT excludes but the SEC operating-
    income tag includes). The resulting ROIC/coverage gap must be explained
    entirely by that difference, proving the two invested_capital/NOPAT
    formulas are otherwise identical -- not an independent second source of
    divergence.
    """
    balance_sheet, income_stmt = _live_statements()
    live_roic = _compute_roic(balance_sheet, income_stmt)
    live_coverage = _compute_interest_coverage(income_stmt)

    row = _point_in_time_row()
    row["operating_income"] = 110.0  # +10 vs EBIT=100
    point_in_time = derive_point_in_time_ratios(pd.DataFrame([row])).iloc[0]

    tax_rate = 18.0 / 90.0
    expected_roic = (110.0 * (1 - tax_rate)) / 500.0
    expected_coverage = 110.0 / 20.0

    assert point_in_time["roic"] == pytest.approx(expected_roic)
    assert point_in_time["interest_coverage"] == pytest.approx(expected_coverage)
    assert point_in_time["roic"] != pytest.approx(live_roic)
    assert point_in_time["interest_coverage"] != pytest.approx(live_coverage)

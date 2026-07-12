from __future__ import annotations

import pandas as pd
import pytest

from analytics.fundamentals import compute_fundamentals


COL_T = pd.Timestamp("2025-12-31")
COL_T1 = pd.Timestamp("2024-12-31")


def _statement(data: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(data, index=[COL_T, COL_T1]).T


def _full_statements() -> dict[str, pd.DataFrame]:
    """
    Duas safras (T e T-1) construídas para bater com contas feitas à mão:
    interest_coverage=5.0, roic=0.16, altman_z=4.99, f_score_annual=9.0
    (todos os 9 critérios do Piotroski positivos).
    """

    income_stmt = _statement(
        {
            "EBIT": [100.0, 80.0],
            "Interest Expense": [20.0, 25.0],
            "Pretax Income": [90.0, 70.0],
            "Tax Provision": [18.0, 14.0],
            "Net Income": [72.0, 56.0],
            "Gross Profit": [400.0, 300.0],
            "Total Revenue": [1000.0, 800.0],
        }
    )
    balance_sheet = _statement(
        {
            "Invested Capital": [500.0, 450.0],
            "Total Assets": [1000.0, 900.0],
            "Working Capital": [200.0, 150.0],
            "Retained Earnings": [300.0, 250.0],
            "Total Liabilities Net Minority Interest": [400.0, 380.0],
            "Long Term Debt": [100.0, 150.0],
            "Current Assets": [350.0, 300.0],
            "Current Liabilities": [150.0, 160.0],
            "Ordinary Shares Number": [100.0, 100.0],
        }
    )
    cashflow = _statement({"Operating Cash Flow": [90.0, 60.0]})

    return {
        "_balance_sheet": balance_sheet,
        "_income_statement": income_stmt,
        "_cashflow": cashflow,
    }


def test_compute_fundamentals_full_statements() -> None:
    row = {"symbol": "TEST", "market_cap": 2000.0, **_full_statements()}

    result = compute_fundamentals(row)

    assert result["ebit"] == pytest.approx(100.0)
    assert result["interest_coverage"] == pytest.approx(5.0)
    assert result["roic"] == pytest.approx(0.16)
    assert result["altman_z"] == pytest.approx(4.99)
    assert result["f_score_annual"] == pytest.approx(9.0)


def test_compute_fundamentals_strips_raw_statements() -> None:
    row = {"symbol": "TEST", "market_cap": 2000.0, **_full_statements()}

    result = compute_fundamentals(row)

    assert "_balance_sheet" not in result
    assert "_income_statement" not in result
    assert "_cashflow" not in result


def test_compute_fundamentals_missing_statements_returns_none() -> None:
    row = {
        "symbol": "TEST",
        "market_cap": 2000.0,
        "_balance_sheet": None,
        "_income_statement": None,
        "_cashflow": None,
    }

    result = compute_fundamentals(row)

    assert result["ebit"] is None
    assert result["interest_coverage"] is None
    assert result["roic"] is None
    assert result["altman_z"] is None
    assert result["f_score_annual"] is None


def test_f_score_requires_two_full_years() -> None:
    """
    Com apenas uma safra, um score parcial mediria menos que os 9
    critérios e distorceria o ranking -- deve retornar None, não um
    score incompleto.
    """

    statements = _full_statements()
    # Zera a coluna do ano anterior (T-1) para simular histórico incompleto.
    for key in ("_balance_sheet", "_income_statement", "_cashflow"):
        statements[key] = statements[key].drop(columns=[COL_T1])

    row = {"symbol": "TEST", "market_cap": 2000.0, **statements}

    result = compute_fundamentals(row)

    assert result["f_score_annual"] is None
    # As demais métricas só precisam do ano corrente e continuam disponíveis.
    assert result["interest_coverage"] == pytest.approx(5.0)
    assert result["roic"] == pytest.approx(0.16)


def test_interest_coverage_zero_interest_expense_is_none() -> None:
    statements = _full_statements()
    statements["_income_statement"].loc["Interest Expense", COL_T] = 0.0
    row = {"symbol": "TEST", "market_cap": 2000.0, **statements}

    result = compute_fundamentals(row)

    assert result["interest_coverage"] is None


def test_roic_falls_back_to_statutory_rate_without_pretax_income() -> None:
    statements = _full_statements()
    statements["_income_statement"].loc["Pretax Income", COL_T] = float("nan")
    row = {"symbol": "TEST", "market_cap": 2000.0, **statements}

    result = compute_fundamentals(row)

    # NOPAT = 100 * (1 - 0.21) = 79; ROIC = 79 / 500
    assert result["roic"] == pytest.approx(79.0 / 500.0)


def test_buyback_absolute_value() -> None:
    statements = _full_statements()
    statements["_cashflow"].loc["Repurchase Of Capital Stock", COL_T] = -1500.0
    row = {"symbol": "TEST", "market_cap": 2000.0, **statements}

    result = compute_fundamentals(row)

    assert result["buyback"] == pytest.approx(1500.0)


def test_buyback_none_when_absent() -> None:
    row = {"symbol": "TEST", "market_cap": 2000.0, **_full_statements()}

    result = compute_fundamentals(row)

    # _full_statements não inclui linha de recompra.
    assert result["buyback"] is None

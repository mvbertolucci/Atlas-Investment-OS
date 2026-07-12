from __future__ import annotations

import pandas as pd


def _row_value(statement: pd.DataFrame | None, label: str, col_index: int = 0):
    if statement is None or statement.empty or label not in statement.index:
        return None
    try:
        value = statement.loc[label].iloc[col_index]
    except IndexError:
        return None
    if pd.isna(value):
        return None
    return float(value)


def _safe_div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _compute_interest_coverage(income_stmt: pd.DataFrame | None) -> float | None:
    ebit = _row_value(income_stmt, "EBIT")
    interest_expense = _row_value(income_stmt, "Interest Expense")
    if interest_expense is not None:
        interest_expense = abs(interest_expense)
    return _safe_div(ebit, interest_expense)


def _compute_roic(
    balance_sheet: pd.DataFrame | None,
    income_stmt: pd.DataFrame | None,
) -> float | None:
    ebit = _row_value(income_stmt, "EBIT")
    invested_capital = _row_value(balance_sheet, "Invested Capital")
    if ebit is None or not invested_capital:
        return None

    pretax_income = _row_value(income_stmt, "Pretax Income")
    tax_provision = _row_value(income_stmt, "Tax Provision")
    tax_rate = _safe_div(tax_provision, pretax_income)
    # Sem pretax income (ou tax rate implausível), assume a aliquota
    # estatutaria dos EUA como fallback em vez de descartar o feature.
    if tax_rate is None or not (0.0 <= tax_rate <= 1.0):
        tax_rate = 0.21

    nopat = ebit * (1 - tax_rate)
    return _safe_div(nopat, invested_capital)


def _compute_altman_z(
    balance_sheet: pd.DataFrame | None,
    income_stmt: pd.DataFrame | None,
    market_cap: float | None,
) -> float | None:
    total_assets = _row_value(balance_sheet, "Total Assets")
    if not total_assets:
        return None

    working_capital = _row_value(balance_sheet, "Working Capital") or 0.0
    retained_earnings = _row_value(balance_sheet, "Retained Earnings") or 0.0
    total_liabilities = _row_value(balance_sheet, "Total Liabilities Net Minority Interest")
    ebit = _row_value(income_stmt, "EBIT") or 0.0
    revenue = _row_value(income_stmt, "Total Revenue") or 0.0

    a = working_capital / total_assets
    b = retained_earnings / total_assets
    c = ebit / total_assets
    d = _safe_div(market_cap, total_liabilities) or 0.0
    e = revenue / total_assets

    return 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e


def _compute_f_score(
    balance_sheet: pd.DataFrame | None,
    income_stmt: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
) -> float | None:
    """
    Piotroski F-Score (0-9), comparando o ano corrente (col 0) com o
    anterior (col 1). Exige as duas safras completas: um score parcial
    por falta de dado do ano anterior mediria menos do que os 9 critérios
    e distorceria o ranking, então retorna None nesse caso.
    """

    net_income_t = _row_value(income_stmt, "Net Income", 0)
    net_income_t1 = _row_value(income_stmt, "Net Income", 1)
    total_assets_t = _row_value(balance_sheet, "Total Assets", 0)
    total_assets_t1 = _row_value(balance_sheet, "Total Assets", 1)
    operating_cf_t = _row_value(cashflow, "Operating Cash Flow", 0)
    current_assets_t = _row_value(balance_sheet, "Current Assets", 0)
    current_liabilities_t = _row_value(balance_sheet, "Current Liabilities", 0)
    current_assets_t1 = _row_value(balance_sheet, "Current Assets", 1)
    current_liabilities_t1 = _row_value(balance_sheet, "Current Liabilities", 1)
    shares_t = _row_value(balance_sheet, "Ordinary Shares Number", 0)
    shares_t1 = _row_value(balance_sheet, "Ordinary Shares Number", 1)
    gross_profit_t = _row_value(income_stmt, "Gross Profit", 0)
    gross_profit_t1 = _row_value(income_stmt, "Gross Profit", 1)
    revenue_t = _row_value(income_stmt, "Total Revenue", 0)
    revenue_t1 = _row_value(income_stmt, "Total Revenue", 1)

    required = [
        net_income_t, net_income_t1, total_assets_t, total_assets_t1,
        operating_cf_t, current_assets_t, current_liabilities_t,
        current_assets_t1, current_liabilities_t1, shares_t, shares_t1,
        gross_profit_t, gross_profit_t1, revenue_t, revenue_t1,
    ]
    if any(value is None for value in required) or not total_assets_t or not total_assets_t1:
        return None

    long_term_debt_t = _row_value(balance_sheet, "Long Term Debt", 0) or 0.0
    long_term_debt_t1 = _row_value(balance_sheet, "Long Term Debt", 1) or 0.0

    roa_t = net_income_t / total_assets_t
    roa_t1 = net_income_t1 / total_assets_t1
    leverage_t = long_term_debt_t / total_assets_t
    leverage_t1 = long_term_debt_t1 / total_assets_t1
    current_ratio_t = _safe_div(current_assets_t, current_liabilities_t)
    current_ratio_t1 = _safe_div(current_assets_t1, current_liabilities_t1)
    margin_t = _safe_div(gross_profit_t, revenue_t)
    margin_t1 = _safe_div(gross_profit_t1, revenue_t1)
    turnover_t = revenue_t / total_assets_t
    turnover_t1 = revenue_t1 / total_assets_t1

    score = 0
    score += 1 if net_income_t > 0 else 0                        # 1. Lucro positivo
    score += 1 if operating_cf_t > 0 else 0                       # 2. CFO positivo
    score += 1 if roa_t > roa_t1 else 0                           # 3. ROA melhorou
    score += 1 if operating_cf_t > net_income_t else 0            # 4. Qualidade do lucro (accruals)
    score += 1 if leverage_t < leverage_t1 else 0                 # 5. Alavancagem caiu
    score += 1 if (current_ratio_t is not None and current_ratio_t1 is not None
                   and current_ratio_t > current_ratio_t1) else 0  # 6. Liquidez melhorou
    score += 1 if shares_t <= shares_t1 else 0                    # 7. Sem diluição nova
    score += 1 if (margin_t is not None and margin_t1 is not None
                   and margin_t > margin_t1) else 0                # 8. Margem bruta melhorou
    score += 1 if turnover_t > turnover_t1 else 0                 # 9. Giro de ativos melhorou

    return float(score)


def compute_fundamentals(row: dict) -> dict:
    """
    Deriva roic, f_score_annual, altman_z, interest_coverage e ebit a
    partir das demonstrações financeiras brutas anexadas pelo provider
    (_balance_sheet/_income_statement/_cashflow), e descarta essas
    demonstrações do row antes de seguir no pipeline (mesmo padrão de
    enrich_technicals com "history").
    """

    balance_sheet = row.pop("_balance_sheet", None)
    income_stmt = row.pop("_income_statement", None)
    cashflow = row.pop("_cashflow", None)

    row["ebit"] = _row_value(income_stmt, "EBIT")
    row["interest_coverage"] = _compute_interest_coverage(income_stmt)
    row["roic"] = _compute_roic(balance_sheet, income_stmt)
    row["altman_z"] = _compute_altman_z(balance_sheet, income_stmt, row.get("market_cap"))
    row["f_score_annual"] = _compute_f_score(balance_sheet, income_stmt, cashflow)

    return row

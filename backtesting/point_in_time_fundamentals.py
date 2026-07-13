from __future__ import annotations

import pandas as pd


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(float("nan"), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _assign_if_absent(
    result: pd.DataFrame,
    column: str,
    values: pd.Series,
) -> None:
    """Só cria a coluna se ela não existir -- nunca sobrescreve uma razão
    que o frame de entrada já forneceu diretamente."""
    if column not in result.columns:
        result[column] = values


def derive_point_in_time_ratios(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Computa, a partir das colunas BRUTAS reconstruídas de observações
    point-in-time da SEC (ver `backtesting.sec_edgar.FIELD_TAG_CANDIDATES`),
    as mesmas razões derivadas que `analytics/fundamentals.py` e
    `analytics/mapper.py` computam para dado ao vivo do Yahoo.

    Isso existe porque `config/features.yaml` (o que o motor de scoring
    realmente lê) pede razões -- gross_margin, net_margin, current_ratio,
    roic etc. -- não os totais brutos em dólar que a SEC fornece. Sem esta
    camada, replay do walk-forward sobre dado real da SEC cairia quase
    inteiramente em fatores neutros (50), mascarando silenciosamente que o
    dado chegou sem produzir um score significativo.

    Pura: opera sobre uma cópia, nunca sobrescreve as colunas brutas de
    entrada. Uma razão cujos componentes estão ausentes na linha fica
    ausente (NaN) -- nunca inventada ou emprestada de outra linha/data.

    Se o frame de entrada JÁ tiver uma coluna de razão (ex.: um dataset que
    fornece `roic` diretamente, de outra fonte), essa coluna é preservada
    intacta -- esta função só PREENCHE razões ausentes, nunca recalcula e
    sobrescreve uma já fornecida.

    Aproximações documentadas (não escondidas):
    - `debt_to_equity`/`roic` usam apenas `long_term_debt` (não há tag
      nativa separada para a parcela circulante da dívida neste mapeamento
      ainda).
    - `interest_coverage`/`roic` usam `operating_income`
      (`us-gaap:OperatingIncomeLoss`) como proxy de EBIT -- a mesma decisão
      já documentada em `sec_edgar.py`.
    - `tax_rate` (usado no NOPAT do ROIC) cai para a alíquota estatutária
      dos EUA (21%) quando `pretax_income`/`tax_provision` estão ausentes
      ou implicam uma taxa fora de [0, 1] -- mesmo fallback de
      `analytics/fundamentals.py::_compute_roic`, não um valor novo
      inventado aqui.

    NÃO computado aqui (fronteira explícita, não este incremento):
    - `f_score_annual`: exige comparar dois exercícios (t vs t-1) -- duas
      reconstruções point-in-time distintas, não uma única linha.
    - `altman_z`: precisa de `market_cap` (preço × ações em circulação);
      SEC EDGAR não tem preço (ver `docs/SEC_EDGAR_DATA.md`). Não
      computado aqui para não silenciosamente aproximar o termo de
      mercado com zero.
    """
    result = frame.copy()

    total_revenue = _numeric(result, "total_revenue").replace(0, pd.NA)
    total_assets = _numeric(result, "total_assets")
    current_assets = _numeric(result, "current_assets")
    current_liabilities = _numeric(result, "current_liabilities").replace(
        0, pd.NA
    )
    total_liabilities = _numeric(result, "total_liabilities")
    gross_profit = _numeric(result, "gross_profit")
    net_income = _numeric(result, "net_income")
    operating_income = _numeric(result, "operating_income")
    long_term_debt = _numeric(result, "long_term_debt")
    interest_expense = _numeric(result, "interest_expense").abs()
    pretax_income = _numeric(result, "pretax_income").replace(0, pd.NA)
    tax_provision = _numeric(result, "tax_provision")
    cash = _numeric(result, "cash_and_equivalents")

    _assign_if_absent(result, "gross_margin", gross_profit / total_revenue)
    _assign_if_absent(
        result, "operating_margin", operating_income / total_revenue
    )
    _assign_if_absent(result, "net_margin", net_income / total_revenue)
    _assign_if_absent(
        result, "current_ratio", current_assets / current_liabilities
    )
    _assign_if_absent(
        result, "working_capital", current_assets - current_liabilities
    )

    # total_equity é intermediário (não um feature do Atlas), mas ainda
    # respeita a mesma regra de não sobrescrever se já fornecido.
    total_equity = (
        pd.to_numeric(result["total_equity"], errors="coerce")
        if "total_equity" in result.columns
        else total_assets - total_liabilities
    )
    _assign_if_absent(result, "total_equity", total_equity)
    equity_denominator = total_equity.replace(0, pd.NA)

    _assign_if_absent(
        result, "debt_to_equity", long_term_debt / equity_denominator
    )
    _assign_if_absent(
        result,
        "interest_coverage",
        operating_income / interest_expense.replace(0, pd.NA),
    )
    _assign_if_absent(result, "roe", net_income / equity_denominator)

    tax_rate = tax_provision / pretax_income
    tax_rate = tax_rate.where((tax_rate >= 0) & (tax_rate <= 1), 0.21)
    nopat = operating_income * (1 - tax_rate)
    invested_capital = (long_term_debt + total_equity - cash).replace(
        0, pd.NA
    )
    _assign_if_absent(result, "roic", nopat / invested_capital)

    return result

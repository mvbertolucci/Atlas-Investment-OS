from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

import pandas as pd

from backtesting.point_in_time import HistoricalObservation, StockSplitRecord


F_SCORE_REQUIRED_FIELDS = frozenset(
    {
        "net_income",
        "total_assets",
        "operating_cash_flow",
        "current_assets",
        "current_liabilities",
        "shares_outstanding",
        "gross_profit",
        "total_revenue",
    }
)


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
    - `debt_to_equity`/`roic` usam dívida total (`long_term_debt` +
      `long_term_debt_current` + `short_term_debt`, cada componente ausente
      no filing tratado como zero, não como dado faltante -- a maioria das
      empresas não carrega uma das duas linhas). Medido contra dado real
      (3 empresas): antes de incluir `long_term_debt_current`/
      `short_term_debt`, o ROIC point-in-time saía sistematicamente 2-4 p.p.
      acima do ao vivo (capital investido subestimado); ver STATUS.md
      seção 2 para o registro da medição antes/depois.
    - `interest_coverage`/`roic` usam `operating_income`
      (`us-gaap:OperatingIncomeLoss`) como proxy de EBIT -- a mesma decisão
      já documentada em `sec_edgar.py`.
    - `tax_rate` (usado no NOPAT do ROIC) cai para a alíquota estatutária
      dos EUA (21%) quando `pretax_income`/`tax_provision` estão ausentes
      ou implicam uma taxa fora de [0, 1] -- mesmo fallback de
      `analytics/fundamentals.py::_compute_roic`, não um valor novo
      inventado aqui.

    `f_score_annual` é derivado separadamente por
    `derive_point_in_time_f_scores`, porque exige o histórico de dois 10-Ks,
    não apenas a linha mais recente deste frame.

    NÃO computado aqui: `altman_z` precisa de `market_cap` (preço × ações em circulação);
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
    # Componentes ausentes no filing (não apenas não mapeados) viram zero --
    # a maioria das empresas de fato não carrega uma das duas linhas. Só
    # `long_term_debt` em si permanece NaN quando ausente (dado central,
    # nunca inventado); as duas linhas abaixo são refinamento aditivo.
    long_term_debt_current = _numeric(
        result, "long_term_debt_current"
    ).fillna(0)
    short_term_debt = _numeric(result, "short_term_debt").fillna(0)
    total_debt = long_term_debt + long_term_debt_current + short_term_debt
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
        result, "debt_to_equity", total_debt / equity_denominator
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
    invested_capital = (total_debt + total_equity - cash).replace(
        0, pd.NA
    )
    _assign_if_absent(result, "roic", nopat / invested_capital)

    return result


def _annual_filing_rows(
    history: Iterable[HistoricalObservation],
) -> dict[str, list[dict[str, object]]]:
    by_filing: dict[
        tuple[str, str, object], list[HistoricalObservation]
    ] = defaultdict(list)
    for observation in history:
        if not observation.source.startswith("SEC EDGAR (10-K"):
            continue
        by_filing[
            (
                observation.symbol,
                observation.revision_id,
                observation.available_at,
            )
        ].append(observation)

    candidates: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (symbol, revision_id, available_at), observations in by_filing.items():
        selected: dict[str, HistoricalObservation] = {}
        for observation in observations:
            current = selected.get(observation.field_name)
            if current is None or observation.observed_on > current.observed_on:
                selected[observation.field_name] = observation
        period_observations = [
            observation
            for field_name, observation in selected.items()
            if field_name != "shares_outstanding"
        ]
        if not period_observations:
            continue
        candidates[symbol].append(
            {
                "period_end": max(
                    observation.observed_on
                    for observation in period_observations
                ),
                "available_at": available_at,
                "revision_id": revision_id,
                "observations": selected,
            }
        )

    result: dict[str, list[dict[str, object]]] = {}
    for symbol, filings in candidates.items():
        merged_by_period: dict[date, dict[str, object]] = {}
        for filing in sorted(
            filings,
            key=lambda item: (item["available_at"], item["revision_id"]),
        ):
            period_end = filing["period_end"]
            current = merged_by_period.get(period_end)
            if current is None:
                merged_by_period[period_end] = {
                    **filing,
                    "observations": dict(filing["observations"]),
                }
                continue
            current["observations"].update(filing["observations"])
            current["available_at"] = filing["available_at"]
            current["revision_id"] = filing["revision_id"]
        result[symbol] = sorted(
            merged_by_period.values(),
            key=lambda item: item["period_end"],
            reverse=True,
        )
    return result


def _filing_value(
    filing: dict[str, object], field_name: str
) -> float | None:
    observations = filing["observations"]
    observation = observations.get(field_name)
    if observation is None:
        return None
    try:
        value = float(observation.value)
    except (TypeError, ValueError):
        return None
    if value != value:
        return None
    return value


def _shares_on_common_basis(
    prior_filing: dict[str, object],
    current_filing: dict[str, object],
    splits: Iterable[StockSplitRecord],
    symbol: str,
) -> tuple[float | None, float | None]:
    prior = _filing_value(prior_filing, "shares_outstanding")
    current = _filing_value(current_filing, "shares_outstanding")
    if prior is None or current is None:
        return prior, current
    prior_observation = prior_filing["observations"]["shares_outstanding"]
    current_observation = current_filing["observations"]["shares_outstanding"]
    factor = 1.0
    for split in splits:
        if (
            split.symbol == symbol
            and prior_observation.observed_on
            < split.effective_on
            <= current_observation.observed_on
        ):
            factor *= split.ratio
    return prior * factor, current


def _compute_f_score_from_filings(
    current: dict[str, object],
    prior: dict[str, object],
    splits: Iterable[StockSplitRecord],
    symbol: str,
) -> float | None:
    gap_days = (current["period_end"] - prior["period_end"]).days
    if not 300 <= gap_days <= 430:
        return None

    required_current = {
        field_name: _filing_value(current, field_name)
        for field_name in F_SCORE_REQUIRED_FIELDS
    }
    required_prior = {
        field_name: _filing_value(prior, field_name)
        for field_name in F_SCORE_REQUIRED_FIELDS - {"operating_cash_flow"}
    }
    if any(value is None for value in required_current.values()) or any(
        value is None for value in required_prior.values()
    ):
        return None

    total_assets_t = required_current["total_assets"]
    total_assets_t1 = required_prior["total_assets"]
    current_liabilities_t = required_current["current_liabilities"]
    current_liabilities_t1 = required_prior["current_liabilities"]
    revenue_t = required_current["total_revenue"]
    revenue_t1 = required_prior["total_revenue"]
    if (
        total_assets_t == 0
        or total_assets_t1 == 0
        or current_liabilities_t == 0
        or current_liabilities_t1 == 0
        or revenue_t == 0
        or revenue_t1 == 0
    ):
        return None

    net_income_t = required_current["net_income"]
    net_income_t1 = required_prior["net_income"]
    operating_cf_t = required_current["operating_cash_flow"]
    roa_t = net_income_t / total_assets_t
    roa_t1 = net_income_t1 / total_assets_t1
    leverage_t = (_filing_value(current, "long_term_debt") or 0.0) / total_assets_t
    leverage_t1 = (_filing_value(prior, "long_term_debt") or 0.0) / total_assets_t1
    current_ratio_t = required_current["current_assets"] / current_liabilities_t
    current_ratio_t1 = required_prior["current_assets"] / current_liabilities_t1
    margin_t = required_current["gross_profit"] / revenue_t
    margin_t1 = required_prior["gross_profit"] / revenue_t1
    turnover_t = revenue_t / total_assets_t
    turnover_t1 = revenue_t1 / total_assets_t1
    shares_t1, shares_t = _shares_on_common_basis(
        prior, current, splits, symbol
    )

    score = 0
    score += int(net_income_t > 0)
    score += int(operating_cf_t > 0)
    score += int(roa_t > roa_t1)
    score += int(operating_cf_t > net_income_t)
    score += int(leverage_t < leverage_t1)
    score += int(current_ratio_t > current_ratio_t1)
    score += int(shares_t <= shares_t1)
    score += int(margin_t > margin_t1)
    score += int(turnover_t > turnover_t1)
    return float(score)


def derive_point_in_time_f_scores(
    frame: pd.DataFrame,
    history: Iterable[HistoricalObservation],
    splits: Iterable[StockSplitRecord] = (),
) -> pd.DataFrame:
    """Deriva Piotroski F-Score de dois 10-Ks visíveis, sem imputação."""
    result = frame.copy()
    if "f_score_annual" in result.columns:
        return result
    filings_by_symbol = _annual_filing_rows(history)
    values: list[float | None] = []
    for _, row in result.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        filings = filings_by_symbol.get(symbol, [])
        value = (
            _compute_f_score_from_filings(
                filings[0], filings[1], splits, symbol
            )
            if len(filings) >= 2
            else None
        )
        values.append(value)
    result["f_score_annual"] = values
    return result

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
    """Só cria a coluna se ela não existir -- nunca sobrescreve um valor que
    o frame de entrada já forneceu diretamente."""
    if column not in result.columns:
        result[column] = values


def derive_point_in_time_valuation(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Computa `market_cap` (preço × ações em circulação ajustadas por splits)
    e as razões de
    valuation que dependem dele -- `pe`, `pb`, `altman_z` -- a partir de uma
    coluna `price` (ver `backtesting.price_history`, pareada por data) e das
    colunas brutas/derivadas já produzidas por
    `backtesting.point_in_time_fundamentals`.

    `altman_z` espelha exatamente `analytics/fundamentals.py::_compute_altman_z`
    (mesmos cinco termos, mesmos pesos), agora com `market_cap` real em vez
    de ausente -- antes desta camada `altman_z` nunca podia ser calculado no
    replay point-in-time (SEC EDGAR não tem preço).

    Pura, assign-if-absent: nunca sobrescreve uma coluna já fornecida.

    O frame reconstruído pode fornecer `shares_outstanding_split_factor`,
    calculado apenas com eventos efetivos entre a data observada das ações e a
    data observada do preço. A coluna auditável
    `shares_outstanding_split_adjusted` preserva a quantidade usada no cálculo.
    Sem o fator, o comportamento compatível permanece 1.0.

    Também deriva, a partir das mesmas colunas point-in-time mais
    `capital_expenditures` e `dividends_paid` (SEC EDGAR
    `PaymentsToAcquirePropertyPlantAndEquipment` /
    `PaymentsOfDividends[CommonStock]`, ver `backtesting.sec_edgar`):

    - `enterprise_value = market_cap + long_term_debt - cash_and_equivalents`
      -- mesma aproximação já documentada e usada por `debt_to_equity`/`roic`
      em `point_in_time_fundamentals.py` (só `long_term_debt`, sem uma tag
      separada para a parcela circulante da dívida).
    - `ev_ebit = enterprise_value / operating_income`, mesma fórmula de
      `analytics/mapper.py` (`enterprise_value / ebit`), com
      `operating_income` como proxy de EBIT (decisão já explícita em
      `sec_edgar.py`).
    - `free_cash_flow = operating_cash_flow - capital_expenditures`;
      `fcf_yield = free_cash_flow / market_cap` -- mesma razão de
      `analytics/mapper.py` (`free_cashflow / market_cap`), com o FCF
      recomputado das duas pernas point-in-time em vez de recebido pronto
      do provedor.
    - `shareholder_yield = (dividends_paid + repurchase_of_stock) / market_cap`
      -- mesmo conceito de `analytics/mapper.py` (dividendo + recompra, como
      fração do valor de mercado), adaptado: o mapper ao vivo usa
      `dividend_rate / price` (taxa por ação); aqui, sem uma tag limpa de
      dividendo por ação, o dividendo agregado (`dividends_paid`) é dividido
      por `market_cap`, na mesma escala já usada para a perna de recompra em
      ambas as versões. Mesmo `fillna(0.0)` por perna que o mapper já usa:
      ausência da tag de dividendo OU de recompra é lida como "nenhuma
      distribuição dessa modalidade", não como "desconhecido" -- só fica
      ausente se `market_cap` também faltar.

    NÃO computado aqui (fronteira explícita, precisa de uma fonte nova, não
    apenas de uma tag adicional da mesma SEC EDGAR): `forward_pe` e `peg`
    exigem estimativa de analistas -- nenhuma fonte point-in-time gratuita
    para isso está integrada. `ev_ebitda` fica de fora porque o pipeline ao
    vivo (`analytics/mapper.py`) simplesmente repassa o `enterpriseToEbitda`
    já calculado do Yahoo, sem fórmula própria para espelhar -- inventar uma
    definição de EBITDA (operating_income + depreciação/amortização) sem
    precedente ao vivo para validar contra seria uma aproximação nova, não
    documentada em lugar nenhum, então fica deliberadamente de fora até
    existir um formato de referência. A família de fatores `timing`
    (`rsi_14`, `momentum_*`, `distance_52w_high`), que precisa da série de
    preço inteira em cada corte, é derivada separadamente por
    `backtesting.point_in_time_timing.derive_point_in_time_timing`.
    """
    result = frame.copy()

    price = _numeric(result, "price")
    shares_outstanding = _numeric(result, "shares_outstanding")
    split_factor = _numeric(
        result, "shares_outstanding_split_factor"
    ).fillna(1.0)
    adjusted_shares = shares_outstanding * split_factor
    _assign_if_absent(
        result,
        "shares_outstanding_split_adjusted",
        adjusted_shares,
    )
    _assign_if_absent(result, "market_cap", price * adjusted_shares)

    market_cap = pd.to_numeric(result["market_cap"], errors="coerce")

    # PE convencionalmente não é reportado (nem negativo, nem zero) para
    # lucro líquido não positivo -- mesma convenção que o Yahoo já aplica na
    # ponta ao vivo (analytics/fundamentals.py não recomputa PE, então não
    # há um precedente direto aqui, mas um PE negativo pontuaria como
    # "extremamente barato" sob a regra higher_is_better=false, distorcendo
    # o ranking em vez de refletir prejuízo).
    net_income = _numeric(result, "net_income")
    positive_net_income = net_income.where(net_income > 0)
    _assign_if_absent(result, "pe", market_cap / positive_net_income)

    total_equity = _numeric(result, "total_equity").replace(0, pd.NA)
    _assign_if_absent(result, "pb", market_cap / total_equity)

    total_assets = _numeric(result, "total_assets")
    total_assets_denominator = total_assets.replace(0, pd.NA)
    working_capital = _numeric(result, "working_capital")
    retained_earnings = _numeric(result, "retained_earnings")
    operating_income = _numeric(result, "operating_income")
    total_revenue = _numeric(result, "total_revenue")
    total_liabilities = _numeric(result, "total_liabilities").replace(0, pd.NA)

    altman_a = working_capital / total_assets_denominator
    altman_b = retained_earnings / total_assets_denominator
    altman_c = operating_income / total_assets_denominator
    altman_d = market_cap / total_liabilities
    altman_e = total_revenue / total_assets_denominator
    altman_z = (
        1.2 * altman_a
        + 1.4 * altman_b
        + 3.3 * altman_c
        + 0.6 * altman_d
        + 1.0 * altman_e
    )
    _assign_if_absent(result, "altman_z", altman_z)

    long_term_debt = _numeric(result, "long_term_debt")
    cash_and_equivalents = _numeric(result, "cash_and_equivalents")
    enterprise_value = market_cap + long_term_debt - cash_and_equivalents
    _assign_if_absent(result, "enterprise_value", enterprise_value)
    _assign_if_absent(
        result, "ev_ebit", enterprise_value / operating_income.replace(0, pd.NA)
    )

    operating_cash_flow = _numeric(result, "operating_cash_flow")
    capital_expenditures = _numeric(result, "capital_expenditures")
    free_cash_flow = operating_cash_flow - capital_expenditures
    _assign_if_absent(result, "free_cash_flow", free_cash_flow)
    market_cap_denominator = market_cap.replace(0, pd.NA)
    _assign_if_absent(result, "fcf_yield", free_cash_flow / market_cap_denominator)

    # Mesmo fillna(0.0) por perna que analytics/mapper.py já usa: a ausência
    # da tag de dividendo ou de recompra é tratada como "nenhuma distribuição
    # dessa modalidade" (uma leitura genuína, não uma suposição arriscada),
    # não como "desconhecido" -- só fica ausente se market_cap também faltar.
    dividends_paid = _numeric(result, "dividends_paid").fillna(0.0)
    repurchase_of_stock = _numeric(result, "repurchase_of_stock").fillna(0.0)
    _assign_if_absent(
        result,
        "shareholder_yield",
        (dividends_paid + repurchase_of_stock) / market_cap_denominator,
    )

    return result

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
    Computa `market_cap` (preço × ações em circulação) e as razões de
    valuation que dependem dele -- `pe`, `pb`, `altman_z` -- a partir de uma
    coluna `price` (ver `backtesting.price_history`, pareada por data) e das
    colunas brutas/derivadas já produzidas por
    `backtesting.point_in_time_fundamentals`.

    `altman_z` espelha exatamente `analytics/fundamentals.py::_compute_altman_z`
    (mesmos cinco termos, mesmos pesos), agora com `market_cap` real em vez
    de ausente -- antes desta camada `altman_z` nunca podia ser calculado no
    replay point-in-time (SEC EDGAR não tem preço).

    Pura, assign-if-absent: nunca sobrescreve uma coluna já fornecida.

    **Limitação documentada, não escondida**: o fechamento histórico do
    Yahoo (`backtesting.price_history`) vem retroativamente ajustado por
    desdobramentos (splits) futuros, mas `shares_outstanding` (SEC EDGAR) é
    a contagem real de ações na data do filing, SEM esse ajuste. Logo,
    `market_cap` (e `pe`/`pb`/`altman_z`, que dependem dele) só está correto
    para datas de decisão NO OU APÓS o desdobramento mais recente da empresa
    (ou para empresas sem desdobramento no período coberto) -- para datas
    anteriores a um desdobramento, o valor sai errado por exatamente o fator
    do desdobramento. Não corrigido neste incremento; ver
    docs/PRICE_HISTORY_DATA.md e o item correspondente em docs/BACKLOG.md.

    NÃO computado aqui (fronteira explícita): `forward_pe` (exige estimativa
    de analistas), `ev_ebitda` (exige uma tag de depreciação/amortização
    ainda não coletada), `ev_ebit` (exige um enterprise_value limpo, com
    dívida total e não só de longo prazo), `peg` (exige estimativa de
    crescimento), `shareholder_yield`/`fcf_yield` (exigem tags de dividendo/
    fluxo de caixa livre ainda não coletadas), e toda a família de fatores
    `timing` (`rsi_14`, `momentum_*`, `distance_52w_high`), que precisam da
    série de preço inteira em cada corte, não de um único valor pontual.
    """
    result = frame.copy()

    price = _numeric(result, "price")
    shares_outstanding = _numeric(result, "shares_outstanding")
    _assign_if_absent(result, "market_cap", price * shares_outstanding)

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

    return result

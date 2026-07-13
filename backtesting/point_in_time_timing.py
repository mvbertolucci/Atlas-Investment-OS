from __future__ import annotations

from typing import Iterable

import pandas as pd

from analytics.indicators import momentum, rsi
from backtesting.point_in_time import HistoricalObservation, StockSplitRecord

TIMING_FIELDS = ("rsi_14", "momentum_3m", "momentum_6m", "momentum_12m", "distance_52w_high")

_MOMENTUM_WINDOWS = {"momentum_3m": 63, "momentum_6m": 126, "momentum_12m": 252}


def _assign_if_absent(result: pd.DataFrame, column: str, values: list) -> None:
    """Só cria a coluna se ela não existir -- nunca sobrescreve um valor de
    timing que o frame de entrada já forneceu diretamente."""
    if column not in result.columns:
        result[column] = values


def _continuous_price_series(
    symbol: str,
    history: Iterable[HistoricalObservation],
    splits: Iterable[StockSplitRecord],
) -> pd.Series:
    """
    Reconstrói, apenas para os fatores de timing, uma série contínua de
    fechamentos a partir do histórico point-in-time visível no corte.

    `HistoricalObservation(field_name="price")` já guarda o preço
    efetivamente negociado (as-traded) em cada data -- necessário para
    market_cap, mas descontínuo através de qualquer split. Para momentum/RSI
    aqui cada preço mais antigo é dividido pelo produto cumulativo dos
    ratios de split com `effective_on` estritamente posterior à sua própria
    data e até (inclusive) a data do preço mais recente visível neste
    corte. Usa somente `splits` já filtrados por `AsOfSnapshot` (efetivos e
    conhecidos no corte) -- um split futuro nunca altera um replay anterior,
    e o próprio preço mais recente nunca é dividido (fator 1.0).
    """
    by_date: dict[object, HistoricalObservation] = {}
    for observation in history:
        if observation.symbol != symbol or observation.field_name != "price":
            continue
        current = by_date.get(observation.observed_on)
        if current is None or (
            observation.available_at,
            observation.revision_id,
        ) > (current.available_at, current.revision_id):
            by_date[observation.observed_on] = observation

    if not by_date:
        return pd.Series(dtype=float)

    dates = sorted(by_date)
    latest_date = dates[-1]
    symbol_splits = [split for split in splits if split.symbol == symbol]

    values: dict[object, float] = {}
    for observed_on in dates:
        ratio_product = 1.0
        for split in symbol_splits:
            if observed_on < split.effective_on <= latest_date:
                ratio_product *= split.ratio
        values[observed_on] = float(by_date[observed_on].value) / ratio_product

    return pd.Series([values[d] for d in dates], index=dates)


def derive_point_in_time_timing(
    frame: pd.DataFrame,
    history: Iterable[HistoricalObservation],
    splits: Iterable[StockSplitRecord] = (),
) -> pd.DataFrame:
    """
    Deriva `rsi_14`, `momentum_3m/6m/12m` e `distance_52w_high` a partir da
    série de preço point-in-time completa visível em cada corte, espelhando
    exatamente a semântica de `analytics/indicators.py` (mesmas janelas de
    pregão, mesmas fórmulas).

    Diferente de `derive_point_in_time_ratios`/`derive_point_in_time_valuation`
    (que operam linha a linha sobre colunas já pareadas), esta função precisa
    do histórico multi-data por símbolo -- por isso recebe `history` e
    `splits` separadamente, no mesmo padrão de
    `derive_point_in_time_f_scores`.

    Assign-if-absent por coluna: nunca sobrescreve um valor de timing já
    fornecido pelo frame de entrada. Um símbolo sem histórico de preço
    suficiente para uma janela fica com esse indicador ausente (NaN) --
    nunca inventado ou emprestado de outro símbolo/data. `target_upside`
    não é computado aqui: exige uma fonte de preço-alvo de analistas
    point-in-time genuína, ainda não coletada.
    """
    result = frame.copy()
    history = tuple(history)
    splits = tuple(splits)

    missing_columns = [
        column for column in TIMING_FIELDS if column not in result.columns
    ]
    if not missing_columns:
        return result

    computed: dict[str, list[float | None]] = {column: [] for column in missing_columns}
    for _, row in result.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        series = _continuous_price_series(symbol, history, splits)

        if "rsi_14" in computed:
            computed["rsi_14"].append(rsi(series, 14) if not series.empty else None)
        for column, window in _MOMENTUM_WINDOWS.items():
            if column in computed:
                computed[column].append(
                    momentum(series, window) if not series.empty else None
                )
        if "distance_52w_high" in computed:
            if series.empty:
                computed["distance_52w_high"].append(None)
            else:
                last_price = float(series.iloc[-1])
                high = float(series.max())
                computed["distance_52w_high"].append(
                    (last_price / high - 1) * 100 if last_price and high else None
                )

    for column, values in computed.items():
        _assign_if_absent(result, column, values)

    return result

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from backtesting.point_in_time import HistoricalObservation, StockSplitRecord

DEFAULT_SOURCE = "yahoo_daily_close"
DEFAULT_SPLIT_SOURCE = "yahoo_stock_splits"


def _row_date(timestamp) -> date:
    return (
        timestamp.date()
        if hasattr(timestamp, "date")
        else date.fromisoformat(str(timestamp))
    )


def _split_events(price_history: pd.DataFrame) -> tuple[tuple[date, float], ...]:
    if "Stock Splits" not in price_history.columns:
        return ()
    events: list[tuple[date, float]] = []
    for timestamp, value in price_history["Stock Splits"].items():
        if pd.isna(value):
            continue
        ratio = float(value)
        if ratio > 0 and ratio != 1:
            events.append((_row_date(timestamp), ratio))
    return tuple(sorted(events))


def available_at_from_trade_date(trade_date: date | str) -> str:
    """
    Mesma convenção conservadora de `sec_edgar.available_at_from_filed`: um
    fechamento diário só é tratado como consolidado/disponível a partir da
    meia-noite UTC do dia SEGUINTE ao pregão, para nunca arriscar look-ahead
    no mesmo dia.
    """
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    available = datetime.combine(
        trade_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return available.isoformat()


def fetch_price_history(
    symbol: str, *, period: str = "max", interval: str = "1d"
) -> pd.DataFrame:
    """
    Busca ao vivo (Yahoo Finance via yfinance) -- espelha
    `backtesting.sec_edgar.fetch_company_facts`: wrapper fino, não testado
    por unidade (só sua contraparte pura, `extract_price_observations`, é).

    `auto_adjust=False` evita o ajuste adicional por dividendos. O fechamento
    ainda vem normalizado por splits; `extract_price_observations` usa a coluna
    `Stock Splits` para restaurar o preço efetivamente negociado em cada data.
    """
    ticker = yf.Ticker(symbol)
    history = ticker.history(period=period, interval=interval, auto_adjust=False)
    if history is None or history.empty:
        raise RuntimeError(f"Sem histórico de preço para {symbol}")
    return history


def extract_price_observations(
    symbol: str,
    price_history: pd.DataFrame,
    *,
    source: str = DEFAULT_SOURCE,
) -> tuple[HistoricalObservation, ...]:
    """
    Conversão pura: uma HistoricalObservation(field_name="price") por pregão
    com fechamento válido, `observed_on` a data do pregão e `available_at` a
    meia-noite UTC do dia seguinte (`available_at_from_trade_date`) -- a
    mesma convenção sem look-ahead já usada para filings da SEC. Quando a
    coluna `Stock Splits` está presente, desfaz a normalização retroativa do
    Yahoo multiplicando cada fechamento apenas pelos splits futuros.

    `revision_id` é a própria data do pregão: um fechamento diário não é
    corrigido por revisão (diferente de um filing, que pode ganhar um 10-K/A),
    então a data já garante identidade única por símbolo/campo.
    """
    if "Close" not in price_history.columns:
        return ()

    split_events = _split_events(price_history)
    observations: list[HistoricalObservation] = []
    for timestamp, row in price_history.iterrows():
        close = row["Close"]
        if pd.isna(close):
            continue
        trade_date = _row_date(timestamp)
        future_split_factor = 1.0
        for effective_on, ratio in split_events:
            if effective_on > trade_date:
                future_split_factor *= ratio
        observations.append(
            HistoricalObservation(
                symbol=symbol,
                field_name="price",
                value=float(close) * future_split_factor,
                observed_on=trade_date,
                available_at=available_at_from_trade_date(trade_date),
                source=source,
                revision_id=trade_date.isoformat(),
            )
        )
    return tuple(observations)


def extract_split_records(
    symbol: str,
    price_history: pd.DataFrame,
    *,
    source: str = DEFAULT_SPLIT_SOURCE,
) -> tuple[StockSplitRecord, ...]:
    """Extrai splits; cada evento só entra no as-of após sua data efetiva."""
    return tuple(
        StockSplitRecord(
            symbol=symbol,
            effective_on=effective_on,
            ratio=ratio,
            known_at=available_at_from_trade_date(effective_on),
            source=source,
        )
        for effective_on, ratio in _split_events(price_history)
    )

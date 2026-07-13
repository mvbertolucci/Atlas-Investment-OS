from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from backtesting.point_in_time import HistoricalObservation

DEFAULT_SOURCE = "yahoo_daily_close"


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

    `auto_adjust=False` evita que o fechamento também seja retroativamente
    ajustado por dividendos -- mas o Yahoo/yfinance não expõe, por este
    endpoint, o preço realmente negociado em cada pregão histórico: o
    fechamento retornado já vem ajustado por desdobramentos (splits)
    futuros, para manter a série contínua em gráficos. Isso tem uma
    implicação real para `market_cap` -- ver docs/PRICE_HISTORY_DATA.md.
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
    mesma convenção sem look-ahead já usada para filings da SEC.

    `revision_id` é a própria data do pregão: um fechamento diário não é
    corrigido por revisão (diferente de um filing, que pode ganhar um 10-K/A),
    então a data já garante identidade única por símbolo/campo.
    """
    if "Close" not in price_history.columns:
        return ()

    observations: list[HistoricalObservation] = []
    for timestamp, row in price_history.iterrows():
        close = row["Close"]
        if pd.isna(close):
            continue
        trade_date = (
            timestamp.date() if hasattr(timestamp, "date") else date.fromisoformat(str(timestamp))
        )
        observations.append(
            HistoricalObservation(
                symbol=symbol,
                field_name="price",
                value=float(close),
                observed_on=trade_date,
                available_at=available_at_from_trade_date(trade_date),
                source=source,
                revision_id=trade_date.isoformat(),
            )
        )
    return tuple(observations)

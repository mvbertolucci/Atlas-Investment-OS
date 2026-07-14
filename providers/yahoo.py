from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf


def _safe_float(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _safe_statement(ticker: "yf.Ticker", attr: str):
    """Busca uma demonstração financeira anual (balance_sheet/financials/
    cashflow). Alguns tickers (ETFs, ADRs sem cobertura) não têm essas
    demonstrações; nesse caso retorna None em vez de propagar exceção."""
    try:
        statement = getattr(ticker, attr)
        if statement is None or statement.empty:
            return None
        return statement
    except Exception:
        return None


def _earnings_date(info: dict[str, Any]) -> str | None:
    """Normaliza a data de earnings atribuída pelo provider, quando houver."""
    value = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp != timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def fetch_symbol(symbol: str, name_hint: str = "", period: str = "2y", interval: str = "1d") -> dict:
    """Fetch one ticker from Yahoo Finance and return raw data for Atlas.

    This provider is intentionally limited to broadly available fields. More
    advanced fields can later come from FMP, Finnhub, SEC, or calculated modules.
    """
    t = yf.Ticker(symbol)
    info = t.info or {}
    hist = t.history(period=period, interval=interval)

    if hist is None or hist.empty:
        raise RuntimeError(f"Sem histórico para {symbol}")

    hist = hist.dropna(subset=["Close"])
    if hist.empty:
        raise RuntimeError(f"Sem fechamento válido para {symbol}")

    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last

    price = _safe_float(last.get("Close"))
    previous_close = _safe_float(prev.get("Close"))
    change_pct = (price / previous_close - 1) * 100 if price and previous_close else None

    return {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or name_hint or symbol,
        "quote_type": info.get("quoteType"),
        "exchange": info.get("exchange"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price": price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "volume": _safe_float(last.get("Volume")),
        "average_volume": _safe_float(info.get("averageVolume")),
        "market_cap": _safe_float(info.get("marketCap")),
        "enterprise_value": _safe_float(info.get("enterpriseValue")),
        "year_high": _safe_float(info.get("fiftyTwoWeekHigh")),
        "year_low": _safe_float(info.get("fiftyTwoWeekLow")),
        "beta": _safe_float(info.get("beta")),
        "pe": _safe_float(info.get("trailingPE")),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "peg": _safe_float(info.get("pegRatio")),
        "pb": _safe_float(info.get("priceToBook")),
        "ps": _safe_float(info.get("priceToSalesTrailing12Months")),
        "ev_to_ebitda": _safe_float(info.get("enterpriseToEbitda")),
        "ev_to_revenue": _safe_float(info.get("enterpriseToRevenue")),
        "roe": _safe_float(info.get("returnOnEquity")),
        "roa": _safe_float(info.get("returnOnAssets")),
        "gross_margin": _safe_float(info.get("grossMargins")),
        "operating_margin": _safe_float(info.get("operatingMargins")),
        "ebitda_margin": _safe_float(info.get("ebitdaMargins")),
        "net_margin": _safe_float(info.get("profitMargins")),
        "debt_to_equity": _safe_float(info.get("debtToEquity")),
        "current_ratio": _safe_float(info.get("currentRatio")),
        "quick_ratio": _safe_float(info.get("quickRatio")),
        "total_debt": _safe_float(info.get("totalDebt")),
        "total_cash": _safe_float(info.get("totalCash")),
        "ebitda": _safe_float(info.get("ebitda")),
        "free_cashflow": _safe_float(info.get("freeCashflow")),
        "operating_cashflow": _safe_float(info.get("operatingCashflow")),
        "dividend_yield": _safe_float(info.get("dividendYield")),
        "dividend_rate": _safe_float(info.get("dividendRate")),
        "target_price": _safe_float(info.get("targetMeanPrice")),
        "target_high_price": _safe_float(info.get("targetHighPrice")),
        "target_low_price": _safe_float(info.get("targetLowPrice")),
        "analyst_count": _safe_float(info.get("numberOfAnalystOpinions")),
        "rating": info.get("recommendationKey"),
        "earnings_date": _earnings_date(info),
        "short_float": _safe_float(info.get("shortPercentOfFloat")),
        "insider_own": _safe_float(info.get("heldPercentInsiders")),
        "inst_own": _safe_float(info.get("heldPercentInstitutions")),
        "history": hist.reset_index().to_dict("records"),
        "source": "Yahoo Finance",
        "_balance_sheet": _safe_statement(t, "balance_sheet"),
        "_income_statement": _safe_statement(t, "financials"),
        "_cashflow": _safe_statement(t, "cashflow"),
    }


def fetch_watchlist(
    watchlist: pd.DataFrame,
    period: str = "2y",
    interval: str = "1d",
    *,
    failures: list[str] | None = None,
) -> list[dict]:
    """
    `failures`, se informado, recebe "SYMBOL: erro" para cada fetch que
    falhou -- opcional para não quebrar chamadores existentes que só querem
    as linhas coletadas.
    """
    rows: list[dict] = []
    for _, row in watchlist.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        name = str(row.get("name", "")).strip()
        try:
            rows.append(fetch_symbol(symbol, name, period=period, interval=interval))
            print(f"[OK] {symbol}")
        except Exception as exc:
            print(f"[ERRO] {symbol}: {exc}")
            if failures is not None:
                failures.append(f"{symbol}: {exc}")
    return rows

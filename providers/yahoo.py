from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import yfinance as yf

from providers.contracts import ProviderClient, ProviderError, ProviderPolicy
from providers.evidence import ensure_field_evidence, reconcile_critical_fields
from storage.raw_snapshots import store_raw_snapshot


DEFAULT_CRITICAL_FIELDS = (
    "market_cap",
    "enterprise_value",
    "total_debt",
    "total_cash",
    "ebitda",
    "free_cashflow",
    "current_ratio",
    "short_float",
)


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

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or name_hint or symbol,
        "quote_type": info.get("quoteType"),
        "exchange": info.get("exchange"),
        "country": info.get("country"),
        "currency": info.get("currency"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "as_of": retrieved_at,
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
    info_fields = {
        "name": ("longName", "shortName"),
        "quote_type": ("quoteType",),
        "exchange": ("exchange",),
        "country": ("country",),
        "currency": ("currency",),
        "sector": ("sector",),
        "industry": ("industry",),
        "average_volume": ("averageVolume",),
        "market_cap": ("marketCap",),
        "enterprise_value": ("enterpriseValue",),
        "year_high": ("fiftyTwoWeekHigh",),
        "year_low": ("fiftyTwoWeekLow",),
        "beta": ("beta",),
        "pe": ("trailingPE",),
        "forward_pe": ("forwardPE",),
        "peg": ("pegRatio",),
        "pb": ("priceToBook",),
        "ps": ("priceToSalesTrailing12Months",),
        "ev_to_ebitda": ("enterpriseToEbitda",),
        "ev_to_revenue": ("enterpriseToRevenue",),
        "roe": ("returnOnEquity",),
        "roa": ("returnOnAssets",),
        "gross_margin": ("grossMargins",),
        "operating_margin": ("operatingMargins",),
        "ebitda_margin": ("ebitdaMargins",),
        "net_margin": ("profitMargins",),
        "debt_to_equity": ("debtToEquity",),
        "current_ratio": ("currentRatio",),
        "quick_ratio": ("quickRatio",),
        "total_debt": ("totalDebt",),
        "total_cash": ("totalCash",),
        "ebitda": ("ebitda",),
        "free_cashflow": ("freeCashflow",),
        "operating_cashflow": ("operatingCashflow",),
        "dividend_yield": ("dividendYield",),
        "dividend_rate": ("dividendRate",),
        "target_price": ("targetMeanPrice",),
        "target_high_price": ("targetHighPrice",),
        "target_low_price": ("targetLowPrice",),
        "analyst_count": ("numberOfAnalystOpinions",),
        "rating": ("recommendationKey",),
        "earnings_date": ("earningsTimestamp", "earningsTimestampStart"),
        "short_float": ("shortPercentOfFloat",),
        "insider_own": ("heldPercentInsiders",),
        "inst_own": ("heldPercentInstitutions",),
    }
    raw_presence: dict[str, bool] = {
        "symbol": True,
        "price": "Close" in last,
        "previous_close": "Close" in prev,
        "change_pct": "Close" in last and "Close" in prev,
        "volume": "Volume" in last,
    }
    raw_values: dict[str, Any] = {
        "symbol": symbol,
        "price": last.get("Close"),
        "previous_close": prev.get("Close"),
        "change_pct": change_pct,
        "volume": last.get("Volume"),
    }
    for field_name, keys in info_fields.items():
        present_keys = [key for key in keys if key in info]
        raw_presence[field_name] = bool(present_keys)
        raw_values[field_name] = next(
            (info.get(key) for key in keys if info.get(key) is not None),
            None,
        )
    market_observed_at = pd.Timestamp(hist.index[-1]).isoformat()
    return ensure_field_evidence(
        record,
        source="Yahoo Finance",
        retrieved_at=retrieved_at,
        raw_presence=raw_presence,
        raw_values=raw_values,
        observed_at_by_category={"market": market_observed_at},
    )


def fetch_watchlist(
    watchlist: pd.DataFrame,
    period: str = "2y",
    interval: str = "1d",
    *,
    failures: list[str] | None = None,
    provider_policy: ProviderPolicy | None = None,
    raw_snapshot_dir: str | Path | None = None,
    secondary_fetcher: Callable[..., dict[str, Any]] | None = None,
    critical_fields: Iterable[str] = DEFAULT_CRITICAL_FIELDS,
) -> list[dict]:
    """
    `failures`, se informado, recebe "SYMBOL: erro" para cada fetch que
    falhou -- opcional para não quebrar chamadores existentes que só querem
    as linhas coletadas.
    """
    rows: list[dict] = []
    client = ProviderClient("Yahoo Finance", provider_policy)
    secondary_client = ProviderClient("Secondary", provider_policy)
    for _, row in watchlist.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        name = str(row.get("name", "")).strip()
        try:
            primary = client.execute(
                "fetch_symbol",
                fetch_symbol,
                symbol,
                name,
                period=period,
                interval=interval,
            )
            if raw_snapshot_dir is not None:
                receipt = store_raw_snapshot(
                    primary,
                    raw_snapshot_dir,
                    provider="Yahoo Finance",
                    symbol=symbol,
                    collected_at=str(primary["as_of"]),
                )
                primary["raw_snapshot_hash"] = receipt.sha256
                primary["raw_snapshot_path"] = str(receipt.path)
            secondary = None
            if secondary_fetcher is not None:
                try:
                    secondary = secondary_client.execute(
                        "fetch_symbol",
                        secondary_fetcher,
                        symbol,
                        name,
                        period=period,
                        interval=interval,
                    )
                except ProviderError as secondary_error:
                    primary["secondary_provider_error"] = secondary_error.to_dict()
                else:
                    ensure_field_evidence(secondary)
                    if raw_snapshot_dir is not None:
                        secondary_receipt = store_raw_snapshot(
                            secondary,
                            raw_snapshot_dir,
                            provider=str(secondary.get("source") or "Secondary"),
                            symbol=symbol,
                            collected_at=str(secondary.get("as_of") or primary["as_of"]),
                        )
                        primary["secondary_raw_snapshot_hash"] = secondary_receipt.sha256
                        primary["secondary_raw_snapshot_path"] = str(
                            secondary_receipt.path
                        )
            rows.append(
                reconcile_critical_fields(
                    primary,
                    secondary,
                    critical_fields,
                )
            )
            print(f"[OK] {symbol}")
        except Exception as exc:
            print(f"[ERRO] {symbol}: {exc}")
            if failures is not None:
                failures.append(f"{symbol}: {exc}")
    return rows

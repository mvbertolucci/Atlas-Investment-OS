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


def _trailing_pe_structurally_absent(pe_value: Any, info: dict[str, Any]) -> bool:
    """Whether a missing trailing PE reflects non-positive trailing earnings
    (a structural absence) rather than a fetch failure.

    Yahoo simply omits ``trailingPE`` for companies with non-positive trailing
    EPS -- the ratio is mathematically undefined, not merely unfetched. In that
    case PE should be marked ``not_applicable`` (excluded from the coverage
    denominator and the required-feature confidence gate), not ``missing``,
    which would wrongly penalise loss-making/turnaround holdings that still have
    full valuation evidence (EV/EBITDA, Forward PE, Price/Book). We only
    conclude "structural" when a positive earnings signal confirms the loss --
    absence of every signal keeps the conservative ``missing`` classification so
    a genuine fetch failure is never masked.
    """
    if _safe_float(pe_value) is not None:
        return False
    for key in ("trailingEps", "netIncomeToCommon", "profitMargins"):
        signal = _safe_float(info.get(key))
        if signal is not None and signal <= 0:
            return True
    return False


def _stockholders_equity(balance_sheet: "pd.DataFrame | None") -> float | None:
    """Most recent common/stockholders equity from the annual balance sheet.

    Used only to tell apart the two reasons ``returnOnEquity`` can be absent
    from Yahoo: a genuine fetch gap for a solvent company (equity > 0 -> ROE
    exists, reconcile it) versus a structurally undefined ratio (equity <= 0,
    e.g. an accumulated-deficit biotech -> dividing by negative book equity
    yields a meaningless number, so ROE is not_applicable)."""
    if balance_sheet is None:
        return None
    for label in (
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ):
        try:
            if label in balance_sheet.index:
                return _safe_float(balance_sheet.loc[label].iloc[0])
        except Exception:
            continue
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


def _statement_date(statement: pd.DataFrame | None) -> str | None:
    if statement is None or statement.empty or len(statement.columns) == 0:
        return None
    dates = pd.to_datetime(statement.columns, errors="coerce", utc=True)
    dates = dates[~pd.isna(dates)]
    return max(dates).date().isoformat() if len(dates) else None


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


def _unix_date(value: Any) -> str | None:
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
    balance_sheet = _safe_statement(t, "balance_sheet")
    income_statement = _safe_statement(t, "financials")
    cashflow = _safe_statement(t, "cashflow")

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
        "_balance_sheet": balance_sheet,
        "_income_statement": income_statement,
        "_cashflow": cashflow,
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
    balance_date = _unix_date(info.get("mostRecentQuarter")) or _statement_date(
        balance_sheet
    )
    income_date = _statement_date(income_statement)
    cashflow_date = _statement_date(cashflow)
    observed_at_by_field = {
        field_name: observed_at
        for observed_at, fields in (
            (
                balance_date,
                (
                    "debt_to_equity", "current_ratio", "quick_ratio",
                    "total_debt", "total_cash",
                ),
            ),
            (
                income_date,
                (
                    "roe", "roa", "gross_margin", "operating_margin",
                    "ebitda_margin", "net_margin", "ebitda",
                ),
            ),
            (
                cashflow_date,
                ("free_cashflow", "operating_cashflow"),
            ),
        )
        if observed_at
        for field_name in fields
    }
    observed_at_by_field.update(
        {
            "market_cap": market_observed_at,
            "enterprise_value": market_observed_at,
        }
    )
    short_interest_date = _unix_date(info.get("dateShortInterest"))
    if short_interest_date:
        observed_at_by_field["short_float"] = short_interest_date
    not_applicable_fields: set[str] = set()
    if _trailing_pe_structurally_absent(record.get("pe"), info):
        not_applicable_fields.add("pe")
    if record.get("roe") is None:
        equity = _stockholders_equity(balance_sheet)
        if equity is not None and equity <= 0:
            # ROE undefined on negative book equity -- do NOT reconcile from a
            # secondary source (which would surface a misleading value); mark
            # not_applicable so it drops out of the confidence gate. When
            # equity > 0 the field stays `missing`, letting the Finnhub roeTTM
            # reconciliation fill a genuine value (ADR-037).
            not_applicable_fields.add("roe")
    annotated = ensure_field_evidence(
        record,
        source="Yahoo Finance",
        retrieved_at=retrieved_at,
        raw_presence=raw_presence,
        raw_values=raw_values,
        observed_at_by_category={"market": market_observed_at},
        observed_at_by_field=observed_at_by_field,
        not_applicable_fields=not_applicable_fields,
    )
    for field_name in ("free_cashflow", "ebitda"):
        evidence = annotated["field_evidence"].get(field_name)
        if isinstance(evidence, dict):
            evidence["detail"] = (
                "Yahoo provider TTM value; not directly comparable to one "
                "annual SEC filing"
            )
    return annotated


def fetch_watchlist(
    watchlist: pd.DataFrame,
    period: str = "2y",
    interval: str = "1d",
    *,
    failures: list[str] | None = None,
    provider_policy: ProviderPolicy | None = None,
    raw_snapshot_dir: str | Path | None = None,
    secondary_fetcher: Callable[..., dict[str, Any]] | None = None,
    secondary_fetchers: Iterable[Callable[..., dict[str, Any]]] = (),
    critical_fields: Iterable[str] = DEFAULT_CRITICAL_FIELDS,
) -> list[dict]:
    """
    `failures`, se informado, recebe "SYMBOL: erro" para cada fetch que
    falhou -- opcional para não quebrar chamadores existentes que só querem
    as linhas coletadas.
    """
    rows: list[dict] = []
    critical_fields = tuple(critical_fields)
    client = ProviderClient("Yahoo Finance", provider_policy)
    configured_fetchers = tuple(
        fetcher
        for fetcher in ((secondary_fetcher,) + tuple(secondary_fetchers))
        if fetcher is not None
    )
    claimed_fields: set[str] = set()
    secondary_boundaries = []
    for fetcher in configured_fetchers:
        declared = getattr(fetcher, "supported_fields", None)
        supported = tuple(
            field_name
            for field_name in critical_fields
            if field_name not in claimed_fields
            and (declared is None or field_name in declared)
        )
        if not supported:
            continue
        claimed_fields.update(supported)
        provider_name = str(
            getattr(fetcher, "provider_name", "Secondary")
        )
        secondary_boundaries.append(
            (
                fetcher,
                ProviderClient(provider_name, provider_policy),
                supported,
            )
        )
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
            reconciled = primary
            secondary_snapshots: dict[str, dict[str, str]] = {}
            secondary_errors: dict[str, dict[str, Any]] = {}
            for fetcher, secondary_client, supported in secondary_boundaries:
                provider_name = secondary_client.provider
                secondary = None
                try:
                    secondary = secondary_client.execute(
                        "fetch_symbol",
                        fetcher,
                        symbol,
                        name,
                        period=period,
                        interval=interval,
                    )
                except ProviderError as secondary_error:
                    error_payload = secondary_error.to_dict()
                    secondary_errors[provider_name] = error_payload
                    if "secondary_provider_error" not in primary:
                        primary["secondary_provider_error"] = error_payload
                else:
                    ensure_field_evidence(secondary)
                    if raw_snapshot_dir is not None:
                        secondary_receipt = store_raw_snapshot(
                            secondary,
                            raw_snapshot_dir,
                            provider=str(secondary.get("source") or "Secondary"),
                            symbol=symbol,
                            collected_at=str(
                                secondary.get("as_of") or primary["as_of"]
                            ),
                        )
                        snapshot_payload = {
                            "hash": secondary_receipt.sha256,
                            "path": str(secondary_receipt.path),
                        }
                        secondary_snapshots[provider_name] = snapshot_payload
                        if "secondary_raw_snapshot_hash" not in primary:
                            primary["secondary_raw_snapshot_hash"] = (
                                secondary_receipt.sha256
                            )
                            primary["secondary_raw_snapshot_path"] = str(
                                secondary_receipt.path
                            )
                reconciled = reconcile_critical_fields(
                    reconciled, secondary, supported
                )
            remaining_fields = tuple(
                field_name
                for field_name in critical_fields
                if field_name not in claimed_fields
            )
            if remaining_fields:
                reconciled = reconcile_critical_fields(
                    reconciled, None, remaining_fields
                )
            if secondary_snapshots:
                reconciled["secondary_raw_snapshots"] = secondary_snapshots
            if secondary_errors:
                reconciled["secondary_provider_errors"] = secondary_errors
            rows.append(reconciled)
            print(f"[OK] {symbol}")
        except Exception as exc:
            print(f"[ERRO] {symbol}: {exc}")
            if failures is not None:
                failures.append(f"{symbol}: {exc}")
    return rows

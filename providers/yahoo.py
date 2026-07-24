from __future__ import annotations

import concurrent.futures

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import yfinance as yf

from providers.contracts import ProviderClient, ProviderError, ProviderPolicy
from providers.evidence import ensure_field_evidence, reconcile_critical_fields
from storage.raw_snapshots import store_raw_snapshot


DEFAULT_CRITICAL_FIELDS = (
    # market_cap, enterprise_value and short_float are deliberately absent
    # (ADR-038): each has a native, self-consistent Yahoo value (same
    # source, same settlement date) that cross-vendor reconciliation was
    # measured to corrupt rather than confirm. market_cap/enterprise_value
    # get their own absolute plausibility/FX-correction resolution
    # (`_resolve_enterprise_value`) instead of requiring 5% agreement with a
    # thinly-covered secondary vendor (BNTX, BTI were both rejected despite
    # being correct). short_float: live-measured on JBS, Massive's own
    # short_interest matches Yahoo's exactly (33,642,565 -- both FINRA-
    # sourced, same settlement date), but Massive's free_float (527M, 67.9%
    # of shares) disagrees sharply with Yahoo's (327.6M, 42.2%) -- Massive's
    # free-float methodology overcounts closely-held shares for a company
    # with a complex dual-listing/holding structure (JBS N.V.'s Dutch
    # reorganization obscures the controlling family stake from a US-market
    # float estimate), understating short_float. Yahoo's own
    # shortPercentOfFloat is already US-market-native and internally
    # consistent by construction; a foreign issuer's listing structure
    # should not be able to corrupt a US-market short-interest reading via a
    # secondary vendor's differently-scoped float estimate. Other critical
    # fields are unaffected.
    #
    # total_debt is also deliberately absent (ADR-042): the SEC secondary
    # sums long_term_debt + long_term_debt_current + short_term_debt for the
    # single latest period any one component appears
    # (sec_companyfacts.py), so a period-misaligned or partially-tagged
    # filing yields an incomplete total. Measured live, COP came out as
    # $1.07B vs Yahoo's correct $23.3B; 26 of the real portfolio's holdings
    # (MSFT, META, GOOGL, CVX, ...) had their correct Yahoo total_debt nulled
    # by a >5% disagreement with the flaky SEC sum, silently dropping
    # net_debt_ebitda for ~48% of the book. Yahoo's totalDebt is a clean,
    # internally-consistent aggregate; it no longer needs SEC agreement.
    #
    # roe is deliberately absent too (ADR-048). It was never in this tuple but
    # was in `config/settings.json`, which overrides it. The ADR-047 freshness
    # fix exposed why that was wrong: while roe sat permanently `stale` it was
    # never reconciled at all (`reconcile_critical_fields` skips unusable
    # primaries), so the disagreement stayed invisible. Once dated correctly
    # the field became `present`, got cross-checked, and was nulled --
    # measured live: ASML Yahoo 0.5394 vs Finnhub 0.4468 (17% apart), CLF
    # -0.1386 vs -0.2091 (34%). Neither vendor is wrong: Yahoo's roe is TTM
    # net income over equity, Finnhub's uses a different period/equity base.
    # A definitional mismatch is not a data error, and 5% agreement between
    # two different definitions is unachievable by construction -- the same
    # reasoning as total_debt above and ADR-038's market_cap/short_float.
    "total_cash",
    "ebitda",
    "free_cashflow",
    "current_ratio",
)


def _safe_float(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _compute_market_cap(price: Any, shares_outstanding: Any) -> float | None:
    """``price x shares_outstanding`` -- currency-neutral by construction.

    An ADR's quote price is always denominated in the exchange's currency
    (USD here), and share count is a pure number, so this never needs FX
    conversion regardless of what currency the issuer reports financials in.
    Live-measured (ADR-038) to match Yahoo's own vendor ``marketCap`` almost
    exactly for every real holding checked (BNTX/BTI/PAM/SGML/YPF within
    rounding); this becomes the primary source of truth instead of a value
    that still depends on a vendor's own (sometimes buggy) computation.
    """
    try:
        p = float(price)
        s = float(shares_outstanding)
    except (TypeError, ValueError):
        return None
    if p <= 0 or s <= 0:
        return None
    return p * s


def _default_fx_rate_to_usd(currency: str) -> float | None:
    """Live spot rate for 1 unit of ``currency`` in USD, via Yahoo's own FX
    quote (``{CUR}USD=X``) -- no new vendor, same client already in use.
    """
    code = str(currency or "").strip().upper()
    if not code or code == "USD":
        return 1.0
    try:
        ticker = yf.Ticker(f"{code}USD=X")
        rate = _safe_float((ticker.info or {}).get("regularMarketPrice"))
        if rate is None:
            history = ticker.history(period="5d")
            if history is not None and not history.empty:
                rate = _safe_float(history["Close"].iloc[-1])
        return rate if rate and rate > 0 else None
    except Exception:
        return None


def _resolve_enterprise_value(
    *,
    market_cap: Any,
    enterprise_value_reported: Any,
    total_debt: Any,
    total_cash: Any,
    financial_currency: Any,
    quote_currency: Any,
    fx_rate_fetcher: Callable[[str], float | None],
) -> tuple[float | None, str]:
    """Resolve EV, correcting a currency-unit bug instead of just rejecting it.

    General ADR/foreign-issuer protocol (ADR-038), not a per-symbol patch:
    1. If Yahoo's own reported ``enterpriseValue`` is already plausible
       (within the ADR-037 EV/MarketCap bound), use it unchanged -- this
       keeps it consistent with Yahoo's own ``ev_to_ebitda``/``ev_to_revenue``
       ratios, which are computed from the same number and are not
       independently re-derivable here. Live-measured: BNTX (0.43x) and BTI
       (5.27x, a real leveraged-conglomerate multiple) both already pass and
       are left untouched.
    2. Only when Yahoo's own value is implausible, reconstruct
       ``market_cap + total_debt - total_cash`` as reported (no FX) and
       retest -- this is Yahoo's own definition, just recomputed from raw
       inputs instead of trusting a possibly-stale precomputed field.
    3. If that reconstruction is still implausible AND the issuer's
       ``financialCurrency`` differs from the quote currency, convert
       debt/cash at the live spot rate and retest. Live-measured on YPF: raw
       ARS-labeled-as-USD debt gives EV/MarketCap=639x either way; converted
       at the real ARS->USD rate it becomes 1.42x (plausible) -- confirms a
       genuine currency-unit bug, not merely a large company.
    4. If still implausible after FX correction, there is no unit bug to fix
       -- something else is wrong, so it stays unresolved and the caller
       nulls it out (along with ev_to_ebitda/ev_to_revenue, which were
       always computed against the rejected number in every branch except
       the first).
    """
    try:
        cap = float(market_cap)
    except (TypeError, ValueError):
        return None, "missing_market_cap"

    if not _enterprise_value_implausible(cap, enterprise_value_reported):
        try:
            return float(enterprise_value_reported), "direct_vendor"
        except (TypeError, ValueError):
            return None, "missing_inputs"

    try:
        debt = float(total_debt)
        cash = float(total_cash)
    except (TypeError, ValueError):
        return None, "missing_inputs"

    naive_ev = cap + debt - cash
    if not _enterprise_value_implausible(cap, naive_ev):
        return naive_ev, "reconstructed"

    fin_currency = str(financial_currency or "").strip().upper()
    quote = str(quote_currency or "").strip().upper()
    if not fin_currency or fin_currency == quote:
        return None, "implausible_same_currency"

    rate = fx_rate_fetcher(fin_currency)
    if rate is None:
        return None, "fx_rate_unavailable"

    converted_ev = cap + (debt * rate) - (cash * rate)
    if _enterprise_value_implausible(cap, converted_ev):
        return None, "implausible_after_fx_correction"
    return converted_ev, f"fx_corrected:{fin_currency}->{quote}@{rate:.6g}"


def _derive_ev_ebitda(enterprise_value: Any, ebitda: Any) -> float | None:
    """``enterprise_value / ebitda`` -- mirrors how ``analytics/mapper.py``
    already derives ``ev_ebit`` from ``enterprise_value``/``ebit`` (ADR-038).

    Used only when Yahoo's own ``enterpriseToEbitda`` ratio was nulled
    because ``enterprise_value`` needed reconstruction/FX-correction (the
    vendor ratio would otherwise disagree with the resolved EV). Must be
    derived at this layer, not downstream in the mapper, because the
    required-feature confidence gate reads ``field_evidence`` status, not
    the raw numeric column -- a value filled in later without updating
    evidence here would be silently ignored by the gate.
    """
    try:
        ev_value = float(enterprise_value)
        ebitda_value = float(ebitda)
    except (TypeError, ValueError):
        return None
    if ebitda_value == 0:
        return None
    return ev_value / ebitda_value


def _enterprise_value_implausible(market_cap: Any, enterprise_value: Any) -> bool:
    """Whether Yahoo's own ``enterpriseValue`` is an order-of-magnitude data
    error rather than a genuine (if extreme) valuation.

    Measured live across this portfolio's real holdings: Yahoo's EV for a
    healthy company stays within a modest multiple of market cap even under
    heavy leverage (BTI 5.4x, FMC 4.0x) or a large net-cash position (BRK-B
    -0.25x) -- but two names came back wildly outside any plausible range:
    ASML showed `enterpriseToEbitda=2750x` (real EBITDA $13.5B against a
    reported EV of $37.1 trillion vs. an actual market cap of $692B) and YPF
    showed EV of $12.87 trillion against a $20B market cap (639x) --
    consistent with an FX-conversion bug in Yahoo's feed for names with a
    foreign reporting/functional currency, not a real valuation. The bound
    below is set far outside the portfolio's own observed legitimate range so
    it only rejects orders-of-magnitude vendor errors, never a real distressed
    or cash-rich company.
    """
    try:
        cap = float(market_cap)
        value = float(enterprise_value)
    except (TypeError, ValueError):
        return False
    if cap <= 0:
        return False
    ratio = value / cap
    return ratio > 20.0 or ratio < -5.0


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


def _cash_and_equivalents(
    quarterly_balance_sheet: "pd.DataFrame | None",
    balance_sheet: "pd.DataFrame | None" = None,
) -> float | None:
    """Strict GAAP cash and cash equivalents from the balance sheet.

    ``info.get("totalCash")`` is NOT this concept -- live-measured on BRK-B
    (ADR-038 adendo): Yahoo's own balance sheet has two distinct rows, "Cash
    And Cash Equivalents" and the broader "Cash Cash Equivalents And Short
    Term Investments" (close to `info.totalCash`, since it folds in
    short-term investments -- T-bills, for an insurer like Berkshire). This
    caused a real, general modeling bug, not a BRK-B quirk: it inflated
    `total_cash` for any company holding a large liquidity buffer, which
    understates `net_debt`/`net_debt_ebitda` and overstates `enterprise_value`
    corrections. The "Cash And Cash Equivalents" label is present for every
    real holding checked (MSFT, JNJ, LMT, ASML, JBS, PAM, BRK-B).

    Reads the quarterly statement first, not the annual one: live-measured
    on the same BRK-B fix, the annual balance sheet's most recent column
    (FY2025) was a full quarter stale against `info["mostRecentQuarter"]`
    (Q1 2026) -- $51.9B (FY2025) vs $58.1B (Q1 2026, matching SEC EDGAR's
    own $58.8B to within 1.2%). Atlas stamps this field's evidence with
    `mostRecentQuarter` regardless of which statement actually supplied the
    value, so reading the annual statement was quietly mislabeling a
    quarter-old number as current -- a second, real Berkshire cash position
    change (not a vendor error) got misclassified as "critical sources
    disagree" purely from that timestamp mismatch. Falls back to the annual
    statement only when no quarterly one is available.
    """
    for statement in (quarterly_balance_sheet, balance_sheet):
        if statement is None:
            continue
        for label in (
            "Cash And Cash Equivalents",
            "Cash Equivalents",
            "Cash Financial",
        ):
            try:
                if label in statement.index:
                    return _safe_float(statement.loc[label].iloc[0])
            except Exception:
                continue
    return None


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


def _period_ends(*statements: "pd.DataFrame | None") -> list[pd.Timestamp]:
    """Datas de fim de período presentes nas demonstrações, ordenadas."""
    collected: list[pd.Timestamp] = []
    for statement in statements:
        if statement is None or statement.empty or len(statement.columns) == 0:
            continue
        dates = pd.to_datetime(statement.columns, errors="coerce", utc=True)
        collected.extend(date for date in dates if not pd.isna(date))
    return sorted(set(collected))


def _reporting_period_days(*statements: "pd.DataFrame | None") -> int | None:
    """Intervalo típico entre períodos consecutivos do próprio emissor.

    Deriva a cadência de divulgação em vez de assumir trimestre: emissores
    do Reino Unido e boa parte da Europa reportam semestralmente (BTI, ~182
    dias), enquanto o padrão americano é trimestral (~91). Sem isso, uma
    constante trimestral marca um semestral como defasado durante metade do
    ciclo dele -- que é exatamente o falso positivo que esta função existe
    para evitar.
    """
    period_ends = _period_ends(*statements)
    if len(period_ends) < 2:
        return None
    gaps = [
        (later - earlier).days
        for earlier, later in zip(period_ends, period_ends[1:])
        if (later - earlier).days > 0
    ]
    if not gaps:
        return None
    return int(pd.Series(gaps).median())


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


def fetch_symbol(
    symbol: str,
    name_hint: str = "",
    period: str = "2y",
    interval: str = "1d",
    *,
    fx_rate_fetcher: Callable[[str], float | None] = _default_fx_rate_to_usd,
) -> dict:
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
    quarterly_balance_sheet = _safe_statement(t, "quarterly_balance_sheet")
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
        "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
        "financial_currency": info.get("financialCurrency"),
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
        "shares_outstanding": ("sharesOutstanding",),
        "financial_currency": ("financialCurrency",),
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
    # Os valores de fluxo abaixo vêm de `info` (defaultKeyStatistics /
    # financialData), que o Yahoo publica em base *trailing twelve months* --
    # verificado contra o quadro anual: MSFT trazia ebitda=184.5bi no `info`
    # contra 160.2bi no exercício FY2025 encerrado em 30/06/2025. Datá-los
    # pelo fim do exercício anual (o que se fazia aqui) carimba um número que
    # cobre até o último trimestre com uma data de até 12 meses atrás, e o
    # motor de frescor então os marcava como defasados sem que houvesse nada
    # mais recente a coletar. O fim de período correto de um TTM é o último
    # trimestre fechado.
    # `balance_date` já é `mostRecentQuarter`, que vem dentro de `info` -- não
    # custa requisição nova. Medido contra `quarterly_financials` em 4
    # emissores: idêntico em MSFT/AVAV, 2 dias de diferença em JNJ (calendário
    # 52/53 semanas), e mais robusto em BTI, onde o quadro trimestral de
    # resultado voltou vazio. Dois dias são ruído para uma regra medida em
    # meses, e buscar os quadros trimestrais de resultado/caixa custaria +2
    # requisições por símbolo -- 33% a mais sobre as 6 que a ADR-046 usou para
    # dimensionar a paralelização, com a coleta ampla já limitada pelo teto de
    # 2 req/s.
    ttm_period_end = balance_date or _statement_date(income_statement)
    ttm_cashflow_period_end = balance_date or _statement_date(cashflow)
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
                ttm_period_end,
                (
                    "roe", "roa", "gross_margin", "operating_margin",
                    "ebitda_margin", "net_margin", "ebitda",
                ),
            ),
            (
                ttm_cashflow_period_end,
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
    # Cadência de divulgação do próprio emissor, para a política de frescor
    # decidir quando o período seguinte já deveria ter saído. Prefixo `_`
    # mantém o campo fora de `field_evidence` (não é um dado observado).
    # `quarterly_balance_sheet` já era buscado antes desta mudança, e sozinho
    # mede a cadência tão bem quanto os três quadros juntos (verificado:
    # BTI 182d, MSFT 91d, AVAV 92d, JNJ 91d -- idêntico nos dois caminhos).
    reporting_period_days = _reporting_period_days(quarterly_balance_sheet)
    if reporting_period_days:
        record["_reporting_period_days"] = reporting_period_days
    short_interest_date = _unix_date(info.get("dateShortInterest"))
    if short_interest_date:
        observed_at_by_field["short_float"] = short_interest_date
    strict_cash = _cash_and_equivalents(quarterly_balance_sheet, balance_sheet)
    if strict_cash is not None:
        # info.get("totalCash") is not "cash" -- it silently folds in
        # short-term investments for companies with a large liquidity
        # buffer (ADR-038 adendo, live-measured on BRK-B). The strict
        # balance-sheet row is the canonical definition for every symbol,
        # not just the one that first exposed the bug.
        record["total_cash"] = strict_cash
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
    # market_cap: currency-neutral by construction (ADR-038), replaces
    # trusting a vendor's own computation whenever price+shares are both
    # available. Falls back to Yahoo's own marketCap only when shares are
    # missing (rare for an actively quoted symbol).
    computed_market_cap = _compute_market_cap(
        record.get("price"), record.get("shares_outstanding")
    )
    if computed_market_cap is not None:
        record["market_cap"] = computed_market_cap
    resolved_ev, ev_provenance = _resolve_enterprise_value(
        market_cap=record.get("market_cap"),
        enterprise_value_reported=record.get("enterprise_value"),
        total_debt=record.get("total_debt"),
        total_cash=record.get("total_cash"),
        financial_currency=record.get("financial_currency"),
        quote_currency=record.get("currency"),
        fx_rate_fetcher=fx_rate_fetcher,
    )
    record["enterprise_value"] = resolved_ev
    if ev_provenance != "direct_vendor":
        # ev_to_ebitda/ev_to_revenue are Yahoo's own precomputed ratios,
        # built from its own (rejected or corrected) enterpriseValue -- they
        # would now disagree with the resolved `enterprise_value`, so they
        # cannot be trusted as-is. ev_ebit is unaffected: it is derived
        # downstream by analytics/mapper.py directly from
        # `enterprise_value` and inherits whichever resolution happened
        # here automatically. ev_to_ebitda gets the same treatment here
        # (not in mapper.py, so the re-derived value and its field_evidence
        # status stay consistent -- the confidence gate reads evidence
        # status, not the raw column, so deriving the number downstream
        # without updating evidence here would silently be ignored) because
        # it is a heavily weighted valuation feature (config/features.yaml,
        # weight 0.30 since ADR-037) and a real ebitda value is often
        # already available; ev_to_revenue has no scored feature depending
        # on it, so it is left null rather than adding an unused derivation.
        record["ev_to_revenue"] = None
        record["ev_to_ebitda"] = _derive_ev_ebitda(resolved_ev, record.get("ebitda"))
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
    market_cap_evidence = annotated["field_evidence"].get("market_cap")
    if computed_market_cap is not None and isinstance(market_cap_evidence, dict):
        market_cap_evidence["detail"] = (
            "Computed as price x shares_outstanding, currency-neutral by "
            "construction (ADR-038); vendor marketCap kept only in raw evidence"
        )
    ev_details = {
        "direct_vendor": None,
        "reconstructed": (
            "EV reconstructed as market_cap+total_debt-total_cash: Yahoo's "
            "own reported enterpriseValue was implausible (ADR-038)"
        ),
        "implausible_same_currency": (
            "Rejected: EV/MarketCap ratio implausible and financialCurrency "
            "matches quote currency, so no FX correction applies (ADR-038)"
        ),
        "fx_rate_unavailable": (
            "Rejected: EV/MarketCap ratio implausible and the live FX rate "
            "needed to correct it could not be fetched (ADR-038)"
        ),
        "implausible_after_fx_correction": (
            "Rejected: EV/MarketCap ratio stayed implausible even after "
            "FX-correcting debt/cash -- not a currency-unit bug (ADR-038)"
        ),
        "missing_inputs": "Rejected: total_debt/total_cash unavailable to resolve EV",
        "missing_market_cap": "Rejected: market_cap unavailable to resolve EV",
    }
    if ev_provenance.startswith("fx_corrected:"):
        detail = (
            f"EV FX-corrected ({ev_provenance.split(':', 1)[1]}): Yahoo's "
            "raw debt/cash were in the issuer's reporting currency, not the "
            "quote currency (ADR-038)"
        )
    else:
        detail = ev_details.get(ev_provenance)
    if detail:
        for field_name in ("enterprise_value", "ev_to_revenue"):
            evidence = annotated["field_evidence"].get(field_name)
            if isinstance(evidence, dict):
                evidence["detail"] = detail
        ev_ebitda_evidence = annotated["field_evidence"].get("ev_to_ebitda")
        if isinstance(ev_ebitda_evidence, dict):
            if record.get("ev_to_ebitda") is not None:
                ev_ebitda_evidence["detail"] = (
                    "Re-derived as resolved enterprise_value/ebitda instead "
                    "of using Yahoo's own ratio, which was computed against "
                    "the rejected enterpriseValue (ADR-038)"
                )
            else:
                ev_ebitda_evidence["detail"] = detail
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
    max_workers: int = 1,
) -> list[dict]:
    """
    `failures`, se informado, recebe "SYMBOL: erro" para cada fetch que
    falhou -- opcional para não quebrar chamadores existentes que só querem
    as linhas coletadas.

    `max_workers` > 1 coleta símbolos em paralelo. O ganho é de latência, não
    de vazão permitida: o rate limit continua global, porque as threads
    compartilham o mesmo `ProviderClient` e ele serializa a espera sob lock.
    Cada símbolo custa ~6 requisições HTTP sequenciais ao Yahoo, e é essa
    latência (medida em ~3,9 s/símbolo) que o paralelismo sobrepõe. Default 1
    preserva o comportamento sequencial de quem chama sem o parâmetro.
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
    def collect_one(symbol: str, name: str) -> dict:
        """Coleta um símbolo. Corpo antes inline no laço, agora reentrante.

        Só usa estado compartilhado imutável (`client`, `secondary_boundaries`)
        e cria o resto localmente, então roda igual em thread única ou em
        paralelo. O `ProviderClient` serializa o rate limit internamente
        (`threading.Lock`), de modo que o teto global de chamadas/segundo vale
        para o conjunto das threads, não por thread.
        """
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
        return reconciled

    entries: list[tuple[str, str]] = []
    for _, row in watchlist.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        entries.append((symbol, str(row.get("name", "")).strip()))

    collected: dict[int, dict] = {}
    errors: dict[int, str] = {}

    def run(index: int, symbol: str, name: str) -> None:
        try:
            collected[index] = collect_one(symbol, name)
            print(f"[OK] {symbol}")
        except Exception as exc:
            print(f"[ERRO] {symbol}: {exc}")
            errors[index] = f"{symbol}: {exc}"

    workers = max(1, int(max_workers or 1))
    if workers > 1 and len(entries) > 1:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="atlas-collect"
        ) as pool:
            list(
                pool.map(
                    lambda item: run(*item),
                    [(i, s, n) for i, (s, n) in enumerate(entries)],
                )
            )
    else:
        for index, (symbol, name) in enumerate(entries):
            run(index, symbol, name)

    # Ordem de saida determinística: nao depende de qual thread terminou antes,
    # entao duas execucoes com os mesmos dados produzem o mesmo resultado.
    for index in range(len(entries)):
        if index in collected:
            rows.append(collected[index])
    if failures is not None:
        for index in range(len(entries)):
            if index in errors:
                failures.append(errors[index])
    return rows

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

from providers.evidence import DataValueStatus, FieldEvidence


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _dates_within_days(
    left: str | None,
    right: str | None,
    tolerance_days: int,
) -> bool:
    if not left or not right:
        return False
    try:
        difference = date.fromisoformat(str(left)[:10]) - date.fromisoformat(
            str(right)[:10]
        )
        return abs(difference.days) <= tolerance_days
    except ValueError:
        return False


def compose_market_cap(
    symbol: str,
    *,
    grouped_daily_row: Mapping[str, Any] | None,
    shares_outstanding: float | None,
    shares_observed_at: str | None,
    shares_alignment_days: int,
) -> dict[str, Any]:
    """market_cap = Grouped Daily close x SEC shares_outstanding.

    Neither component is invented when absent, and the two are only
    composed when their dates are within `shares_alignment_days` of each
    other. Unlike debt/cash (which can move materially within a quarter,
    so EV composition elsewhere uses a tight 45-day window), share count
    only changes via deliberate buybacks/issuance and is reported
    quarterly -- a much wider window is the correct judgment here, not a
    copy of the 45-day EV convention (see ADR-031/033).

    Default 140 days, not 100: measured against the real 2026-07-18 broad
    run, 300/2,429 symbols fell outside a 100-day window, but 142 of those
    were only 101-130 days old -- consistent with SEC's own worst-case
    quarterly filing cadence for a non-accelerated filer (10-Q due up to
    45 days after quarter-end, ~91 days between quarters -> up to ~136
    days between two consecutive on-time filings). 140 days covers that
    real cadence with a small margin. It does not paper over genuinely
    stale data: 119 of the 300 were 365+ days old (one over 6,000 days),
    which is dead/shell-company territory, not a filing-cadence question,
    and stays excluded regardless of the window.
    """
    normalized = str(symbol).strip().upper()
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    close = _number((grouped_daily_row or {}).get("close"))
    price_date = (grouped_daily_row or {}).get("trade_date")
    shares = _number(shares_outstanding)

    status = "composed"
    detail = "Massive Grouped Daily close x SEC shares_outstanding"
    market_cap: float | None = None
    if close is None:
        status = "price_unavailable"
        detail = "no Grouped Daily close for this symbol/date"
    elif shares is None:
        status = "shares_unavailable"
        detail = "no SEC shares_outstanding for this symbol"
    elif not _dates_within_days(price_date, shares_observed_at, shares_alignment_days):
        status = "shares_stale"
        detail = (
            f"SEC shares_outstanding observed_at={shares_observed_at or 'unavailable'} "
            f"outside {shares_alignment_days}-day window of price_date={price_date or 'unavailable'}"
        )
    else:
        market_cap = close * shares

    return {
        "symbol": normalized,
        "source": "Massive Grouped Daily + SEC EDGAR Company Facts",
        "as_of": retrieved_at,
        "status": status,
        "market_cap": market_cap,
        "price": close,
        "price_date": price_date,
        "shares_outstanding": shares,
        "shares_observed_at": shares_observed_at,
        "field_evidence": {
            "market_cap": FieldEvidence(
                status=(
                    DataValueStatus.PRESENT
                    if market_cap is not None
                    else DataValueStatus.UNAVAILABLE
                ),
                source="Massive Grouped Daily + SEC EDGAR Company Facts",
                category="fundamentals",
                retrieved_at=retrieved_at,
                observed_at=price_date,
                available_at=retrieved_at,
                detail=detail,
            ).to_dict()
        },
    }

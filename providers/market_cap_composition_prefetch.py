from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Sequence

from providers.contracts import ProviderClient, ProviderError, ProviderPolicy
from providers.market_cap_composition import compose_market_cap
from providers.massive_cache import MassiveGroupedDailyCache
from providers.massive_prefetch import _atomic_write
from providers.prefetch_symbols import load_symbols
from providers.sec_companyfacts import build_sec_secondary_provider
from providers.sec_shares_cache import SecSharesCache


ROOT = Path(__file__).resolve().parents[1]


def _latest_cached_trade_date(cache: MassiveGroupedDailyCache) -> str | None:
    dates = cache.load().get("dates") or {}
    return max(dates.keys(), default=None)


def _fetch_shares(
    symbol: str,
    provider: Any,
    cache: SecSharesCache | None,
    client: ProviderClient,
    *,
    max_age_days: float,
) -> tuple[float | None, str | None, str | None]:
    """Returns (shares_outstanding, observed_at, error_message)."""
    cached = cache.get(symbol, max_age_days=max_age_days) if cache else None
    if cached is not None:
        return cached.get("shares_outstanding"), cached.get("observed_at"), None
    try:
        record = client.execute("shares_outstanding", provider, symbol)
    except ProviderError as exc:
        return None, None, exc.kind.value
    shares = record.get("shares_outstanding")
    evidence = (record.get("field_evidence") or {}).get("shares_outstanding") or {}
    observed_at = evidence.get("observed_at")
    if cache is not None:
        cache.put(symbol, {"shares_outstanding": shares, "observed_at": observed_at})
    return shares, observed_at, None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compõe market_cap amplo (Massive Grouped Daily x SEC "
            "shares_outstanding) contra o universo elegível."
        )
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--symbols")
    parser.add_argument(
        "--date",
        help="Trade date do Grouped Daily a usar (default: mais recente em cache).",
    )
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument("--limit", type=int)
    limits.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    symbols_path = Path(
        args.symbols
        or settings.get(
            "massive_prefetch_universe_path",
            "output/dados/research_universe_report_market.json",
        )
    )
    if not symbols_path.is_absolute():
        symbols_path = ROOT / symbols_path
    symbols = sorted(
        {str(symbol).strip().upper() for symbol in load_symbols(symbols_path) if str(symbol).strip()}
    )

    grouped_daily_cache = MassiveGroupedDailyCache(
        ROOT
        / str(
            settings.get(
                "massive_grouped_daily_cache_path",
                "data/provider_cache/massive_grouped_daily.json",
            )
        )
    )
    trade_date = args.date or _latest_cached_trade_date(grouped_daily_cache)
    if trade_date is None:
        raise RuntimeError(
            "Nenhum snapshot Grouped Daily em cache -- rode "
            "providers.massive_grouped_daily_prefetch primeiro."
        )
    price_records = grouped_daily_cache.get_date(trade_date) or {}

    sec_provider = build_sec_secondary_provider(ROOT, settings)
    if sec_provider is None:
        raise RuntimeError(
            "SEC está desabilitada ou sec_user_agent não foi configurado."
        )
    sec_cache = SecSharesCache(
        ROOT
        / str(
            settings.get(
                "sec_shares_cache_path", "data/provider_cache/sec_shares.json"
            )
        )
    )
    sec_cache_days = float(settings.get("sec_shares_cache_days", 30))
    client = ProviderClient(
        "SEC EDGAR Company Facts",
        ProviderPolicy(
            timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
            max_retries=int(settings.get("provider_max_retries", 2)),
            backoff_seconds=float(settings.get("provider_backoff_seconds", 0.5)),
            rate_limit_per_second=float(
                settings.get("sec_public_float_rate_limit_per_second", 2)
            ),
        ),
    )
    alignment_days = int(
        settings.get("market_cap_composition_shares_alignment_days", 100)
    )

    max_symbols = None if args.all else args.limit if args.limit is not None else int(
        settings.get("market_cap_composition_batch_size", 100)
    )
    requested_this_run = 0
    fetch_errors: list[dict[str, str]] = []
    composed: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        cached_shares = sec_cache.get(symbol, max_age_days=sec_cache_days)
        if cached_shares is None:
            if max_symbols is not None and requested_this_run >= max_symbols:
                continue
            requested_this_run += 1
        shares, observed_at, error = _fetch_shares(
            symbol,
            sec_provider,
            sec_cache,
            client,
            max_age_days=sec_cache_days,
        )
        if error is not None:
            fetch_errors.append({"symbol": symbol, "error": error})
        composed[symbol] = compose_market_cap(
            symbol,
            grouped_daily_row=price_records.get(symbol)
            or price_records.get(symbol.replace("-", ".")),
            shares_outstanding=shares,
            shares_observed_at=observed_at,
            shares_alignment_days=alignment_days,
        )

    status_counts = Counter(row["status"] for row in composed.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_universe": settings.get(
            "scoring_reference_universe_id", "US_MARKET_ELIGIBLE"
        ),
        "trade_date": trade_date,
        "alignment_days": alignment_days,
        "requested": len(symbols),
        "requested_this_run": requested_this_run,
        "composed": status_counts.get("composed", 0),
        "coverage_pct": (
            round(100 * status_counts.get("composed", 0) / len(symbols), 2)
            if symbols
            else 0.0
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "fetch_error_count": len(fetch_errors),
        "fetch_errors": fetch_errors[:20],
    }
    report_path = ROOT / str(
        settings.get(
            "market_cap_composition_report_path",
            "output/dados/market_cap_composition_coverage.json",
        )
    )
    _atomic_write(report, report_path)
    snapshot_path = ROOT / str(
        settings.get(
            "market_cap_composition_snapshot_path",
            "output/dados/market_cap_composition.json",
        )
    )
    _atomic_write(
        {
            "generated_at": report["generated_at"],
            "trade_date": trade_date,
            "records": composed,
        },
        snapshot_path,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

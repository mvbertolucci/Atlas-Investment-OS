from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from providers.finnhub import build_finnhub_secondary_provider
from providers.massive_prefetch import _atomic_write
from providers.prefetch_symbols import load_symbols


ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preenche de forma retomável o cache Finnhub Basic Financials "
            "(market cap + enterprise value) e reporta cobertura."
        )
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--symbols")
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
            "finnhub_prefetch_universe_path",
            "output/dados/research_universe_report_market.json",
        )
    )
    if not symbols_path.is_absolute():
        symbols_path = ROOT / symbols_path
    symbols = load_symbols(symbols_path)
    provider = build_finnhub_secondary_provider(ROOT, settings)
    if provider is None:
        raise RuntimeError(
            "Finnhub está desabilitada ou finnhub_api_key não foi configurada."
        )
    max_symbols = (
        None
        if args.all
        else args.limit
        if args.limit is not None
        else int(settings.get("finnhub_prefetch_batch_size", 55))
    )
    normalized = sorted(
        {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    )
    requested = 0
    errors: list[dict[str, Any]] = []
    for symbol in normalized:
        cached = (
            provider.cache.get(symbol, max_age_days=provider.cache_days)
            if provider.cache is not None
            else None
        )
        if cached is not None:
            continue
        if max_symbols is not None and requested >= max_symbols:
            break
        requested += 1
        try:
            provider(symbol)
        except Exception as exc:  # noqa: BLE001 -- record and continue the batch
            errors.append({"symbol": symbol, "error": str(exc)})

    def available(symbol: str) -> bool:
        cached = (
            provider.cache.get(symbol, max_age_days=provider.cache_days)
            if provider.cache is not None
            else None
        )
        metric: Mapping[str, Any] = (
            (cached or {}).get("metric") or {} if cached else {}
        )
        return metric.get("marketCapitalization") is not None

    cached_count = sum(
        1
        for symbol in normalized
        if provider.cache is not None
        and provider.cache.get(symbol, max_age_days=provider.cache_days)
        is not None
    )
    available_count = sum(1 for symbol in normalized if available(symbol))
    source_payload = (
        json.loads(symbols_path.read_text(encoding="utf-8"))
        if symbols_path.suffix.casefold() == ".json"
        else {}
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_universe": settings.get(
            "scoring_reference_universe_id", "US_MARKET_ELIGIBLE"
        ),
        "reference_date": str(source_payload.get("generated_at") or "")[:10]
        or None,
        "requested_this_run": requested,
        "cached": cached_count,
        "available": available_count,
        "missing": len(normalized) - available_count,
        "coverage_pct": (
            round(100 * available_count / len(normalized), 2)
            if normalized
            else 0.0
        ),
        "remaining": len(normalized) - cached_count,
        "error_count": len(errors),
        "errors": errors[:20],
    }
    report_path = Path(
        str(
            settings.get(
                "finnhub_coverage_report_path",
                "output/dados/finnhub_coverage.json",
            )
        )
    )
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    _atomic_write(report, report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

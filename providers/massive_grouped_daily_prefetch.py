from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Sequence

from providers.massive import build_massive_secondary_provider
from providers.massive_prefetch import _atomic_write
from providers.prefetch_symbols import load_symbols


ROOT = Path(__file__).resolve().parents[1]


def _default_trade_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Busca o snapshot Massive Grouped Daily de uma data e reporta "
            "cobertura contra o universo elegível."
        )
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--symbols")
    parser.add_argument(
        "--date",
        help="Data pregão AAAA-MM-DD (default: ontem UTC).",
    )
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
    symbols = load_symbols(symbols_path)
    provider = build_massive_secondary_provider(ROOT, settings)
    if provider is None:
        raise RuntimeError(
            "Massive está desabilitada ou massive_api_key não foi configurada."
        )
    trade_date = args.date or _default_trade_date()
    date.fromisoformat(trade_date)

    records = provider.fetch_grouped_daily(trade_date)
    normalized_symbols = sorted(
        {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    )
    matched = [
        symbol
        for symbol in normalized_symbols
        if symbol in records or symbol.replace("-", ".") in records
    ]
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
        "trade_date": trade_date,
        "market_record_count": len(records),
        "requested": len(normalized_symbols),
        "matched": len(matched),
        "missing": len(normalized_symbols) - len(matched),
        "coverage_pct": (
            round(100 * len(matched) / len(normalized_symbols), 2)
            if normalized_symbols
            else 0.0
        ),
    }
    report_path = Path(
        str(
            settings.get(
                "massive_grouped_daily_coverage_report_path",
                "output/dados/massive_grouped_daily_coverage.json",
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

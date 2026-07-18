from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from providers.massive import build_massive_secondary_provider
from providers.prefetch_symbols import load_symbols


ROOT = Path(__file__).resolve().parents[1]


def _atomic_write(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preenche de forma retomável o cache Massive Ticker Details."
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
    max_symbols = (
        None
        if args.all
        else args.limit
        if args.limit is not None
        else int(settings.get("massive_prefetch_batch_size", 25))
    )
    summary = provider.prefetch_ticker_details(
        symbols, max_symbols=max_symbols
    )
    source_payload = (
        json.loads(symbols_path.read_text(encoding="utf-8"))
        if symbols_path.suffix.casefold() == ".json"
        else {}
    )
    source_date = (
        str(source_payload.get("generated_at") or "")[:10]
        if isinstance(source_payload, dict)
        else ""
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference_universe": settings.get(
            "scoring_reference_universe_id", "US_MARKET_ELIGIBLE"
        ),
        "reference_date": source_date or None,
        **summary,
    }
    report_path = Path(
        str(
            settings.get(
                "massive_coverage_report_path",
                "output/dados/massive_ticker_details_coverage.json",
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

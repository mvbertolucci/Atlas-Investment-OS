from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from providers.fmp import build_fmp_secondary_provider
from providers.prefetch_symbols import load_symbols


ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preenche o cache FMP dentro da quota gratuita diária."
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--symbols")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    symbols_path = args.symbols or settings.get(
        "fmp_prefetch_universe_path",
        "output/dados/research_universe_report_market.json",
    )
    symbols_path = Path(symbols_path)
    if not symbols_path.is_absolute():
        symbols_path = ROOT / symbols_path
    symbols = load_symbols(symbols_path)
    provider = build_fmp_secondary_provider(ROOT, settings)
    if provider is None:
        raise RuntimeError(
            "FMP está desabilitada ou fmp_api_key não foi configurada."
        )
    summary = provider.prefetch(symbols)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

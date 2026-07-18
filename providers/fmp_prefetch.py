from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence

from providers.fmp import build_fmp_secondary_provider


ROOT = Path(__file__).resolve().parents[1]


def load_symbols(path: str | Path) -> list[str]:
    source = Path(path)
    if source.suffix.casefold() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        members = payload.get("members") if isinstance(payload, dict) else None
        if not isinstance(members, list):
            raise ValueError("FMP prefetch exige JSON com lista members.")
        return sorted(
            {
                str(member.get("symbol") or "").strip().upper()
                for member in members
                if isinstance(member, dict)
                and member.get("eligible") is True
                and str(member.get("symbol") or "").strip()
            }
        )
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames:
            raise ValueError("FMP prefetch exige CSV com cabeçalho symbol.")
        symbol_field = next(
            (
                field
                for field in rows.fieldnames
                if str(field).strip().casefold() == "symbol"
            ),
            None,
        )
        if symbol_field is None:
            raise ValueError("FMP prefetch exige coluna symbol.")
        return sorted(
            {
                str(row.get(symbol_field) or "").strip().upper()
                for row in rows
                if str(row.get(symbol_field) or "").strip()
            }
        )


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

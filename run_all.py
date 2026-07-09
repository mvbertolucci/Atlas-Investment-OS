from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from providers.yahoo import fetch_watchlist
from analytics.indicators import enrich_technicals
from analytics.mapper import normalize_columns
from analytics.validator import add_confidence_score
from scoring.investment import score_dataframe
from reports.excel import write_latest_and_history

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"


def print_columns(title: str, df: pd.DataFrame) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    for col in sorted(df.columns.tolist()):
        print(col)


def main() -> None:
    settings = json.loads((CONFIG / "settings.json").read_text(encoding="utf-8"))
    watchlist_path = ROOT / settings.get("watchlist_path", "config/watchlist.csv")
    watchlist = pd.read_csv(watchlist_path)

    print("=" * 70)
    print("ATLAS – INVESTMENT DECISION OS")
    print("=" * 70)
    print(f"Watchlist: {watchlist_path}")

    rows = fetch_watchlist(
        watchlist,
        period=settings.get("history_period", "1y"),
        interval=settings.get("history_interval", "1d"),
    )

    enriched = [enrich_technicals(r) for r in rows]

    df = pd.DataFrame([
        {k: v for k, v in r.items() if k != "history"}
        for r in enriched
    ])

    if df.empty:
        raise RuntimeError("Nenhum dado foi coletado. Verifique a watchlist ou a conexão.")

    print_columns("COLUNAS APÓS COLETA", df)

    df = normalize_columns(df)
    print_columns("COLUNAS APÓS NORMALIZAÇÃO", df)

    df = add_confidence_score(df)
    print_columns("COLUNAS APÓS CONFIDENCE", df)

    df = score_dataframe(
        df,
        CONFIG / "weights.json",
        CONFIG / "deal_breakers.json",
    )
    print_columns("COLUNAS APÓS SCORE", df)

    history_file, latest_file = write_latest_and_history(df, OUTPUT)

    cols = [
        "symbol",
        "Investment Score",
        "Business Score",
        "Valuation Score",
        "Financial Score",
        "Timing Score",
        "Confidence Score",
        "Recommendation",
    ]

    print()
    print(df[[c for c in cols if c in df.columns]].head(20))
    print()
    print(f"Histórico salvo em: {history_file}")

    if latest_file:
        print(f"Latest atualizado em: {latest_file}")

    print("Concluído.")


if __name__ == "__main__":
    main()
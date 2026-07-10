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
from reports.change_report import write_change_report
from database.repository import AtlasRepository

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"


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
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "history"} for r in enriched])

    if df.empty:
        raise RuntimeError("Nenhum dado foi coletado. Verifique a watchlist ou a conexão.")

    df = normalize_columns(df)
    df = add_confidence_score(df)
    df = score_dataframe(df, CONFIG / "weights.json", CONFIG / "deal_breakers.json")

    repo = AtlasRepository(version=settings.get("atlas_version", "Atlas Core 0.1"))
    run_id = repo.start_run(symbols_processed=len(df))
    repo.save_companies(df)
    repo.save_snapshots(run_id, df)
    repo.save_scores(run_id, df)
    changes = repo.compare_with_previous(run_id)
    change_report_file = write_change_report(changes, OUTPUT)
    repo.finish_run(run_id)

    history_file, latest_file = write_latest_and_history(df, OUTPUT)

    cols = ["symbol", "Investment Score", "Business Score", "Valuation Score", "Financial Score", "Timing Score", "Confidence Score", "Recommendation"]
    print()
    print(df[[c for c in cols if c in df.columns]].head(20))
    print()
    print(f"Run ID salvo no banco: {run_id}")
    print(f"Banco SQLite: {ROOT / 'database' / 'atlas.db'}")
    print(f"Relatório de mudanças: {change_report_file}")
    print(f"Histórico salvo em: {history_file}")
    if latest_file:
        print(f"Latest atualizado em: {latest_file}")
    print("Concluído.")


if __name__ == "__main__":
    main()

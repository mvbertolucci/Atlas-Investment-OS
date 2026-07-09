from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from analytics.indicators import enrich_technicals
from analytics.mapper import normalize_columns
from analytics.validator import add_confidence_score
from providers.yahoo import fetch_watchlist
from reports.excel import write_latest_and_history
from scoring.investment import score_dataframe
from storage.history_db import HistoryDatabase


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
HISTORY_DATABASE = DATA / "atlas_history.db"


def save_history_snapshot(df: pd.DataFrame) -> str:
    """
    Salva no SQLite o resultado completo dos scores da execução atual.

    O horário faz parte da chave do snapshot, permitindo mais de uma
    execução no mesmo dia sem substituir registros anteriores.
    """

    snapshot_date = datetime.now().isoformat(timespec="seconds")

    with HistoryDatabase(HISTORY_DATABASE) as database:
        database.save_snapshot(
            df=df,
            snapshot_date=snapshot_date,
        )

    return snapshot_date


def main() -> None:
    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {settings_path}"
        )

    settings = json.loads(
        settings_path.read_text(encoding="utf-8")
    )

    watchlist_path = ROOT / settings.get(
        "watchlist_path",
        "config/watchlist.csv",
    )

    if not watchlist_path.exists():
        raise FileNotFoundError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    watchlist = pd.read_csv(watchlist_path)

    print("=" * 70)
    print("ATLAS – INVESTMENT DECISION OS")
    print("=" * 70)
    print(f"Watchlist: {watchlist_path}")
    print(f"Banco histórico: {HISTORY_DATABASE}")

    rows = fetch_watchlist(
        watchlist,
        period=settings.get("history_period", "1y"),
        interval=settings.get("history_interval", "1d"),
    )

    enriched = [
        enrich_technicals(row)
        for row in rows
    ]

    df = pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key != "history"
            }
            for row in enriched
        ]
    )

    if df.empty:
        raise RuntimeError(
            "Nenhum dado foi coletado. "
            "Verifique a watchlist ou a conexão."
        )

    df = normalize_columns(df)
    df = add_confidence_score(df)

    df = score_dataframe(
        df,
        CONFIG / "weights.json",
        CONFIG / "deal_breakers.json",
    )

    snapshot_date = save_history_snapshot(df)

    history_file, latest_file = write_latest_and_history(
        df,
        OUTPUT,
    )

    display_columns = [
        "symbol",
        "Investment Score",
        "Opportunity Score",
        "Opportunity Rating",
        "Business Score",
        "Valuation Score",
        "Financial Score",
        "Timing Score",
        "Confidence Score",
        "Risk Penalty",
        "Recommendation",
    ]

    available_display_columns = [
        column
        for column in display_columns
        if column in df.columns
    ]

    print()
    print(
        df[available_display_columns]
        .head(20)
        .to_string(index=False)
    )
    print()
    print(f"Snapshot histórico salvo em: {snapshot_date}")
    print(f"Banco SQLite atualizado em: {HISTORY_DATABASE}")
    print(f"Excel histórico salvo em: {history_file}")

    if latest_file:
        print(f"Latest atualizado em: {latest_file}")
    else:
        print(
            "[AVISO] latest.xlsx não foi atualizado. "
            "Provavelmente o arquivo está aberto no Excel."
        )

    print("Concluído.")


if __name__ == "__main__":
    main()
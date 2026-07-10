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
from reports.morning_brief import (
    render_morning_brief,
    write_morning_brief,
)

from scoring.investment import score_dataframe

from storage.history_db import HistoryDatabase


ROOT = Path(__file__).resolve().parent

CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"

HISTORY_DATABASE = DATA / "atlas_history.db"

MORNING_BRIEF_FILE = OUTPUT / "morning_brief.md"


def save_history_snapshot(
    df: pd.DataFrame,
) -> str:
    """
    Salva o snapshot atual no banco SQLite.
    """

    snapshot_date = datetime.now().isoformat(
        timespec="seconds"
    )

    with HistoryDatabase(
        HISTORY_DATABASE
    ) as database:

        database.save_snapshot(
            df=df,
            snapshot_date=snapshot_date,
        )

    return snapshot_date


def load_settings() -> dict:

    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {settings_path}"
        )

    return json.loads(
        settings_path.read_text(
            encoding="utf-8"
        )
    )


def load_watchlist(
    settings: dict,
) -> tuple[Path, pd.DataFrame]:

    watchlist_path = ROOT / settings.get(
        "watchlist_path",
        "config/watchlist.csv",
    )

    if not watchlist_path.exists():
        raise FileNotFoundError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    watchlist = pd.read_csv(
        watchlist_path
    )

    return (
        watchlist_path,
        watchlist,
    )


def collect_market_data(
    settings: dict,
    watchlist: pd.DataFrame,
) -> pd.DataFrame:

    rows = fetch_watchlist(
        watchlist,
        period=settings.get(
            "history_period",
            "1y",
        ),
        interval=settings.get(
            "history_interval",
            "1d",
        ),
    )

    enriched = [
        enrich_technicals(
            row
        )
        for row in rows
    ]

    df = pd.DataFrame(
        [
            {
                k: v
                for k, v in row.items()
                if k != "history"
            }
            for row in enriched
        ]
    )

    if df.empty:
        raise RuntimeError(
            "Nenhum dado foi coletado."
        )

    return df


def build_scores(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = normalize_columns(df)

    df = add_confidence_score(df)

    df = score_dataframe(
        df,
        CONFIG / "weights.json",
        CONFIG / "deal_breakers.json",
    )

    return df


def print_console_table(
    df: pd.DataFrame,
) -> None:

    columns = [
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

    columns = [
        c
        for c in columns
        if c in df.columns
    ]

    print()

    print(
        df[columns]
        .head(20)
        .to_string(index=False)
    )

    print()


def generate_reports(
    df: pd.DataFrame,
):
    """
    Gera Excel e Morning Brief.
    """

    history_file, latest_file = (
        write_latest_and_history(
            df,
            OUTPUT,
        )
    )

    brief_path = write_morning_brief(
        current_df=df,
        database_path=HISTORY_DATABASE,
        output_path=MORNING_BRIEF_FILE,
    )

    return (
        history_file,
        latest_file,
        brief_path,
    )


def main() -> None:

    settings = load_settings()

    (
        watchlist_path,
        watchlist,
    ) = load_watchlist(
        settings
    )

    print("=" * 70)
    print("ATLAS DECISION INTELLIGENCE PLATFORM")
    print("=" * 70)

    print(
        f"Watchlist: {watchlist_path}"
    )

    print(
        f"History DB: {HISTORY_DATABASE}"
    )

    df = collect_market_data(
        settings,
        watchlist,
    )

    df = build_scores(df)

    snapshot = save_history_snapshot(
        df
    )

    (
        history_file,
        latest_file,
        brief_file,
    ) = generate_reports(
        df
    )
    print_console_table(df)

    print("-" * 70)
    print("ATLAS MORNING BRIEF")
    print("-" * 70)
    print()

    try:
        brief_text = render_morning_brief(
            current_df=df,
            database_path=HISTORY_DATABASE,
        )

        print(brief_text)

    except Exception as exc:
        print(
            "[AVISO] Não foi possível gerar o Morning Brief:"
        )
        print(exc)

    print()
    print("=" * 70)

    print(
        f"Snapshot salvo : {snapshot}"
    )

    print(
        f"SQLite         : {HISTORY_DATABASE}"
    )

    print(
        f"Histórico Excel: {history_file}"
    )

    if latest_file is not None:

        print(
            f"Latest.xlsx    : {latest_file}"
        )

    else:

        print(
            "Latest.xlsx não atualizado "
            "(arquivo aberto)."
        )

    print(
        f"Morning Brief  : {brief_file}"
    )

    print("=" * 70)

    print()

    print(
        "Atlas finalizado com sucesso."
    )


if __name__ == "__main__":
    main()
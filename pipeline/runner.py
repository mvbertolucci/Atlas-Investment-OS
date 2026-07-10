from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.indicators import enrich_technicals
from analytics.mapper import normalize_columns
from analytics.validator import add_confidence_score
from atlas_logger import get_logger
from health.health_check import print_health_report, run_health_check
from metrics.execution import (
    ExecutionMetrics,
    StageTimer,
    print_execution_metrics,
    save_execution_metrics,
)
from providers.yahoo import fetch_watchlist
from reports.excel import write_latest_and_history
from reports.morning_brief import render_morning_brief, write_morning_brief
from scoring.investment import score_dataframe
from storage.history_db import HistoryDatabase


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
LOGS = ROOT / "logs"

HISTORY_DATABASE = DATA / "atlas_history.db"
MORNING_BRIEF_FILE = OUTPUT / "morning_brief.md"
EXECUTION_METRICS_FILE = LOGS / "execution_metrics.csv"

logger = get_logger("atlas.pipeline")


def load_settings() -> dict[str, Any]:
    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {settings_path}"
        )

    data = json.loads(settings_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(
            f"settings.json deve conter um objeto JSON: {settings_path}"
        )

    return data


def load_watchlist(
    settings: dict[str, Any],
) -> tuple[Path, pd.DataFrame]:
    configured_path = settings.get(
        "watchlist_path",
        "config/watchlist.csv",
    )

    watchlist_path = ROOT / str(configured_path)

    if not watchlist_path.exists():
        raise FileNotFoundError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    watchlist = pd.read_csv(watchlist_path)

    if watchlist.empty:
        raise RuntimeError(
            f"A watchlist está vazia: {watchlist_path}"
        )

    return watchlist_path, watchlist


def collect_market_data(
    settings: dict[str, Any],
    watchlist: pd.DataFrame,
) -> pd.DataFrame:
    logger.info(
        "Iniciando coleta de dados para %s empresas.",
        len(watchlist),
    )

    rows = fetch_watchlist(
        watchlist,
        period=str(settings.get("history_period", "1y")),
        interval=str(settings.get("history_interval", "1d")),
    )

    enriched_rows = [
        enrich_technicals(row)
        for row in rows
    ]

    frame = pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key != "history"
            }
            for row in enriched_rows
        ]
    )

    if frame.empty:
        raise RuntimeError(
            "Nenhum dado foi coletado. "
            "Verifique a watchlist ou a conexão."
        )

    logger.info(
        "Coleta concluída: %s empresas retornadas.",
        len(frame),
    )

    return frame


def build_scores(frame: pd.DataFrame) -> pd.DataFrame:
    logger.info("Iniciando normalização e scoring.")

    result = normalize_columns(frame)
    result = add_confidence_score(result)

    result = score_dataframe(
        result,
        CONFIG / "weights.json",
        CONFIG / "deal_breakers.json",
    )

    logger.info(
        "Scoring concluído para %s empresas.",
        len(result),
    )

    return result


def save_history_snapshot(frame: pd.DataFrame) -> str:
    snapshot_date = datetime.now().isoformat(
        timespec="seconds"
    )

    with HistoryDatabase(HISTORY_DATABASE) as database:
        database.save_snapshot(
            df=frame,
            snapshot_date=snapshot_date,
        )

    logger.info(
        "Snapshot histórico salvo em %s.",
        snapshot_date,
    )

    return snapshot_date


def generate_excel_reports(
    frame: pd.DataFrame,
) -> tuple[Path, Path | None]:
    logger.info("Gerando relatórios Excel.")

    history_file, latest_file = write_latest_and_history(
        frame,
        OUTPUT,
    )

    logger.info(
        "Excel histórico gerado em %s.",
        history_file,
    )

    return history_file, latest_file


def generate_morning_brief(
    frame: pd.DataFrame,
) -> tuple[Path, str]:
    logger.info("Gerando Morning Brief.")

    brief_file = write_morning_brief(
        current_df=frame,
        database_path=HISTORY_DATABASE,
        output_path=MORNING_BRIEF_FILE,
    )

    brief_text = render_morning_brief(
        current_df=frame,
        database_path=HISTORY_DATABASE,
    )

    logger.info(
        "Morning Brief gerado em %s.",
        brief_file,
    )

    return brief_file, brief_text


def print_console_table(frame: pd.DataFrame) -> None:
    preferred_columns = [
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
        column
        for column in preferred_columns
        if column in frame.columns
    ]

    print()

    if columns:
        print(
            frame[columns]
            .head(20)
            .to_string(index=False)
        )
    else:
        print(
            "[AVISO] Nenhuma coluna de resumo foi encontrada."
        )

    print()


def print_generated_files(
    snapshot_date: str,
    history_file: Path,
    latest_file: Path | None,
    brief_file: Path,
) -> None:
    print("=" * 70)
    print("ARQUIVOS GERADOS")
    print("=" * 70)
    print(f"Snapshot        : {snapshot_date}")
    print(f"SQLite          : {HISTORY_DATABASE}")
    print(f"Excel histórico : {history_file}")

    if latest_file is not None:
        print(f"Latest.xlsx     : {latest_file}")
    else:
        print(
            "Latest.xlsx     : não atualizado "
            "(arquivo provavelmente aberto)"
        )

    print(f"Morning Brief   : {brief_file}")
    print("=" * 70)


def run_atlas() -> None:
    metrics = ExecutionMetrics()

    logger.info("Iniciando Atlas.")

    try:
        health_report = run_health_check(ROOT)
        print_health_report(health_report)

        settings = load_settings()
        watchlist_path, watchlist = load_watchlist(settings)

        print()
        print("=" * 70)
        print("ATLAS DECISION INTELLIGENCE PLATFORM")
        print("=" * 70)
        print(f"Watchlist       : {watchlist_path}")
        print(f"History DB      : {HISTORY_DATABASE}")
        print(f"Execution log   : {LOGS / 'atlas.log'}")
        print()

        with StageTimer(metrics, "download_time"):
            frame = collect_market_data(
                settings,
                watchlist,
            )

        metrics.companies = len(frame)

        with StageTimer(metrics, "scoring_time"):
            frame = build_scores(frame)

        with StageTimer(metrics, "history_time"):
            snapshot_date = save_history_snapshot(frame)

        with StageTimer(metrics, "reports_time"):
            history_file, latest_file = generate_excel_reports(
                frame
            )

        with StageTimer(metrics, "morning_brief_time"):
            brief_file, brief_text = generate_morning_brief(
                frame
            )

        print_console_table(frame)
        print(brief_text)
        print()

        print_generated_files(
            snapshot_date=snapshot_date,
            history_file=history_file,
            latest_file=latest_file,
            brief_file=brief_file,
        )

        save_execution_metrics(
            metrics,
            EXECUTION_METRICS_FILE,
        )

        print_execution_metrics(metrics)

        logger.info(
            "Atlas concluído com sucesso em %.2f segundos.",
            metrics.total_time(),
        )

        print(
            f"Métricas salvas : {EXECUTION_METRICS_FILE}"
        )
        print()
        print("Atlas finalizado com sucesso.")

    except SystemExit:
        logger.error(
            "Execução interrompida pelo Health Check."
        )
        raise

    except Exception:
        logger.exception(
            "Falha durante a execução do Atlas."
        )
        raise
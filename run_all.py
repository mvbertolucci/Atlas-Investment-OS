from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from analytics.feature_audit import (
    audit_coverage,
    format_coverage_report,
    phantom_weight_summary,
)
from analytics.fundamentals import compute_fundamentals
from analytics.indicators import enrich_technicals
from analytics.mapper import normalize_columns
from atlas_logger import get_logger
from health.health_check import print_health_report, run_health_check
from metrics.execution import (
    ExecutionMetrics,
    StageTimer,
    print_execution_metrics,
    save_execution_metrics,
)
from outcomes.analytics import (
    OutcomeAnalyticsReport,
    build_outcome_analytics_report,
)
from outcomes.pipeline import (
    OutcomeCaptureResult,
    OutcomeEvaluationResult,
    capture_outcome_snapshots,
    evaluate_due_outcomes,
)
from outcomes.report import write_outcome_report
from portfolio.pipeline import (
    build_portfolio_intelligence,
    write_portfolio_report,
)
from portfolio.report import PortfolioReport
from providers.yahoo import fetch_watchlist
from ranking import (
    RankingReport,
    load_ranking_policy,
    rank_companies,
    write_ranking_report,
)
from reports.excel import write_latest_and_history
from reports.morning_brief import render_morning_brief, write_morning_brief
from dashboard import build_dashboard_view, write_dashboard_view
from priority import (
    PriorityReport,
    build_buy_priority,
    build_sell_priority,
    write_priority_report,
)
from reports.report_engine import build_company_reports
from scoring.investment import score_dataframe
from storage.history_db import HistoryDatabase
from universe import (
    UniverseReport,
    evaluate_universe,
    load_universe_policy,
    write_universe_report,
)


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
LOGS = ROOT / "logs"

HISTORY_DATABASE = DATA / "atlas_history.db"
MORNING_BRIEF_FILE = OUTPUT / "morning_brief.md"
EXECUTION_METRICS_FILE = LOGS / "execution_metrics.csv"
PORTFOLIO_REPORT_FILE = OUTPUT / "portfolio_report.json"
OUTCOME_REPORT_FILE = OUTPUT / "outcome_report.json"
DASHBOARD_REPORT_FILE = OUTPUT / "dashboard.json"
PRIORITY_REPORT_FILE = OUTPUT / "priority_report.json"
RESEARCH_RANKING_REPORT_FILE = OUTPUT / "research_ranking_report.json"
UNIVERSE_REPORT_FILE = OUTPUT / "universe_report.json"
RANKING_REPORT_FILE = OUTPUT / "ranking_report.json"

logger = get_logger("run_all")


def load_settings() -> dict:
    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {settings_path}"
        )

    return json.loads(
        settings_path.read_text(encoding="utf-8")
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

    watchlist = pd.read_csv(watchlist_path)

    if watchlist.empty:
        raise RuntimeError(
            f"A watchlist está vazia: {watchlist_path}"
        )

    return watchlist_path, watchlist


def collect_market_data(
    settings: dict,
    watchlist: pd.DataFrame,
) -> pd.DataFrame:
    logger.info(
        "Iniciando coleta de dados para %s empresas.",
        len(watchlist),
    )

    rows = fetch_watchlist(
        watchlist,
        period=settings.get("history_period", "2y"),
        interval=settings.get("history_interval", "1d"),
    )

    enriched = [
        compute_fundamentals(enrich_technicals(row))
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

    logger.info(
        "Coleta concluída: %s empresas retornadas.",
        len(df),
    )

    return df


def build_scores(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Iniciando normalização e scoring.")

    result = normalize_columns(df)

    result = score_dataframe(
        result,
        CONFIG / "model.yaml",
        CONFIG / "deal_breakers.json",
    )

    logger.info(
        "Scoring concluído para %s empresas.",
        len(result),
    )

    return result


def audit_feature_coverage(df: pd.DataFrame) -> dict:
    """
    Mede quanto do Investment Score está alocado a features cujas colunas
    nunca chegam populadas (peso fantasma = constante 50 neutro).

    Não altera o pipeline; apenas informa e registra um aviso.
    """

    coverage = audit_coverage(
        df,
        CONFIG / "features.yaml",
        CONFIG / "model.yaml",
    )

    summary = phantom_weight_summary(coverage)

    print()
    print(format_coverage_report(coverage, summary))

    phantom_share = summary["phantom_investment_share"]

    if phantom_share > 0:
        logger.warning(
            "Peso fantasma no Investment Score: %.1f%% "
            "(features sempre neutras por falta de dados).",
            phantom_share,
        )

    return summary


def save_history_snapshot(df: pd.DataFrame) -> str:
    snapshot_date = datetime.now().isoformat(
        timespec="seconds"
    )

    with HistoryDatabase(HISTORY_DATABASE) as database:
        database.save_snapshot(
            df=df,
            snapshot_date=snapshot_date,
        )

    logger.info(
        "Snapshot histórico salvo em %s.",
        snapshot_date,
    )

    return snapshot_date


def save_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeCaptureResult | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        logger.info("Outcome Analytics desabilitado.")
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        result = capture_outcome_snapshots(
            database,
            df,
            decision_date=snapshot_date,
            horizons_days=settings.get(
                "outcome_horizons_days"
            ),
        )

    logger.info(
        "Outcome snapshots salvos: %s; ignorados: %s.",
        result.saved_count,
        len(result.skipped_symbols),
    )
    return result


def evaluate_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeEvaluationResult | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        result = evaluate_due_outcomes(
            database,
            df,
            evaluation_date=snapshot_date,
            horizons_days=settings.get(
                "outcome_horizons_days"
            ),
        )

    logger.info(
        "Outcome results avaliados: %s; pendentes: %s; sem preço: %s.",
        result.evaluated_count,
        result.pending_count,
        len(result.missing_price_symbols),
    )
    return result


def generate_outcome_analytics(
    settings: dict,
) -> OutcomeAnalyticsReport | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        report = build_outcome_analytics_report(
            database,
            threshold_pct=settings.get(
                "outcome_hit_threshold_pct",
                0.0,
            ),
            bucket_size=settings.get(
                "outcome_calibration_bucket_size",
                20,
            ),
        )

    write_outcome_report(
        report,
        OUTCOME_REPORT_FILE,
    )

    logger.info(
        "Outcome Analytics: %s resultados elegíveis; hit rate %s.",
        report.hit_rate.eligible_count,
        report.hit_rate.hit_rate,
    )
    return report


def generate_universe_report(
    df: pd.DataFrame,
    settings: dict,
) -> UniverseReport | None:
    """Avalia e publica o universo sem filtrar o pipeline existente."""
    if not settings.get("universe_enabled", True):
        logger.info("Market Universe desabilitado.")
        return None

    policy_path = ROOT / settings.get(
        "universe_policy_path",
        "config/universe.yaml",
    )
    policy = load_universe_policy(policy_path)
    report = evaluate_universe(df, policy)
    write_universe_report(report, UNIVERSE_REPORT_FILE)

    logger.info(
        "Market Universe: %s elegíveis de %s; cobertura média %s%%.",
        report.eligible_count,
        report.total_count,
        report.average_data_coverage_pct,
    )
    return report


def generate_ranking_report(
    df: pd.DataFrame,
    settings: dict,
    universe_report: UniverseReport | None,
) -> RankingReport | None:
    """Publica ranking diagnóstico sem recalcular scores ou decisões."""
    if not settings.get("ranking_enabled", True):
        logger.info("Analytical Ranking desabilitado.")
        return None
    if universe_report is None:
        logger.warning(
            "Analytical Ranking ignorado: Universe Report indisponível."
        )
        return None

    policy_path = ROOT / settings.get(
        "ranking_policy_path",
        "config/ranking.yaml",
    )
    policy = load_ranking_policy(policy_path)
    report = rank_companies(df, universe_report, policy)
    write_ranking_report(report, RANKING_REPORT_FILE)
    logger.info(
        "Analytical Ranking: %s candidatos de %s empresas.",
        report.candidate_count,
        report.total_count,
    )
    return report


def generate_dashboard(
    df: pd.DataFrame,
    settings: dict,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
    universe_report: UniverseReport | None = None,
    priority_report: PriorityReport | None = None,
) -> Path | None:
    """
    Emite o contrato read-only do dashboard (output/dashboard.json).

    Pura agregação das visões que o Atlas já produziu nesta execução
    (mercado, empresas, carteira, outcomes e prioridade); não recomputa nem
    altera nada. Guardado por `dashboard_enabled` (default True).
    """
    if not settings.get("dashboard_enabled", True):
        return None

    view = build_dashboard_view(
        build_company_reports(df),
        market=universe_report,
        portfolio=portfolio_report,
        outcomes=outcome_report,
        priority=priority_report,
    )

    write_dashboard_view(view, DASHBOARD_REPORT_FILE)

    logger.info(
        "Dashboard contract gerado em %s (%s empresas).",
        DASHBOARD_REPORT_FILE,
        len(view.companies),
    )
    return DASHBOARD_REPORT_FILE


def generate_priority_report(
    settings: dict,
    *,
    ranking_report: RankingReport | None,
    portfolio_report: PortfolioReport | None,
) -> tuple[Path, PriorityReport] | None:
    """
    Classificação individual de prioridade de venda (carteira atual) e de
    compra (screener, quando o universo amplo já foi coletado). Não
    distribui peso nem aplica teto de setor -- apenas ordena por qualidade.
    Guardado por priority_enabled (default True).
    """
    if not settings.get("priority_enabled", True):
        return None

    weights_by_symbol: dict[str, float] = {}
    held_symbols: frozenset[str] | None = None

    if portfolio_report is not None:
        weights_by_symbol = dict(
            portfolio_report.allocation.get("by_symbol", {})
        )
        held_symbols = frozenset(weights_by_symbol)

    sell = build_sell_priority(
        ranking_report.to_dict()["companies"] if ranking_report else (),
        held_symbols=held_symbols,
        weights_by_symbol=weights_by_symbol,
    )

    buy = None
    if RESEARCH_RANKING_REPORT_FILE.exists():
        research_data = json.loads(
            RESEARCH_RANKING_REPORT_FILE.read_text(encoding="utf-8")
        )
        buy = build_buy_priority(
            research_data["companies"],
            held_symbols=held_symbols or frozenset(),
        )

    report = PriorityReport(sell=sell, buy=buy)
    write_priority_report(report, PRIORITY_REPORT_FILE)

    logger.info(
        "Priority Report: %s holdings classificados; %s candidatos de "
        "compra disponíveis.",
        len(sell.items),
        len(buy.items) if buy is not None else 0,
    )
    return PRIORITY_REPORT_FILE, report


def generate_excel_reports(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, Path | None]:
    logger.info("Gerando relatórios Excel.")

    history_file, latest_file = write_latest_and_history(
        df,
        OUTPUT,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    logger.info(
        "Excel histórico gerado em %s.",
        history_file,
    )

    return history_file, latest_file


def generate_morning_brief(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, str]:
    logger.info("Gerando Morning Brief.")

    brief_path = write_morning_brief(
        current_df=df,
        database_path=HISTORY_DATABASE,
        output_path=MORNING_BRIEF_FILE,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    brief_text = render_morning_brief(
        current_df=df,
        database_path=HISTORY_DATABASE,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    logger.info(
        "Morning Brief gerado em %s.",
        brief_path,
    )

    return brief_path, brief_text



def generate_portfolio_intelligence(
    df: pd.DataFrame,
    settings: dict,
) -> tuple[Path, PortfolioReport] | None:
    portfolio_path = ROOT / settings.get(
        "portfolio_path",
        "config/portfolio.csv",
    )

    if not portfolio_path.exists():
        logger.info(
            "Portfolio Intelligence ignorado: arquivo não encontrado em %s.",
            portfolio_path,
        )
        return None

    logger.info(
        "Executando Portfolio Intelligence com %s.",
        portfolio_path,
    )

    report = build_portfolio_intelligence(
        portfolio_path,
        df,
        portfolio_name=settings.get("portfolio_name"),
        cash=float(settings.get("portfolio_cash", 0.0)),
        currency=settings.get("portfolio_currency", "BRL"),
        rebalance_mode=settings.get(
            "portfolio_rebalance_mode", "sell_only"
        ),
    )
    report_path = write_portfolio_report(
        report,
        PORTFOLIO_REPORT_FILE,
    )

    logger.info(
        "Portfolio Intelligence concluído em %s.",
        report_path,
    )
    return report_path, report


def _safe_console_text(
    value: object,
    encoding: str | None = None,
) -> str:
    text = str(value)
    target_encoding = encoding or getattr(
        sys.stdout,
        "encoding",
        None,
    )
    if not target_encoding:
        return text
    return text.encode(
        target_encoding,
        errors="replace",
    ).decode(target_encoding)


def print_console_table(df: pd.DataFrame) -> None:
    columns = [
        "symbol",
        "Investment Score",
        "Opportunity Score",
        "Opportunity Rating",
        "Conviction Score",
        "Decision Rating",
        "Suggested Action",
        "Business Score",
        "Valuation Score",
        "Financial Score",
        "Timing Score",
        "Confidence Score",
        "Risk Penalty",
        "Recommendation",
    ]

    available_columns = [
        column
        for column in columns
        if column in df.columns
    ]

    print()

    if available_columns:
        table = (
            df[available_columns]
            .head(20)
            .to_string(index=False)
        )
        print(_safe_console_text(table))
    else:
        print(
            "[AVISO] Nenhuma coluna de resumo foi encontrada."
        )

    print()


def main() -> None:
    metrics = ExecutionMetrics()

    logger.info("Iniciando Atlas.")

    try:
        health_report = run_health_check(ROOT)
        print_health_report(health_report)

        settings = load_settings()

        watchlist_path, watchlist = load_watchlist(
            settings
        )

        print()
        print("=" * 70)
        print("ATLAS DECISION INTELLIGENCE PLATFORM")
        print("=" * 70)
        print(f"Watchlist       : {watchlist_path}")
        print(f"History DB      : {HISTORY_DATABASE}")
        print(f"Execution log   : {LOGS / 'atlas.log'}")
        print()

        with StageTimer(metrics, "download_time"):
            df = collect_market_data(
                settings,
                watchlist,
            )

        metrics.companies = len(df)

        with StageTimer(metrics, "scoring_time"):
            df = build_scores(df)

        audit_feature_coverage(df)

        universe_report = generate_universe_report(
            df,
            settings,
        )
        ranking_report = generate_ranking_report(
            df,
            settings,
            universe_report,
        )

        with StageTimer(metrics, "history_time"):
            snapshot_date = save_history_snapshot(df)
            outcome_capture = save_outcome_decisions(
                df,
                snapshot_date,
                settings,
            )
            outcome_evaluation = evaluate_outcome_decisions(
                df,
                snapshot_date,
                settings,
            )
            outcome_analytics = generate_outcome_analytics(
                settings
            )

        portfolio_result = generate_portfolio_intelligence(
            df,
            settings,
        )
        portfolio_report = (
            portfolio_result[1]
            if portfolio_result is not None
            else None
        )

        with StageTimer(metrics, "reports_time"):
            history_file, latest_file = (
                generate_excel_reports(
                    df,
                    portfolio_report=portfolio_report,
                    outcome_report=outcome_analytics,
                )
            )

        with StageTimer(
            metrics,
            "morning_brief_time",
        ):
            brief_file, brief_text = (
                generate_morning_brief(
                    df,
                    portfolio_report=portfolio_report,
                    outcome_report=outcome_analytics,
                )
            )

        priority_result = generate_priority_report(
            settings,
            ranking_report=ranking_report,
            portfolio_report=portfolio_report,
        )
        priority_file, priority_report = (
            priority_result
            if priority_result is not None
            else (None, None)
        )

        dashboard_file = generate_dashboard(
            df,
            settings,
            portfolio_report=portfolio_report,
            outcome_report=outcome_analytics,
            universe_report=universe_report,
            priority_report=priority_report,
        )

        print_console_table(df)

        print(_safe_console_text(brief_text))
        print()

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

        if outcome_capture is not None:
            print(
                "Outcome Captures: "
                f"{outcome_capture.saved_count} "
                f"({', '.join(map(str, outcome_capture.horizons_days))} dias)"
            )
            if outcome_capture.skipped_symbols:
                print(
                    "Outcome Skipped : "
                    + ", ".join(
                        outcome_capture.skipped_symbols
                    )
                )

        if outcome_evaluation is not None:
            print(
                "Outcome Results : "
                f"{outcome_evaluation.evaluated_count} avaliados; "
                f"{outcome_evaluation.pending_count} pendentes"
            )
            if outcome_evaluation.missing_price_symbols:
                print(
                    "Outcome Prices  : ausentes para "
                    + ", ".join(
                        outcome_evaluation.missing_price_symbols
                    )
                )

        if outcome_analytics is not None:
            hit_rate = outcome_analytics.hit_rate
            print(
                "Outcome Hit Rate: "
                f"{hit_rate.hit_rate if hit_rate.hit_rate is not None else '-'}% "
                f"({hit_rate.hit_count}/{hit_rate.eligible_count})"
            )
            print(f"Outcome JSON    : {OUTCOME_REPORT_FILE}")

        if dashboard_file is not None:
            print(f"Dashboard JSON  : {dashboard_file}")

        if priority_file is not None:
            print(f"Priority JSON   : {priority_file}")

        if universe_report is not None:
            print(f"Universe JSON   : {UNIVERSE_REPORT_FILE}")
            print(
                "Universe        : "
                f"{universe_report.eligible_count}/"
                f"{universe_report.total_count} elegíveis; "
                f"cobertura {universe_report.average_data_coverage_pct}%"
            )

        if ranking_report is not None:
            print(f"Ranking JSON    : {RANKING_REPORT_FILE}")
            print(
                "Ranking         : "
                f"{ranking_report.candidate_count}/"
                f"{ranking_report.total_count} candidatos"
            )

        if portfolio_result is not None:
            portfolio_file, portfolio_report = portfolio_result
            print(f"Portfolio JSON  : {portfolio_file}")
            print(
                "Portfolio Score : "
                f"{portfolio_report.summary.get('quality_score')} "
                f"({portfolio_report.summary.get('quality_rating')})"
            )
        else:
            print(
                "Portfolio       : não executado "
                "(config/portfolio.csv ausente)"
            )

        print("=" * 70)

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


if __name__ == "__main__":
    main()

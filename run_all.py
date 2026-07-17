from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.history import load_history as load_score_history
from application import (
    ORIGIN_PORTFOLIO,
    ORIGIN_PRIORITY,
    ORIGIN_UNIVERSE,
    ORIGIN_WATCHLIST,
    CollectionApplicationService,
    HistoryApplicationService,
    IntelligenceApplicationService,
    OperationalRuntimeService,
    ReportingApplicationService,
    ScoringApplicationService,
    TickerAnalysisApplicationService,
)
from atlas_logger import get_logger
from health.health_check import print_health_report, run_health_check
from metrics.execution import (
    ExecutionMetrics,
    print_execution_metrics,
    save_execution_metrics,
)
from outcomes.analytics import (
    OutcomeAnalyticsReport,
)
from outcomes.pipeline import (
    OutcomeCaptureResult,
    OutcomeEvaluationResult,
)
from orchestration import PipelineContext, build_pipeline, parse_pipeline_request
from orchestration.services import (
    CollectionServices,
    HistoryServices,
    IntelligenceServices,
    PipelinePaths,
    PipelineServices,
    ReportingServices,
    RuntimeServices,
    ScoringServices,
    TickerServices,
)
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy
from ranking import RankingReport
from reports.morning_brief import render_morning_brief, write_morning_brief
from priority import PriorityReport
from scoring.reference import ScoringReference
from universe import UniverseReport
from watchlist import WatchlistReport


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
# Separação "para você" vs "não é para você" (ver STATUS.md): relatorios/ só
# tem artefatos pensados para leitura humana (HTML, Excel, Markdown);
# dados/ só tem os contratos JSON internos entre motor e camada de
# relatório -- nunca pensados para abrir direto.
OUTPUT_REPORTS = OUTPUT / "relatorios"
OUTPUT_DATA = OUTPUT / "dados"
DATA = ROOT / "data"
LOGS = ROOT / "logs"

HISTORY_DATABASE = DATA / "atlas_history.db"
MORNING_BRIEF_FILE = OUTPUT_REPORTS / "morning_brief.md"
EXECUTION_METRICS_FILE = LOGS / "execution_metrics.csv"
PORTFOLIO_REPORT_FILE = OUTPUT_DATA / "portfolio_report.json"
OUTCOME_REPORT_FILE = OUTPUT_DATA / "outcome_report.json"
DASHBOARD_REPORT_FILE = OUTPUT_DATA / "dashboard.json"
PRIORITY_REPORT_FILE = OUTPUT_DATA / "priority_report.json"
PERFORMANCE_VALIDATION_FILE = OUTPUT_DATA / "performance_validation.json"
RESEARCH_RANKING_REPORT_FILE = OUTPUT_DATA / "research_ranking_report.json"
UNIVERSE_REPORT_FILE = OUTPUT_DATA / "universe_report.json"
RANKING_REPORT_FILE = OUTPUT_DATA / "ranking_report.json"
WATCHLIST_REPORT_FILE = OUTPUT_DATA / "watchlist_report.json"

logger = get_logger("run_all")


def _read_status_md() -> str:
    return _intelligence_application_service().read_status_md()


def load_settings() -> dict:
    return _operational_runtime_service().load_settings()


def _operational_runtime_service() -> OperationalRuntimeService:
    return OperationalRuntimeService(
        root=ROOT,
        config=CONFIG,
        execution_metrics_file=EXECUTION_METRICS_FILE,
        logger=logger,
        health_check_runner=run_health_check,
        health_report_writer=print_health_report,
        metrics_saver=save_execution_metrics,
        metrics_writer=print_execution_metrics,
    )


def _collection_application_service() -> CollectionApplicationService:
    return CollectionApplicationService(
        root=ROOT,
        config=CONFIG,
        logger=logger,
    )


def _scoring_application_service() -> ScoringApplicationService:
    return ScoringApplicationService(
        root=ROOT,
        config=CONFIG,
        universe_report_file=UNIVERSE_REPORT_FILE,
        ranking_report_file=RANKING_REPORT_FILE,
        logger=logger,
    )


def _history_application_service() -> HistoryApplicationService:
    return HistoryApplicationService(
        root=ROOT,
        config=CONFIG,
        history_database=HISTORY_DATABASE,
        outcome_report_file=OUTCOME_REPORT_FILE,
        logger=logger,
    )


def _intelligence_application_service() -> IntelligenceApplicationService:
    return IntelligenceApplicationService(
        root=ROOT,
        config=CONFIG,
        output_reports=OUTPUT_REPORTS,
        history_database=HISTORY_DATABASE,
        portfolio_report_file=PORTFOLIO_REPORT_FILE,
        watchlist_report_file=WATCHLIST_REPORT_FILE,
        logger=logger,
    )


def _reporting_application_service() -> ReportingApplicationService:
    return ReportingApplicationService(
        output_reports=OUTPUT_REPORTS,
        history_database=HISTORY_DATABASE,
        morning_brief_file=MORNING_BRIEF_FILE,
        performance_validation_file=PERFORMANCE_VALIDATION_FILE,
        dashboard_report_file=DASHBOARD_REPORT_FILE,
        priority_report_file=PRIORITY_REPORT_FILE,
        research_ranking_report_file=RESEARCH_RANKING_REPORT_FILE,
        logger=logger,
        morning_brief_writer=write_morning_brief,
        morning_brief_renderer=render_morning_brief,
    )


def _ticker_analysis_application_service(
    collection: CollectionApplicationService | None = None,
    scoring: ScoringApplicationService | None = None,
    history: HistoryApplicationService | None = None,
) -> TickerAnalysisApplicationService:
    return TickerAnalysisApplicationService(
        config=CONFIG,
        output_reports=OUTPUT_REPORTS,
        collection=collection or _collection_application_service(),
        scoring=scoring or _scoring_application_service(),
        history=history or _history_application_service(),
        logger=logger,
    )


def load_watchlist(
    settings: dict,
) -> tuple[Path, pd.DataFrame]:
    return _collection_application_service().load_watchlist(settings)


def merge_watchlist_with_portfolio(
    watchlist: pd.DataFrame,
    settings: dict,
) -> pd.DataFrame:
    return _collection_application_service().merge_watchlist_with_portfolio(
        watchlist, settings
    )


def collect_market_data(
    settings: dict,
    watchlist: pd.DataFrame,
    *,
    failures: list[str] | None = None,
) -> pd.DataFrame:
    return _collection_application_service().collect_market_data(
        settings,
        watchlist,
        failures=failures,
    )


def load_official_scoring_reference(
    settings: dict,
) -> ScoringReference | None:
    return _scoring_application_service().load_official_reference(settings)


def build_scores(
    df: pd.DataFrame,
    scoring_reference: ScoringReference | None = None,
) -> pd.DataFrame:
    return _scoring_application_service().build_scores(
        df, scoring_reference
    )


def audit_feature_coverage(df: pd.DataFrame) -> dict:
    return _scoring_application_service().audit_feature_coverage(df)


def generate_universe_report(
    df: pd.DataFrame,
    settings: dict,
) -> UniverseReport | None:
    return _scoring_application_service().generate_universe_report(
        df, settings
    )


def generate_ranking_report(
    df: pd.DataFrame,
    settings: dict,
    universe_report: UniverseReport | None,
) -> RankingReport | None:
    return _scoring_application_service().generate_ranking_report(
        df, settings, universe_report
    )


def save_history_snapshot(
    df: pd.DataFrame,
    snapshot_date: str,
    model_version: str = "legacy",
) -> str:
    return _history_application_service().save_history_snapshot(
        df, snapshot_date, model_version
    )


def save_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeCaptureResult | None:
    return _history_application_service().save_outcome_decisions(
        df, snapshot_date, settings
    )


def evaluate_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeEvaluationResult | None:
    return _history_application_service().evaluate_outcome_decisions(
        df, snapshot_date, settings
    )


def generate_outcome_analytics(
    settings: dict,
) -> OutcomeAnalyticsReport | None:
    return _history_application_service().generate_outcome_analytics(settings)


def generate_performance_validation(
    df: pd.DataFrame,
    settings: dict,
    *,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
    snapshot_date: str | None = None,
) -> Path | None:
    """
    Emite o contrato inicial de validação de performance
    (output/performance_validation.json).

    Esta etapa é somente publicação/validação. Não altera scores, decisões,
    carteira, ranking ou outcome analytics -- só resume o que esses motores
    já produziram nesta run.
    """
    return _reporting_application_service().generate_performance_validation(
        df,
        settings,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
        snapshot_date=snapshot_date,
    )


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
    return _reporting_application_service().generate_dashboard(
        df,
        settings,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
        universe_report=universe_report,
        priority_report=priority_report,
    )


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
    return _reporting_application_service().generate_priority_report(
        settings,
        ranking_report=ranking_report,
        portfolio_report=portfolio_report,
    )


def generate_excel_reports(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, Path | None]:
    return _reporting_application_service().generate_excel_reports(
        df,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )


def generate_morning_brief(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, str]:
    return _reporting_application_service().generate_morning_brief(
        df,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )



def generate_portfolio_intelligence(
    df: pd.DataFrame,
    settings: dict,
    *,
    sell_rules_policy: SellRulesPolicy | None = None,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
) -> tuple[Path, PortfolioReport] | None:
    return _intelligence_application_service().generate_portfolio_intelligence(
        df,
        settings,
        sell_rules_policy=sell_rules_policy,
        previous_by_symbol=previous_by_symbol,
        baseline_status=baseline_status,
        previous_run_at=previous_run_at,
        current_run_at=current_run_at,
    )


def generate_watchlist_report(
    df: pd.DataFrame,
    settings: dict,
    *,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
) -> tuple[Path, WatchlistReport] | None:
    return _intelligence_application_service().generate_watchlist_report(
        df,
        settings,
        previous_by_symbol=previous_by_symbol,
        baseline_status=baseline_status,
        previous_run_at=previous_run_at,
        current_run_at=current_run_at,
    )


def _safe_console_text(
    value: object,
    encoding: str | None = None,
) -> str:
    return _operational_runtime_service().safe_console_text(value, encoding)


def print_console_table(df: pd.DataFrame) -> None:
    _operational_runtime_service().print_console_table(df)


def run_ticker_mode(symbol: str, settings: dict) -> Path:
    """
    Modo --ticker SYM: gera o one-pager de um símbolo (decomposição de
    score + histórico + tese, se for uma posição real).

    O símbolo é pontuado contra a última distribuição oficial do mercado
    amplo elegível. A watchlist não participa do denominador e, portanto,
    adicionar ou remover um ticker dela não altera este score.
    """
    return _ticker_analysis_application_service().run_ticker_mode(
        symbol, settings
    )


def build_pipeline_services() -> PipelineServices:
    paths = PipelinePaths(
        root=ROOT,
        config=CONFIG,
        logs=LOGS,
        output_data=OUTPUT_DATA,
        output_reports=OUTPUT_REPORTS,
        history_database=HISTORY_DATABASE,
        execution_metrics_file=EXECUTION_METRICS_FILE,
        outcome_report_file=OUTCOME_REPORT_FILE,
        universe_report_file=UNIVERSE_REPORT_FILE,
        ranking_report_file=RANKING_REPORT_FILE,
    )
    collection_application = _collection_application_service()
    scoring_application = _scoring_application_service()
    history_application = _history_application_service()
    intelligence_application = _intelligence_application_service()
    reporting_application = _reporting_application_service()
    operational_runtime = _operational_runtime_service()
    ticker_application = _ticker_analysis_application_service(
        collection_application,
        scoring_application,
        history_application,
    )
    return PipelineServices(
        runtime=RuntimeServices(
            paths=paths,
            logger=logger,
            _run_health_check=operational_runtime.run_health_check,
            _print_health_report=operational_runtime.print_health_report,
            _load_settings=operational_runtime.load_settings,
            _print_console_table=operational_runtime.print_console_table,
            _safe_console_text=operational_runtime.safe_console_text,
            _save_execution_metrics=(
                operational_runtime.save_execution_metrics
            ),
            _print_execution_metrics=(
                operational_runtime.print_execution_metrics
            ),
        ),
        ticker=TickerServices(
            _run_ticker_mode=ticker_application.run_ticker_mode,
        ),
        collection=CollectionServices(
            _load_watchlist=collection_application.load_watchlist,
            _merge_watchlist_with_portfolio=(
                collection_application.merge_watchlist_with_portfolio
            ),
            _collect_market_data=collection_application.collect_market_data,
        ),
        scoring=ScoringServices(
            paths=paths,
            _load_official_reference=(
                scoring_application.load_official_reference
            ),
            _build_scores=scoring_application.build_scores,
            _audit_feature_coverage=(
                scoring_application.audit_feature_coverage
            ),
            _generate_universe_report=(
                scoring_application.generate_universe_report
            ),
            _generate_ranking_report=(
                scoring_application.generate_ranking_report
            ),
        ),
        history=HistoryServices(
            paths=paths,
            logger=logger,
            _load_model_config=history_application.load_model_config,
            _load_score_history=history_application.load_score_history,
            _previous_run_context=history_application.previous_run_context,
            _load_sell_rules_policy=(
                history_application.load_sell_rules_policy
            ),
            _load_portfolio=history_application.load_portfolio,
            _save_history_snapshot=history_application.save_history_snapshot,
            _save_outcome_decisions=history_application.save_outcome_decisions,
            _evaluate_outcome_decisions=(
                history_application.evaluate_outcome_decisions
            ),
            _generate_outcome_analytics=(
                history_application.generate_outcome_analytics
            ),
        ),
        intelligence=IntelligenceServices(
            paths=paths,
            _read_status_md=intelligence_application.read_status_md,
            _generate_portfolio_intelligence=(
                intelligence_application.generate_portfolio_intelligence
            ),
            _generate_watchlist_report=(
                intelligence_application.generate_watchlist_report
            ),
            _build_report_context=(
                intelligence_application.build_report_context
            ),
            _render_and_write_report=(
                intelligence_application.render_and_write_report
            ),
        ),
        reporting=ReportingServices(
            _generate_excel_reports=(
                reporting_application.generate_excel_reports
            ),
            _generate_morning_brief=(
                reporting_application.generate_morning_brief
            ),
            _generate_priority_report=(
                reporting_application.generate_priority_report
            ),
            _generate_performance_validation=(
                reporting_application.generate_performance_validation
            ),
            _generate_dashboard=reporting_application.generate_dashboard,
        ),
    )


def main(argv: list[str] | None = None) -> None:
    request = parse_pipeline_request(argv)
    metrics = ExecutionMetrics()
    logger.info("Iniciando Atlas (modo=%s).", request.mode)
    context = PipelineContext(
        request=request,
        services=build_pipeline_services(),
        metrics=metrics,
    )
    try:
        build_pipeline(request.mode).run(context)
    except SystemExit:
        logger.error("Execução interrompida pelo Health Check.")
        raise
    except Exception:
        logger.exception("Falha durante a execução do Atlas.")
        raise

if __name__ == "__main__":
    main()

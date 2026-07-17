from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from analytics.history import load_history as load_score_history
from analytics.history import previous_run_context
from analytics.performance_validation import (
    build_performance_validation_report,
    write_performance_validation_report,
)
from application import (
    ORIGIN_PORTFOLIO,
    ORIGIN_PRIORITY,
    ORIGIN_UNIVERSE,
    ORIGIN_WATCHLIST,
    CollectionApplicationService,
    ScoringApplicationService,
)
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
)
from portfolio.exceptions import PortfolioError
from portfolio.loader import load_portfolio_csv
from portfolio.pipeline import (
    build_portfolio_intelligence,
    write_portfolio_report,
)
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy, load_sell_rules_policy
from ranking import RankingReport
from reports.atlas_report.context import build_report_context
from reports.atlas_report.one_pager import (
    compute_symbol_contributions,
    render_one_pager,
)
from reports.atlas_report.render import page_shell, render_report
from reports.atlas_report.write import write_one_pager, write_report
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
from scoring.investment import load_yaml
from scoring.reference import ScoringReference
from storage.history_db import HistoryDatabase
from universe import UniverseReport
from watchlist import (
    WatchlistError,
    WatchlistReport,
    attach_aging,
    evaluate_watchlist_triggers,
    load_watchlist_csv,
    normalize_current_row,
    write_watchlist_report,
)


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
    """
    Lê STATUS.md só para extrair os alertas de conflito de motor exibidos
    no Diagnóstico do relatório -- se o arquivo não existir, o relatório
    simplesmente não mostra alertas (nunca quebra o run por isso).
    """
    status_path = ROOT / "STATUS.md"
    try:
        return status_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_settings() -> dict:
    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {settings_path}"
        )

    return json.loads(
        settings_path.read_text(encoding="utf-8")
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
    with HistoryDatabase(HISTORY_DATABASE) as database:
        database.save_snapshot(
            df=df,
            snapshot_date=snapshot_date,
            model_version=model_version,
        )

    logger.info(
        "Snapshot histórico salvo em %s (model_version=%s).",
        snapshot_date,
        model_version,
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
    if not settings.get("performance_validation_enabled", True):
        logger.info("Performance Validation desabilitado.")
        return None

    report = build_performance_validation_report(
        df,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
        snapshot_date=snapshot_date,
    )

    path = write_performance_validation_report(
        report,
        PERFORMANCE_VALIDATION_FILE,
    )

    logger.info(
        "Performance Validation gerado em %s.",
        path,
    )

    return path


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
    rebalance_actions: tuple = ()

    if portfolio_report is not None:
        weights_by_symbol = dict(
            portfolio_report.allocation.get("by_symbol", {})
        )
        held_symbols = frozenset(weights_by_symbol)
        rebalance_actions = tuple(
            portfolio_report.rebalance.get("actions", ())
        )

    sell = build_sell_priority(
        ranking_report.to_dict()["companies"] if ranking_report else (),
        rebalance_actions=rebalance_actions,
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
        OUTPUT_REPORTS,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
        database_path=HISTORY_DATABASE,
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
    *,
    sell_rules_policy: SellRulesPolicy | None = None,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
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

    # Nota: build_portfolio_intelligence nunca mais propaga
    # SellEngineBlockedError -- quando o motor de venda recusa decidir (tese
    # ausente), ele mesmo substitui o plano por REVISAR por holding, sem
    # suprimir score/qualidade/alocação (ver portfolio.pipeline
    # ::_build_blocked_rebalance_plan). O aviso do bloqueio já chega ao
    # usuário via PortfolioReport.warnings (linha "Portfolio" no resumo do
    # console + seção Carteira do relatório HTML).
    report = build_portfolio_intelligence(
        portfolio_path,
        df,
        portfolio_name=settings.get("portfolio_name"),
        cash=float(settings.get("portfolio_cash", 0.0)),
        currency=settings.get("portfolio_currency", "BRL"),
        rebalance_mode=settings.get(
            "portfolio_rebalance_mode", "sell_only"
        ),
        sell_rules_policy=sell_rules_policy,
        previous_by_symbol=previous_by_symbol,
        baseline_status=baseline_status,
        previous_run_at=previous_run_at,
        current_run_at=current_run_at,
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


def generate_watchlist_report(
    df: pd.DataFrame,
    settings: dict,
    *,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
) -> tuple[Path, WatchlistReport] | None:
    """
    Independente do motor de venda estar bloqueado: watchlist tracking é uma
    preocupação separada de PR-020, nunca acoplada ao estado da carteira.
    """
    watchlist_path = ROOT / settings.get(
        "watchlist_path", "config/watchlist.csv"
    )

    if not watchlist_path.exists():
        logger.info(
            "Watchlist tracking ignorado: arquivo não encontrado em %s.",
            watchlist_path,
        )
        return None

    try:
        entries = load_watchlist_csv(watchlist_path)
    except WatchlistError as exc:
        logger.warning(
            "Não foi possível avaliar triggers da watchlist: %s",
            exc,
        )
        return None

    current_by_symbol = {
        str(row.get("symbol", "")).strip().upper(): normalize_current_row(
            row.to_dict()
        )
        for _, row in df.iterrows()
        if str(row.get("symbol", "")).strip()
    }

    results = evaluate_watchlist_triggers(
        entries,
        current_by_symbol,
        previous_by_symbol=previous_by_symbol,
        baseline_status=baseline_status,
        previous_run_at=previous_run_at,
        current_run_at=current_run_at,
    )

    aging_threshold_days = int(
        settings.get("watchlist_aging_threshold_days", 180)
    )
    last_triggered_value = (
        str(current_run_at)
        if current_run_at is not None
        else datetime.now().isoformat(timespec="seconds")
    )

    with HistoryDatabase(HISTORY_DATABASE) as database:
        trigger_history = database.load_watchlist_triggers()
        results = attach_aging(
            results,
            entries,
            trigger_history=trigger_history,
            aging_threshold_days=aging_threshold_days,
        )
        for result in results:
            if result.triggered_this_run:
                database.save_watchlist_trigger(
                    result.symbol,
                    result.trigger_condition,
                    last_triggered_value,
                )

    report = WatchlistReport(results=results)
    report_path = write_watchlist_report(report, WATCHLIST_REPORT_FILE)

    logger.info(
        "Watchlist tracking: %s trigger(s) disparado(s); %s sugestão(ões) "
        "de limpeza.",
        len(report.triggered),
        len(report.cleanup_candidates),
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
        "Score Band",
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


def run_ticker_mode(symbol: str, settings: dict) -> Path:
    """
    Modo --ticker SYM: gera o one-pager de um símbolo (decomposição de
    score + histórico + tese, se for uma posição real).

    O símbolo é pontuado contra a última distribuição oficial do mercado
    amplo elegível. A watchlist não participa do denominador e, portanto,
    adicionar ou remover um ticker dela não altera este score.
    """
    symbol = symbol.strip().upper()
    logger.info("Modo --ticker: analisando %s contra a referência ampla.", symbol)
    scoring_reference = load_official_scoring_reference(settings)
    analysis_universe = pd.DataFrame(
        [{"symbol": symbol, "name": symbol, "origin": "ticker"}]
    )
    df = collect_market_data(settings, analysis_universe)
    df = build_scores(df, scoring_reference)

    symbol_rows = df.index[
        df["symbol"].astype(str).str.strip().str.upper() == symbol
    ]
    if len(symbol_rows) == 0:
        raise RuntimeError(
            f"Não foi possível coletar dados de mercado para {symbol}."
        )
    position = symbol_rows[0]

    investment_score = None
    if "Investment Score" in df.columns:
        try:
            investment_score = float(df.loc[position, "Investment Score"])
        except (TypeError, ValueError):
            investment_score = None

    positive, negative = compute_symbol_contributions(
        df,
        symbol,
        CONFIG / "features.yaml",
        CONFIG / "model.yaml",
    )

    score_history = load_score_history(HISTORY_DATABASE)
    if not score_history.empty and "symbol" in score_history.columns:
        score_history = score_history.loc[
            score_history["symbol"].astype(str).str.upper() == symbol
        ]

    thesis = ""
    portfolio_path = ROOT / settings.get("portfolio_path", "config/portfolio.csv")
    if portfolio_path.exists():
        try:
            holding = load_portfolio_csv(portfolio_path).holding(symbol)
            if holding is not None:
                thesis = holding.thesis
        except PortfolioError:
            logger.warning(
                "Não foi possível ler %s para buscar a tese de %s.",
                portfolio_path,
                symbol,
            )

    company_name = str(df.loc[position].get("name", "") or "").strip() or symbol
    body = render_one_pager(
        symbol=symbol,
        company_name=company_name,
        investment_score=investment_score,
        positive=positive,
        negative=negative,
        score_history=score_history,
        thesis=thesis,
    )
    html = page_shell(f"Atlas One-Pager — {symbol}", body)

    date_stamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    path = write_one_pager(html, OUTPUT_REPORTS, symbol, date_stamp)
    print(f"One-pager de {symbol} gerado em {path}")
    logger.info("One-pager de %s gerado em %s.", symbol, path)
    return path


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
    return PipelineServices(
        runtime=RuntimeServices(
            paths=paths,
            logger=logger,
            _run_health_check=run_health_check,
            _print_health_report=print_health_report,
            _load_settings=load_settings,
            _read_status_md=_read_status_md,
            _print_console_table=print_console_table,
            _safe_console_text=_safe_console_text,
            _save_execution_metrics=save_execution_metrics,
            _print_execution_metrics=print_execution_metrics,
            _run_ticker_mode=run_ticker_mode,
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
            _load_model_config=load_yaml,
            _load_score_history=load_score_history,
            _previous_run_context=previous_run_context,
            _load_sell_rules_policy=load_sell_rules_policy,
            _load_portfolio=load_portfolio_csv,
            _save_history_snapshot=save_history_snapshot,
            _save_outcome_decisions=save_outcome_decisions,
            _evaluate_outcome_decisions=evaluate_outcome_decisions,
            _generate_outcome_analytics=generate_outcome_analytics,
        ),
        intelligence=IntelligenceServices(
            paths=paths,
            _generate_portfolio_intelligence=generate_portfolio_intelligence,
            _generate_watchlist_report=generate_watchlist_report,
            _build_report_context=build_report_context,
            _render_report=render_report,
            _write_report=write_report,
        ),
        reporting=ReportingServices(
            _generate_excel_reports=generate_excel_reports,
            _generate_morning_brief=generate_morning_brief,
            _generate_priority_report=generate_priority_report,
            _generate_performance_validation=generate_performance_validation,
            _generate_dashboard=generate_dashboard,
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

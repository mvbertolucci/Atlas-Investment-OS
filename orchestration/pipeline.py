from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar, cast

import pandas as pd

from metrics.execution import ExecutionMetrics, StageTimer
from outcomes.analytics import OutcomeAnalyticsReport
from outcomes.pipeline import OutcomeCaptureResult, OutcomeEvaluationResult
from portfolio.exceptions import PortfolioError
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy
from priority import PriorityReport
from ranking import RankingReport
from reports.atlas_report.context import ReportContext
from scoring.reference import ScoringReference
from universe import UniverseReport
from watchlist.auto_curation import AutoCurationResult
from watchlist.models import WatchlistReport

from orchestration.services import PipelineServices


PipelineMode = Literal["full", "portfolio", "ticker"]
ArtifactT = TypeVar("ArtifactT")


@dataclass(frozen=True)
class PipelineRequest:
    mode: PipelineMode
    ticker: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"full", "portfolio", "ticker"}:
            raise ValueError(f"Modo de pipeline inválido: {self.mode}.")
        if self.mode == "ticker" and not str(self.ticker or "").strip():
            raise ValueError("O modo ticker exige um símbolo.")
        if self.mode != "ticker" and self.ticker is not None:
            raise ValueError("ticker só pode ser informado no modo ticker.")


@dataclass
class PipelineContext:
    request: PipelineRequest
    services: PipelineServices
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    _artifacts: dict[type[Any], Any] = field(default_factory=dict, repr=False)

    def publish(self, artifact: ArtifactT) -> ArtifactT:
        artifact_type = type(artifact)
        if artifact_type in self._artifacts:
            raise RuntimeError(
                f"Artefato {artifact_type.__name__} já foi publicado."
            )
        self._artifacts[artifact_type] = artifact
        return artifact

    def require(self, artifact_type: type[ArtifactT]) -> ArtifactT:
        if artifact_type not in self._artifacts:
            raise RuntimeError(
                f"Artefato obrigatório ausente: {artifact_type.__name__}."
            )
        return cast(ArtifactT, self._artifacts[artifact_type])


@dataclass(frozen=True)
class BootstrapOutput:
    settings: dict[str, Any]
    scoring_reference: ScoringReference | None
    watchlist_path: Path
    watchlist: pd.DataFrame
    analysis_universe: pd.DataFrame


@dataclass(frozen=True)
class CollectionOutput:
    frame: pd.DataFrame
    fetch_failures: tuple[str, ...]


@dataclass(frozen=True)
class ScoringOutput:
    frame: pd.DataFrame
    feature_coverage_summary: dict[str, Any]
    universe_report: UniverseReport | None
    ranking_report: RankingReport | None
    broad_market_report_path: Path | None
    adr_report_path: Path | None
    research_ranking_report_path: Path | None = None


@dataclass(frozen=True)
class HistoricalContextOutput:
    frame: pd.DataFrame
    run_at: datetime
    snapshot_date: str
    model_version: str
    score_history: pd.DataFrame
    previous_by_symbol: dict[str, Any]
    baseline_status: str
    previous_run_at: pd.Timestamp | None
    sell_rules_policy: SellRulesPolicy


@dataclass(frozen=True)
class PersistenceOutput:
    outcome_capture: OutcomeCaptureResult | None
    outcome_evaluation: OutcomeEvaluationResult | None
    outcome_analytics: OutcomeAnalyticsReport | None


@dataclass(frozen=True)
class IntelligenceOutput:
    portfolio_result: tuple[Path, PortfolioReport] | None
    portfolio_report: PortfolioReport | None
    watchlist_result: tuple[Path, WatchlistReport] | None
    watchlist_report: WatchlistReport | None
    report_context: ReportContext
    atlas_report_dated: Path
    atlas_report_latest: Path
    watchlist_auto_curation: AutoCurationResult | None = None
    opportunity_funnel_path: Path | None = None


@dataclass(frozen=True)
class ReportsOutput:
    history_file: Path
    latest_file: Path | None
    brief_file: Path
    brief_text: str
    priority_file: Path | None
    priority_report: PriorityReport | None
    performance_validation_file: Path | None
    dashboard_file: Path | None


@dataclass(frozen=True)
class TickerOutput:
    report_path: Path


@dataclass(frozen=True)
class CompletionOutput:
    snapshot_date: str | None


OutputT = TypeVar("OutputT")


class PipelineStage(Protocol, Generic[OutputT]):
    name: str
    requires: tuple[type[Any], ...]
    output_type: type[OutputT]

    def run(self, context: PipelineContext) -> OutputT: ...


@dataclass(frozen=True)
class PipelineRunner:
    stages: tuple[PipelineStage[Any], ...]

    def run(self, context: PipelineContext) -> PipelineContext:
        for stage in self.stages:
            for required in stage.requires:
                context.require(required)
            output = stage.run(context)
            if not isinstance(output, stage.output_type):
                raise TypeError(
                    f"Estágio {stage.name} retornou {type(output).__name__}; "
                    f"esperado {stage.output_type.__name__}."
                )
            context.publish(output)
        return context


class BootstrapStage:
    name = "bootstrap"
    requires = ()
    output_type = BootstrapOutput

    def run(self, context: PipelineContext) -> BootstrapOutput:
        services = context.services
        runtime = services.runtime
        health_report = runtime.run_health_check()
        runtime.print_health_report(health_report)
        settings = runtime.load_settings()
        scoring_reference = services.scoring.load_official_reference(settings)
        watchlist_path, watchlist = services.collection.load_watchlist(settings)
        analysis_universe = services.collection.merge_watchlist_with_portfolio(
            watchlist, settings
        )

        print()
        print("=" * 70)
        print("ATLAS DECISION INTELLIGENCE PLATFORM")
        print("=" * 70)
        print(f"Watchlist       : {watchlist_path}")
        if len(analysis_universe) != len(watchlist):
            print(
                f"Carteira        : +{len(analysis_universe) - len(watchlist)} "
                "símbolo(s) da carteira real incluído(s) só nesta análise "
                "(watchlist.csv não é alterado)"
            )
        print(f"History DB      : {runtime.paths.history_database}")
        print(f"Execution log   : {runtime.paths.logs / 'atlas.log'}")
        print()
        return BootstrapOutput(
            settings=settings,
            scoring_reference=scoring_reference,
            watchlist_path=watchlist_path,
            watchlist=watchlist,
            analysis_universe=analysis_universe,
        )


class CollectionStage:
    name = "collection"
    requires = (BootstrapOutput,)
    output_type = CollectionOutput

    def run(self, context: PipelineContext) -> CollectionOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        failures: list[str] = []
        with StageTimer(context.metrics, "download_time"):
            frame = services.collection.collect_market_data(
                bootstrap.settings,
                bootstrap.analysis_universe,
                failures=failures,
            )
        context.metrics.companies = len(frame)
        return CollectionOutput(frame=frame, fetch_failures=tuple(failures))


class ScoringStage:
    name = "scoring"
    requires = (BootstrapOutput, CollectionOutput)
    output_type = ScoringOutput

    def run(self, context: PipelineContext) -> ScoringOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        collection = context.require(CollectionOutput)
        with StageTimer(context.metrics, "scoring_time"):
            frame = services.scoring.build_scores(
                collection.frame,
                bootstrap.scoring_reference,
            )
        coverage = services.scoring.audit_feature_coverage(frame)
        if context.request.mode == "full":
            universe_report = services.scoring.generate_universe_report(
                frame, bootstrap.settings
            )
            ranking_report = services.scoring.generate_ranking_report(
                frame, bootstrap.settings, universe_report
            )
            broad_path = (
                services.scoring.paths.output_data
                / "research_ranking_report_market.json"
            )
            adr_path = (
                services.scoring.paths.output_data
                / "research_ranking_report_adr.json"
            )
            sp500_path = (
                services.scoring.paths.output_data
                / "research_ranking_report.json"
            )
        else:
            universe_report = ranking_report = None
            broad_path = adr_path = sp500_path = None
        return ScoringOutput(
            frame=frame,
            feature_coverage_summary=coverage,
            universe_report=universe_report,
            ranking_report=ranking_report,
            broad_market_report_path=broad_path,
            adr_report_path=adr_path,
            research_ranking_report_path=sp500_path,
        )


class HistoricalContextStage:
    name = "historical_context"
    requires = (BootstrapOutput, ScoringOutput)
    output_type = HistoricalContextOutput

    def run(self, context: PipelineContext) -> HistoricalContextOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        scoring = context.require(ScoringOutput)
        history_services = services.history
        frame = scoring.frame.copy()
        run_at = datetime.now()
        snapshot_date = run_at.isoformat(timespec="seconds")
        model_version = (
            str(
                history_services.load_model_config().get("model_version", "legacy")
            ).strip()
            or "legacy"
        )
        score_history = history_services.load_score_history()
        previous_by_symbol, baseline_status, previous_run_at = (
            history_services.previous_run_context(
                score_history,
                current_snapshot_date=snapshot_date,
                current_model_version=model_version,
            )
        )
        sell_rules_policy = history_services.load_sell_rules_policy()

        portfolio_path = history_services.portfolio_path(bootstrap.settings)
        if portfolio_path.exists():
            try:
                quantity_by_symbol = {
                    holding.symbol: holding.quantity
                    for holding in history_services.load_portfolio(
                        portfolio_path
                    ).holdings
                }
                frame["quantity"] = (
                    frame["symbol"].astype(str).str.strip().str.upper().map(
                        quantity_by_symbol
                    )
                )
            except PortfolioError:
                history_services.logger.warning(
                    "Não foi possível ler %s para anexar quantity ao "
                    "snapshot histórico.",
                    portfolio_path,
                )

        if scoring.ranking_report is not None:
            candidate_by_symbol = {
                company.symbol: bool(
                    company.safeguard_passed
                    and company.candidate_rank is not None
                )
                for company in scoring.ranking_report.companies
            }
            frame["is_candidate"] = (
                frame["symbol"].astype(str).str.strip().str.upper().map(
                    candidate_by_symbol
                )
            )
        return HistoricalContextOutput(
            frame=frame,
            run_at=run_at,
            snapshot_date=snapshot_date,
            model_version=model_version,
            score_history=score_history,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            sell_rules_policy=sell_rules_policy,
        )


class PersistenceStage:
    name = "persistence"
    requires = (BootstrapOutput, HistoricalContextOutput)
    output_type = PersistenceOutput

    def run(self, context: PipelineContext) -> PersistenceOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        historical = context.require(HistoricalContextOutput)
        history_services = services.history
        with StageTimer(context.metrics, "history_time"):
            history_services.save_history_snapshot(
                historical.frame,
                historical.snapshot_date,
                historical.model_version,
            )
            capture = history_services.save_outcome_decisions(
                historical.frame,
                historical.snapshot_date,
                bootstrap.settings,
            )
            evaluation = history_services.evaluate_outcome_decisions(
                historical.frame,
                historical.snapshot_date,
                bootstrap.settings,
            )
            analytics = history_services.generate_outcome_analytics(
                bootstrap.settings
            )
        return PersistenceOutput(capture, evaluation, analytics)


class IntelligenceStage:
    name = "intelligence"
    requires = (
        BootstrapOutput,
        CollectionOutput,
        ScoringOutput,
        HistoricalContextOutput,
        PersistenceOutput,
    )
    output_type = IntelligenceOutput

    def run(self, context: PipelineContext) -> IntelligenceOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        collection = context.require(CollectionOutput)
        scoring = context.require(ScoringOutput)
        historical = context.require(HistoricalContextOutput)
        persistence = context.require(PersistenceOutput)
        intelligence_services = services.intelligence
        portfolio_result = intelligence_services.generate_portfolio_intelligence(
            historical.frame,
            bootstrap.settings,
            sell_rules_policy=historical.sell_rules_policy,
            previous_by_symbol=historical.previous_by_symbol,
            baseline_status=historical.baseline_status,
            previous_run_at=historical.previous_run_at,
            current_run_at=historical.snapshot_date,
        )
        portfolio_report = portfolio_result[1] if portfolio_result else None
        opportunity_funnel_path = intelligence_services.generate_opportunity_funnel(
            historical.frame,
            bootstrap.settings,
            sp500_report_path=scoring.research_ranking_report_path,
            broad_market_report_path=scoring.broad_market_report_path,
            adr_report_path=scoring.adr_report_path,
        )
        watchlist_auto_curation = (
            intelligence_services.run_watchlist_auto_curation(
                historical.frame,
                bootstrap.settings,
                sp500_report_path=scoring.research_ranking_report_path,
                broad_market_report_path=scoring.broad_market_report_path,
                adr_report_path=scoring.adr_report_path,
            )
        )
        watchlist_result = intelligence_services.generate_watchlist_report(
            historical.frame,
            bootstrap.settings,
            previous_by_symbol=historical.previous_by_symbol,
            baseline_status=historical.baseline_status,
            previous_run_at=historical.previous_run_at,
            current_run_at=historical.snapshot_date,
            auto_curation=watchlist_auto_curation,
        )
        watchlist_report = watchlist_result[1] if watchlist_result else None
        report_context = intelligence_services.build_report_context(
            mode=context.request.mode,
            df=historical.frame,
            snapshot_date=historical.snapshot_date,
            previous_run_at=historical.previous_run_at,
            baseline_status=historical.baseline_status,
            previous_by_symbol=historical.previous_by_symbol,
            rebalance=(portfolio_report.rebalance if portfolio_report else None),
            portfolio_warnings=(
                portfolio_report.warnings if portfolio_report else ()
            ),
            watchlist_report=watchlist_report,
            ranking_report=scoring.ranking_report,
            universe_report=scoring.universe_report,
            fetch_failures=collection.fetch_failures,
            phantom_weight_pct=scoring.feature_coverage_summary.get(
                "phantom_investment_share", 0.0
            ),
            status_md_text=intelligence_services.read_status_md(),
            holdings=(portfolio_report.holdings if portfolio_report else ()),
            score_history=historical.score_history,
            features_path=intelligence_services.paths.config / "features.yaml",
            model_path=intelligence_services.paths.config / "model.yaml",
            broad_market_report_path=scoring.broad_market_report_path,
            adr_report_path=scoring.adr_report_path,
        )
        dated, latest = intelligence_services.render_and_write_report(
            report_context,
            historical.run_at.strftime("%Y-%m-%d"),
        )
        return IntelligenceOutput(
            portfolio_result=portfolio_result,
            portfolio_report=portfolio_report,
            watchlist_result=watchlist_result,
            watchlist_report=watchlist_report,
            report_context=report_context,
            atlas_report_dated=dated,
            atlas_report_latest=latest,
            watchlist_auto_curation=watchlist_auto_curation,
            opportunity_funnel_path=opportunity_funnel_path,
        )


class ReportsStage:
    name = "reports"
    requires = (
        BootstrapOutput,
        ScoringOutput,
        HistoricalContextOutput,
        PersistenceOutput,
        IntelligenceOutput,
    )
    output_type = ReportsOutput

    def run(self, context: PipelineContext) -> ReportsOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        scoring = context.require(ScoringOutput)
        historical = context.require(HistoricalContextOutput)
        persistence = context.require(PersistenceOutput)
        intelligence = context.require(IntelligenceOutput)
        reporting = services.reporting
        with StageTimer(context.metrics, "reports_time"):
            history_file, latest_file = reporting.generate_excel_reports(
                historical.frame,
                portfolio_report=intelligence.portfolio_report,
                outcome_report=persistence.outcome_analytics,
            )
        with StageTimer(context.metrics, "morning_brief_time"):
            brief_file, brief_text = reporting.generate_morning_brief(
                historical.frame,
                portfolio_report=intelligence.portfolio_report,
                outcome_report=persistence.outcome_analytics,
            )
        priority_result = reporting.generate_priority_report(
            bootstrap.settings,
            ranking_report=scoring.ranking_report,
            portfolio_report=intelligence.portfolio_report,
        )
        priority_file, priority_report = (
            priority_result if priority_result else (None, None)
        )
        performance_file = reporting.generate_performance_validation(
            historical.frame,
            bootstrap.settings,
            portfolio_report=intelligence.portfolio_report,
            outcome_report=persistence.outcome_analytics,
            snapshot_date=historical.snapshot_date,
        )
        dashboard_file = reporting.generate_dashboard(
            historical.frame,
            bootstrap.settings,
            portfolio_report=intelligence.portfolio_report,
            outcome_report=persistence.outcome_analytics,
            universe_report=scoring.universe_report,
            priority_report=priority_report,
        )
        return ReportsOutput(
            history_file=history_file,
            latest_file=latest_file,
            brief_file=brief_file,
            brief_text=brief_text,
            priority_file=priority_file,
            priority_report=priority_report,
            performance_validation_file=performance_file,
            dashboard_file=dashboard_file,
        )


class CompletionStage:
    name = "completion"
    requires = (
        BootstrapOutput,
        ScoringOutput,
        HistoricalContextOutput,
        PersistenceOutput,
        IntelligenceOutput,
        ReportsOutput,
    )
    output_type = CompletionOutput

    def run(self, context: PipelineContext) -> CompletionOutput:
        services = context.services
        bootstrap = context.require(BootstrapOutput)
        scoring = context.require(ScoringOutput)
        historical = context.require(HistoricalContextOutput)
        persistence = context.require(PersistenceOutput)
        intelligence = context.require(IntelligenceOutput)
        reports = context.require(ReportsOutput)
        runtime = services.runtime
        paths = runtime.paths

        runtime.print_console_table(historical.frame)
        print(runtime.safe_console_text(reports.brief_text))
        print()
        print("=" * 70)
        print("ARQUIVOS GERADOS")
        print("=" * 70)
        print(f"Snapshot        : {historical.snapshot_date}")
        print(f"SQLite          : {paths.history_database}")
        print(f"Excel histórico : {reports.history_file}")
        print(
            f"Latest.xlsx     : {reports.latest_file}"
            if reports.latest_file is not None
            else "Latest.xlsx     : não atualizado (arquivo provavelmente aberto)"
        )
        print(f"Morning Brief   : {reports.brief_file}")
        if persistence.outcome_capture is not None:
            capture = persistence.outcome_capture
            print(
                "Outcome Captures: "
                f"{capture.saved_count} "
                f"({', '.join(map(str, capture.horizons_days))} dias)"
            )
            if capture.skipped_symbols:
                print("Outcome Skipped : " + ", ".join(capture.skipped_symbols))
        if persistence.outcome_evaluation is not None:
            evaluation = persistence.outcome_evaluation
            print(
                "Outcome Results : "
                f"{evaluation.evaluated_count} avaliados; "
                f"{evaluation.pending_count} pendentes"
            )
            if evaluation.missing_price_symbols:
                print(
                    "Outcome Prices  : ausentes para "
                    + ", ".join(evaluation.missing_price_symbols)
                )
        if persistence.outcome_analytics is not None:
            hit_rate = persistence.outcome_analytics.hit_rate
            shown = hit_rate.hit_rate if hit_rate.hit_rate is not None else "-"
            print(
                f"Outcome Hit Rate: {shown}% "
                f"({hit_rate.hit_count}/{hit_rate.eligible_count})"
            )
            print(f"Outcome JSON    : {paths.outcome_report_file}")
        if reports.dashboard_file is not None:
            print(f"Dashboard JSON  : {reports.dashboard_file}")
        if reports.priority_file is not None:
            print(f"Priority JSON   : {reports.priority_file}")
        if reports.performance_validation_file is not None:
            print(f"Validation JSON : {reports.performance_validation_file}")
        if scoring.universe_report is not None:
            universe = scoring.universe_report
            print(f"Universe JSON   : {paths.universe_report_file}")
            print(
                f"Universe        : {universe.eligible_count}/{universe.total_count} "
                f"elegíveis; cobertura {universe.average_data_coverage_pct}%"
            )
        if scoring.ranking_report is not None:
            ranking = scoring.ranking_report
            print(f"Ranking JSON    : {paths.ranking_report_file}")
            print(
                f"Ranking         : {ranking.candidate_count}/"
                f"{ranking.total_count} candidatos"
            )
        if intelligence.portfolio_result is not None:
            portfolio_file, portfolio = intelligence.portfolio_result
            print(f"Portfolio JSON  : {portfolio_file}")
            print(
                f"Portfolio Score : {portfolio.summary.get('quality_score')} "
                f"({portfolio.summary.get('quality_rating')})"
            )
            if any(
                warning.startswith("Motor de venda bloqueado")
                for warning in portfolio.warnings
            ):
                print(
                    "Portfolio       : motor de venda bloqueado -- "
                    "posição(ões) sem tese (ver aviso acima)"
                )
        else:
            print(
                "Portfolio       : não executado "
                "(config/portfolio.csv ausente)"
            )
        if intelligence.watchlist_result is not None:
            watchlist_file, watchlist = intelligence.watchlist_result
            print(f"Watchlist JSON  : {watchlist_file}")
            print(
                f"Watchlist       : {len(watchlist.triggered)} trigger(s) "
                f"disparado(s); {len(watchlist.cleanup_candidates)} "
                "sugestão(ões) de limpeza"
            )
            for triggered in watchlist.triggered:
                print(f"  [TRIGGER] {triggered.symbol} -- {triggered.message}")
            for candidate in watchlist.cleanup_candidates:
                print(
                    f"  [LIMPEZA?] {candidate.symbol} -- {candidate.age_days} "
                    "dias sem trigger"
                )
        auto_curation = intelligence.watchlist_auto_curation
        if auto_curation is not None and auto_curation.enabled:
            print(
                f"Watchlist Auto  : +{len(auto_curation.included)} "
                f"incluído(s), -{len(auto_curation.excluded)} removido(s)"
            )
            for item in auto_curation.included:
                print(f"  [AUTO-IN]  {item.symbol} -- {item.note}")
            for item in auto_curation.excluded:
                print(f"  [AUTO-OUT] {item.symbol} -- {item.reason}")
        print(f"Atlas Report    : {intelligence.atlas_report_dated}")
        print(f"Atlas Latest    : {intelligence.atlas_report_latest}")
        print("=" * 70)
        runtime.save_execution_metrics(context.metrics)
        runtime.print_execution_metrics(context.metrics)
        runtime.logger.info(
            "Atlas concluído com sucesso em %.2f segundos.",
            context.metrics.total_time(),
        )
        print(f"Métricas salvas : {paths.execution_metrics_file}")
        print()
        print("Atlas finalizado com sucesso.")
        return CompletionOutput(snapshot_date=historical.snapshot_date)


class TickerStage:
    name = "ticker"
    requires = ()
    output_type = TickerOutput

    def run(self, context: PipelineContext) -> TickerOutput:
        runtime = context.services.runtime
        settings = runtime.load_settings()
        path = context.services.ticker.run_ticker_mode(
            str(context.request.ticker), settings
        )
        return TickerOutput(path)


def build_pipeline(mode: PipelineMode) -> PipelineRunner:
    if mode not in {"full", "portfolio", "ticker"}:
        raise ValueError(f"Modo de pipeline inválido: {mode}.")
    if mode == "ticker":
        return PipelineRunner((TickerStage(),))
    return PipelineRunner(
        (
            BootstrapStage(),
            CollectionStage(),
            ScoringStage(),
            HistoricalContextStage(),
            PersistenceStage(),
            IntelligenceStage(),
            ReportsStage(),
            CompletionStage(),
        )
    )


def parse_pipeline_request(argv: list[str] | None = None) -> PipelineRequest:
    parser = argparse.ArgumentParser(
        description="Atlas Decision Intelligence Platform."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Universo + funil + carteira + watchlist (default).",
    )
    mode_group.add_argument(
        "--portfolio",
        action="store_true",
        help="Só carteira + watchlist, sem funil de screener.",
    )
    parser.add_argument(
        "--ticker",
        metavar="SYM",
        default=None,
        help="Analisa só um símbolo e gera o one-pager (ex.: --ticker MSFT).",
    )
    args = parser.parse_args(argv)
    if args.ticker:
        return PipelineRequest("ticker", str(args.ticker).strip().upper())
    return PipelineRequest("portfolio" if args.portfolio else "full")

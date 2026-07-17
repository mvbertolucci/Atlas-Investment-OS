from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from health.health_check import HealthReport
from metrics.execution import ExecutionMetrics
from outcomes.analytics import OutcomeAnalyticsReport
from outcomes.pipeline import OutcomeCaptureResult, OutcomeEvaluationResult
from portfolio.models import Portfolio
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy
from priority import PriorityReport
from ranking import RankingReport
from reports.atlas_report.context import ReportContext
from scoring.reference import ScoringReference
from universe import UniverseReport
from watchlist.models import WatchlistReport


Settings = dict[str, Any]
PreviousBySymbol = dict[str, dict[str, object]]


class Logger(Protocol):
    def info(self, message: str, *args: object) -> None: ...

    def warning(self, message: str, *args: object) -> None: ...


@dataclass(frozen=True)
class PipelinePaths:
    root: Path
    config: Path
    logs: Path
    output_data: Path
    output_reports: Path
    history_database: Path
    execution_metrics_file: Path
    outcome_report_file: Path
    universe_report_file: Path
    ranking_report_file: Path


@dataclass(frozen=True)
class RuntimeServices:
    paths: PipelinePaths
    logger: Logger
    _run_health_check: Callable[[Path], HealthReport]
    _print_health_report: Callable[[HealthReport], None]
    _load_settings: Callable[[], Settings]
    _read_status_md: Callable[[], str]
    _print_console_table: Callable[[pd.DataFrame], None]
    _safe_console_text: Callable[[object, str | None], str]
    _save_execution_metrics: Callable[[ExecutionMetrics, Path], None]
    _print_execution_metrics: Callable[[ExecutionMetrics], None]
    _run_ticker_mode: Callable[[str, Settings], Path]

    def run_health_check(self) -> HealthReport:
        return self._run_health_check(self.paths.root)

    def print_health_report(self, report: HealthReport) -> None:
        self._print_health_report(report)

    def load_settings(self) -> Settings:
        return self._load_settings()

    def read_status_md(self) -> str:
        return self._read_status_md()

    def print_console_table(self, frame: pd.DataFrame) -> None:
        self._print_console_table(frame)

    def safe_console_text(
        self, value: object, encoding: str | None = None
    ) -> str:
        return self._safe_console_text(value, encoding)

    def save_execution_metrics(self, metrics: ExecutionMetrics) -> None:
        self._save_execution_metrics(metrics, self.paths.execution_metrics_file)

    def print_execution_metrics(self, metrics: ExecutionMetrics) -> None:
        self._print_execution_metrics(metrics)

    def run_ticker_mode(self, symbol: str, settings: Settings) -> Path:
        return self._run_ticker_mode(symbol, settings)


@dataclass(frozen=True)
class CollectionServices:
    _load_watchlist: Callable[[Settings], tuple[Path, pd.DataFrame]]
    _merge_watchlist_with_portfolio: Callable[
        [pd.DataFrame, Settings], pd.DataFrame
    ]
    _collect_market_data: Callable[..., pd.DataFrame]

    def load_watchlist(self, settings: Settings) -> tuple[Path, pd.DataFrame]:
        return self._load_watchlist(settings)

    def merge_watchlist_with_portfolio(
        self, watchlist: pd.DataFrame, settings: Settings
    ) -> pd.DataFrame:
        return self._merge_watchlist_with_portfolio(watchlist, settings)

    def collect_market_data(
        self,
        settings: Settings,
        analysis_universe: pd.DataFrame,
        *,
        failures: list[str],
    ) -> pd.DataFrame:
        return self._collect_market_data(
            settings, analysis_universe, failures=failures
        )


@dataclass(frozen=True)
class ScoringServices:
    paths: PipelinePaths
    _load_official_reference: Callable[[Settings], ScoringReference | None]
    _build_scores: Callable[
        [pd.DataFrame, ScoringReference | None], pd.DataFrame
    ]
    _audit_feature_coverage: Callable[[pd.DataFrame], dict[str, Any]]
    _generate_universe_report: Callable[
        [pd.DataFrame, Settings], UniverseReport | None
    ]
    _generate_ranking_report: Callable[
        [pd.DataFrame, Settings, UniverseReport | None], RankingReport | None
    ]

    def load_official_reference(
        self, settings: Settings
    ) -> ScoringReference | None:
        return self._load_official_reference(settings)

    def build_scores(
        self,
        frame: pd.DataFrame,
        reference: ScoringReference | None,
    ) -> pd.DataFrame:
        return self._build_scores(frame, reference)

    def audit_feature_coverage(
        self, frame: pd.DataFrame
    ) -> dict[str, Any]:
        return self._audit_feature_coverage(frame)

    def generate_universe_report(
        self, frame: pd.DataFrame, settings: Settings
    ) -> UniverseReport | None:
        return self._generate_universe_report(frame, settings)

    def generate_ranking_report(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        universe_report: UniverseReport | None,
    ) -> RankingReport | None:
        return self._generate_ranking_report(
            frame, settings, universe_report
        )


@dataclass(frozen=True)
class HistoryServices:
    paths: PipelinePaths
    logger: Logger
    _load_model_config: Callable[[Path], dict[str, Any]]
    _load_score_history: Callable[[Path], pd.DataFrame]
    _previous_run_context: Callable[..., tuple[PreviousBySymbol, str, Any]]
    _load_sell_rules_policy: Callable[[Path], SellRulesPolicy]
    _load_portfolio: Callable[[Path], Portfolio]
    _save_history_snapshot: Callable[[pd.DataFrame, str, str], str]
    _save_outcome_decisions: Callable[
        [pd.DataFrame, str, Settings], OutcomeCaptureResult | None
    ]
    _evaluate_outcome_decisions: Callable[
        [pd.DataFrame, str, Settings], OutcomeEvaluationResult | None
    ]
    _generate_outcome_analytics: Callable[
        [Settings], OutcomeAnalyticsReport | None
    ]

    def load_model_config(self) -> dict[str, Any]:
        return self._load_model_config(self.paths.config / "model.yaml")

    def load_score_history(self) -> pd.DataFrame:
        return self._load_score_history(self.paths.history_database)

    def previous_run_context(
        self,
        history: pd.DataFrame,
        *,
        current_snapshot_date: str,
        current_model_version: str,
    ) -> tuple[PreviousBySymbol, str, pd.Timestamp | None]:
        return self._previous_run_context(
            history,
            current_snapshot_date=current_snapshot_date,
            current_model_version=current_model_version,
        )

    def load_sell_rules_policy(self) -> SellRulesPolicy:
        return self._load_sell_rules_policy(
            self.paths.config / "sell_rules.yaml"
        )

    def portfolio_path(self, settings: Settings) -> Path:
        return self.paths.root / settings.get(
            "portfolio_path", "config/portfolio.csv"
        )

    def load_portfolio(self, path: Path) -> Portfolio:
        return self._load_portfolio(path)

    def save_history_snapshot(
        self, frame: pd.DataFrame, snapshot_date: str, model_version: str
    ) -> str:
        return self._save_history_snapshot(
            frame, snapshot_date, model_version
        )

    def save_outcome_decisions(
        self, frame: pd.DataFrame, snapshot_date: str, settings: Settings
    ) -> OutcomeCaptureResult | None:
        return self._save_outcome_decisions(frame, snapshot_date, settings)

    def evaluate_outcome_decisions(
        self, frame: pd.DataFrame, snapshot_date: str, settings: Settings
    ) -> OutcomeEvaluationResult | None:
        return self._evaluate_outcome_decisions(
            frame, snapshot_date, settings
        )

    def generate_outcome_analytics(
        self, settings: Settings
    ) -> OutcomeAnalyticsReport | None:
        return self._generate_outcome_analytics(settings)


@dataclass(frozen=True)
class IntelligenceServices:
    paths: PipelinePaths
    _generate_portfolio_intelligence: Callable[..., tuple[Path, PortfolioReport] | None]
    _generate_watchlist_report: Callable[..., tuple[Path, WatchlistReport] | None]
    _build_report_context: Callable[..., ReportContext]
    _render_report: Callable[[ReportContext], str]
    _write_report: Callable[[str, Path, str], tuple[Path, Path]]

    def generate_portfolio_intelligence(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        sell_rules_policy: SellRulesPolicy,
        previous_by_symbol: PreviousBySymbol,
        baseline_status: str,
        previous_run_at: pd.Timestamp | None,
        current_run_at: str,
    ) -> tuple[Path, PortfolioReport] | None:
        return self._generate_portfolio_intelligence(
            frame,
            settings,
            sell_rules_policy=sell_rules_policy,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=current_run_at,
        )

    def generate_watchlist_report(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        previous_by_symbol: PreviousBySymbol,
        baseline_status: str,
        previous_run_at: pd.Timestamp | None,
        current_run_at: str,
    ) -> tuple[Path, WatchlistReport] | None:
        return self._generate_watchlist_report(
            frame,
            settings,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=current_run_at,
        )

    def build_report_context(self, **kwargs: Any) -> ReportContext:
        return self._build_report_context(**kwargs)

    def render_and_write_report(
        self, context: ReportContext, report_date: str
    ) -> tuple[Path, Path]:
        return self._write_report(
            self._render_report(context),
            self.paths.output_reports,
            report_date,
        )


@dataclass(frozen=True)
class ReportingServices:
    _generate_excel_reports: Callable[..., tuple[Path, Path | None]]
    _generate_morning_brief: Callable[..., tuple[Path, str]]
    _generate_priority_report: Callable[..., tuple[Path, PriorityReport] | None]
    _generate_performance_validation: Callable[..., Path | None]
    _generate_dashboard: Callable[..., Path | None]

    def generate_excel_reports(
        self,
        frame: pd.DataFrame,
        *,
        portfolio_report: PortfolioReport | None,
        outcome_report: OutcomeAnalyticsReport | None,
    ) -> tuple[Path, Path | None]:
        return self._generate_excel_reports(
            frame,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
        )

    def generate_morning_brief(
        self,
        frame: pd.DataFrame,
        *,
        portfolio_report: PortfolioReport | None,
        outcome_report: OutcomeAnalyticsReport | None,
    ) -> tuple[Path, str]:
        return self._generate_morning_brief(
            frame,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
        )

    def generate_priority_report(
        self,
        settings: Settings,
        *,
        ranking_report: RankingReport | None,
        portfolio_report: PortfolioReport | None,
    ) -> tuple[Path, PriorityReport] | None:
        return self._generate_priority_report(
            settings,
            ranking_report=ranking_report,
            portfolio_report=portfolio_report,
        )

    def generate_performance_validation(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        portfolio_report: PortfolioReport | None,
        outcome_report: OutcomeAnalyticsReport | None,
        snapshot_date: str,
    ) -> Path | None:
        return self._generate_performance_validation(
            frame,
            settings,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
            snapshot_date=snapshot_date,
        )

    def generate_dashboard(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        portfolio_report: PortfolioReport | None,
        outcome_report: OutcomeAnalyticsReport | None,
        universe_report: UniverseReport | None,
        priority_report: PriorityReport | None,
    ) -> Path | None:
        return self._generate_dashboard(
            frame,
            settings,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
            universe_report=universe_report,
            priority_report=priority_report,
        )


@dataclass(frozen=True)
class PipelineServices:
    runtime: RuntimeServices
    collection: CollectionServices
    scoring: ScoringServices
    history: HistoryServices
    intelligence: IntelligenceServices
    reporting: ReportingServices

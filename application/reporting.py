from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from analytics.performance_validation import (
    build_performance_validation_report,
    write_performance_validation_report,
)
from dashboard import build_dashboard_view, write_dashboard_view
from decision.queue import build_decision_queue, write_decision_queue
from outcomes.analytics import OutcomeAnalyticsReport
from portfolio.report import PortfolioReport
from priority import (
    PriorityReport,
    build_buy_priority,
    build_sell_priority,
    write_priority_report,
)
from ranking import RankingReport
from reports.excel import write_latest_and_history
from reports.morning_brief import render_morning_brief, write_morning_brief
from reports.report_engine import build_company_reports
from universe import UniverseReport
from watchlist.models import WatchlistReport


Settings = dict[str, Any]
MorningBriefWriter = Callable[..., Path]
MorningBriefRenderer = Callable[..., str]


@dataclass(frozen=True)
class ReportingApplicationService:
    output_reports: Path
    history_database: Path
    morning_brief_file: Path
    performance_validation_file: Path
    dashboard_report_file: Path
    priority_report_file: Path
    research_ranking_report_file: Path
    logger: logging.Logger
    morning_brief_writer: MorningBriefWriter = write_morning_brief
    morning_brief_renderer: MorningBriefRenderer = render_morning_brief

    def generate_performance_validation(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        portfolio_report: PortfolioReport | None = None,
        outcome_report: OutcomeAnalyticsReport | None = None,
        snapshot_date: str | None = None,
    ) -> Path | None:
        if not settings.get("performance_validation_enabled", True):
            self.logger.info("Performance Validation desabilitado.")
            return None

        validation_path = Path(
            settings.get(
                "portfolio_validation_report_path",
                self.performance_validation_file.parent
                / "portfolio_validation_report.json",
            )
        )
        portfolio_validation_report = None
        if validation_path.exists():
            try:
                portfolio_validation_report = json.loads(
                    validation_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                self.logger.warning(
                    "Relatório histórico ignorado (%s): %s",
                    validation_path,
                    exc,
                )

        report = build_performance_validation_report(
            frame,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
            portfolio_validation_report=portfolio_validation_report,
            snapshot_date=snapshot_date,
        )
        path = write_performance_validation_report(
            report, self.performance_validation_file
        )
        self.logger.info("Performance Validation gerado em %s.", path)
        return path

    def generate_dashboard(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        portfolio_report: PortfolioReport | None = None,
        outcome_report: OutcomeAnalyticsReport | None = None,
        universe_report: UniverseReport | None = None,
        priority_report: PriorityReport | None = None,
        watchlist_report: WatchlistReport | None = None,
    ) -> Path | None:
        if not settings.get("dashboard_enabled", True):
            return None

        portfolio_rebalance = getattr(portfolio_report, "rebalance", None)
        if portfolio_rebalance is None and portfolio_report is not None:
            serialized_portfolio = portfolio_report.to_dict()
            portfolio_rebalance = serialized_portfolio.get("rebalance", {})
        decision_queue = build_decision_queue(
            priority=(priority_report.to_dict() if priority_report else None),
            active_watchlist=(watchlist_report.active_queue if watchlist_report else ()),
            portfolio_actions=(
                tuple((portfolio_rebalance or {}).get("actions", ()))
                if portfolio_rebalance is not None
                else ()
            ),
        )
        write_decision_queue(
            decision_queue, self.dashboard_report_file.parent / "decision_queue.json"
        )
        view = build_dashboard_view(
            build_company_reports(frame),
            market=universe_report,
            portfolio=portfolio_report,
            outcomes=outcome_report,
            priority=priority_report,
            decision_queue=decision_queue,
        )
        write_dashboard_view(view, self.dashboard_report_file)
        self.logger.info(
            "Dashboard contract gerado em %s (%s empresas).",
            self.dashboard_report_file,
            len(view.companies),
        )
        return self.dashboard_report_file

    def generate_priority_report(
        self,
        settings: Settings,
        *,
        ranking_report: RankingReport | None,
        portfolio_report: PortfolioReport | None,
    ) -> tuple[Path, PriorityReport] | None:
        if not settings.get("priority_enabled", True):
            return None

        weights_by_symbol: dict[str, float] = {}
        held_symbols: frozenset[str] | None = None
        rebalance_actions: tuple[dict[str, Any], ...] = ()
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
        if self.research_ranking_report_file.exists():
            research_data = json.loads(
                self.research_ranking_report_file.read_text(encoding="utf-8")
            )
            buy = build_buy_priority(
                research_data["companies"],
                held_symbols=held_symbols or frozenset(),
            )

        report = PriorityReport(sell=sell, buy=buy)
        write_priority_report(report, self.priority_report_file)
        self.logger.info(
            "Priority Report: %s holdings classificados; %s candidatos "
            "de compra disponíveis.",
            len(sell.items),
            len(buy.items) if buy is not None else 0,
        )
        return self.priority_report_file, report

    def generate_excel_reports(
        self,
        frame: pd.DataFrame,
        portfolio_report: PortfolioReport | None = None,
        outcome_report: OutcomeAnalyticsReport | None = None,
    ) -> tuple[Path, Path | None]:
        self.logger.info("Gerando relatórios Excel.")
        history_file, latest_file = write_latest_and_history(
            frame,
            self.output_reports,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
            database_path=self.history_database,
        )
        self.logger.info("Excel histórico gerado em %s.", history_file)
        return history_file, latest_file

    def generate_morning_brief(
        self,
        frame: pd.DataFrame,
        portfolio_report: PortfolioReport | None = None,
        outcome_report: OutcomeAnalyticsReport | None = None,
    ) -> tuple[Path, str]:
        self.logger.info("Gerando Morning Brief.")
        brief_path = self.morning_brief_writer(
            current_df=frame,
            database_path=self.history_database,
            output_path=self.morning_brief_file,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
        )
        brief_text = self.morning_brief_renderer(
            current_df=frame,
            database_path=self.history_database,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
        )
        self.logger.info("Morning Brief gerado em %s.", brief_path)
        return brief_path, brief_text

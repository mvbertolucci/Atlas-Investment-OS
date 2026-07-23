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
from decision.delta import (
    build_decision_delta,
    find_previous_snapshot,
    write_decision_delta,
)
from decision.queue import (
    build_decision_queue,
    snapshot_decision_queue,
    write_decision_queue,
)
from decision.cockpit import write_decision_cockpit
from decision.journal import journal_summary, load_journal
from decision.execution import execution_summary, load_execution_ledger
from decision.reconciliation import (
    load_reconciliation_summary,
    reconcile_executions,
    write_execution_reconciliation,
)
from portfolio.custody_history import (
    capture_custody_snapshot,
    custody_history_summary,
    load_custody_history,
)
from portfolio.scenario import build_sell_scenario, write_portfolio_scenario
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

_BUY_DECISIONS = {"STRONG_BUY", "BUY", "ACCUMULATE"}


def _fmt_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_number(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _build_cockpit_opportunities(
    company_reports: tuple[Any, ...],
    portfolio_report: PortfolioReport | None,
    *,
    limit: int = 5,
) -> tuple[dict[str, Any], ...]:
    """Candidatas de compra fora da carteira (mesma seleção do antigo brief).

    Ordena por opportunity_score desc; exclui o que já é posição. Move para o
    cockpit o único conteúdo que o `decision_brief.html` tinha de próprio.
    """
    held: set[str] = set()
    if portfolio_report is not None:
        allocation = portfolio_report.to_dict().get("allocation", {}) or {}
        held = {str(sym).upper() for sym in (allocation.get("by_symbol", {}) or {})}
    candidates = [
        report
        for report in company_reports
        if str(report.symbol).upper() not in held
        and report.decision in _BUY_DECISIONS
    ]
    candidates.sort(key=lambda r: r.opportunity_score or 0.0, reverse=True)
    return tuple(
        {
            "symbol": report.symbol,
            "company_name": report.company_name,
            "action": "CANDIDATA",
            "decision_drivers": tuple(report.decision_drivers),
            "investment_thesis": report.investment_thesis,
            "opportunity_score": report.opportunity_score,
            "conviction_score": report.conviction_score,
            "decision_confidence": report.decision_confidence,
            "data_coverage": report.data_coverage,
            "risk_penalty": report.risk_penalty,
        }
        for report in candidates[:limit]
    )


def _build_cockpit_health(
    portfolio_report: PortfolioReport | None,
) -> dict[str, Any] | None:
    if portfolio_report is None:
        return None
    payload = portfolio_report.to_dict()
    summary = payload.get("summary", {}) or {}
    if not summary.get("total_value"):
        return None
    return {
        "currency": summary.get("currency", "USD"),
        "total_value": f"{float(summary.get('total_value', 0.0)):,.2f}",
        "quality_score": _fmt_number(summary.get("quality_score")),
        "quality_rating": summary.get("quality_rating", "-"),
        "cash_weight": _fmt_percent(summary.get("cash_weight")),
        "largest_position_weight": _fmt_percent(
            summary.get("largest_position_weight")
        ),
        "warnings": tuple(payload.get("warnings", ()) or ()),
    }


def _build_cockpit_outcomes_line(
    outcome_report: OutcomeAnalyticsReport | None,
) -> str | None:
    hit_rate = getattr(outcome_report, "hit_rate", None)
    if hit_rate is None or getattr(hit_rate, "eligible_count", 0) == 0:
        return "Ainda não há amostra direcional madura."
    return (
        f"Hit rate direcional: {hit_rate.hit_rate:.1f}% "
        f"({hit_rate.hit_count}/{hit_rate.eligible_count})."
    )


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
        company_reports = build_company_reports(frame)
        company_context = {
            report.symbol: {
                "company_name": report.company_name,
                "investment_thesis": report.investment_thesis,
                "opportunity_score": report.opportunity_score,
                "conviction_score": report.conviction_score,
                "decision_confidence": report.decision_confidence,
                "data_coverage": report.data_coverage,
                "risk_penalty": report.risk_penalty,
            }
            for report in company_reports
        }
        decision_queue = build_decision_queue(
            priority=(priority_report.to_dict() if priority_report else None),
            active_watchlist=(watchlist_report.active_queue if watchlist_report else ()),
            portfolio_actions=(
                tuple((portfolio_rebalance or {}).get("actions", ()))
                if portfolio_rebalance is not None
                else ()
            ),
            company_context=company_context,
        )
        write_decision_queue(
            decision_queue, self.dashboard_report_file.parent / "decision_queue.json"
        )
        history_dir = self.dashboard_report_file.parent / "history" / "decision_queue"
        # Diff contra a execução anterior antes de gravar o snapshot novo (que
        # tem generated_at posterior e por isso não é selecionado como base).
        previous_snapshot = find_previous_snapshot(
            history_dir, before_generated_at=decision_queue.generated_at
        )
        decision_delta = build_decision_delta(
            decision_queue.to_dict(), previous_snapshot
        )
        write_decision_delta(
            decision_delta, self.dashboard_report_file.parent / "decision_delta.json"
        )
        snapshot_decision_queue(decision_queue, history_dir)
        portfolio_scenario = None
        if portfolio_report is not None:
            portfolio_payload = portfolio_report.to_dict()
            if (portfolio_payload.get("summary") or {}).get("total_value"):
                portfolio_scenario = build_sell_scenario(portfolio_payload)
                write_portfolio_scenario(
                    portfolio_scenario,
                    self.dashboard_report_file.parent / "portfolio_scenario.json",
                )
        journal_path = self.dashboard_report_file.parent / "decision_journal.json"
        decision_journal = journal_summary(load_journal(journal_path))
        ledger_path = self.dashboard_report_file.parent / "execution_ledger.json"
        ledger_payload = load_execution_ledger(ledger_path)
        execution_ledger = execution_summary(ledger_payload)
        reconciliation_path = self.dashboard_report_file.parent / "execution_reconciliation.json"
        execution_reconciliation = None
        custody_history = None
        if portfolio_report is not None:
            custody_payload = portfolio_report.to_dict()
            if custody_payload.get("generated_at") and isinstance(
                custody_payload.get("holdings"), (list, tuple)
            ):
                history_path = self.dashboard_report_file.parent / "portfolio_custody_history.json"
                capture_custody_snapshot(custody_payload, history_path=history_path)
                history_payload = load_custody_history(history_path)
                custody_history = custody_history_summary(history_payload)
                snapshots = history_payload["snapshots"]
                if len(snapshots) >= 2:
                    baseline, current = snapshots[-2:]
                    reconciliation = reconcile_executions(
                        ledger_payload,
                        baseline_portfolio=baseline,
                        current_portfolio=current,
                        baseline_snapshot_at=str(baseline["snapshot_at"]),
                        current_snapshot_at=str(current["snapshot_at"]),
                    )
                    write_execution_reconciliation(reconciliation, reconciliation_path)
                    execution_reconciliation = reconciliation.to_dict()["summary"]
        elif reconciliation_path.exists():
            execution_reconciliation = load_reconciliation_summary(reconciliation_path)
        cockpit_opportunities = _build_cockpit_opportunities(
            company_reports, portfolio_report
        )
        cockpit_health = _build_cockpit_health(portfolio_report)
        cockpit_outcomes_line = _build_cockpit_outcomes_line(outcome_report)
        cockpit_path = self.output_reports / "decision_cockpit.html"
        write_decision_cockpit(
            decision_queue,
            cockpit_path,
            delta=decision_delta.to_dict(),
            opportunities=cockpit_opportunities,
            portfolio_health=cockpit_health,
            outcomes_line=cockpit_outcomes_line,
            scenario=portfolio_scenario,
            journal_summary=decision_journal,
            execution_summary=execution_ledger,
            reconciliation_summary=execution_reconciliation,
        )
        view = build_dashboard_view(
            company_reports,
            market=universe_report,
            portfolio=portfolio_report,
            outcomes=outcome_report,
            priority=priority_report,
            decision_queue=decision_queue,
            portfolio_scenario=portfolio_scenario,
            decision_journal=decision_journal,
            execution_ledger=execution_ledger,
            execution_reconciliation=execution_reconciliation,
            custody_history=custody_history,
        )
        write_dashboard_view(view, self.dashboard_report_file)
        self.logger.info(
            "Dashboard contract gerado em %s (%s empresas); cockpit em %s.",
            self.dashboard_report_file,
            len(view.companies),
            cockpit_path,
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

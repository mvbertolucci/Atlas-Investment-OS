from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.history import load_history, previous_run_context
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
from portfolio.loader import load_portfolio_csv
from portfolio.models import Portfolio
from portfolio.sell_rules import SellRulesPolicy, load_sell_rules_policy
from scoring.investment import load_yaml
from storage.history_db import HistoryDatabase


Settings = dict[str, Any]
PreviousBySymbol = dict[str, dict[str, object]]


@dataclass(frozen=True)
class HistoryApplicationService:
    root: Path
    config: Path
    history_database: Path
    outcome_report_file: Path
    logger: logging.Logger

    def load_model_config(
        self, path: Path | None = None
    ) -> dict[str, Any]:
        return load_yaml(path or self.config / "model.yaml")

    def load_score_history(self, path: Path | None = None) -> pd.DataFrame:
        return load_history(path or self.history_database)

    def previous_run_context(
        self,
        history: pd.DataFrame,
        *,
        current_snapshot_date: str,
        current_model_version: str,
    ) -> tuple[PreviousBySymbol, str, pd.Timestamp | None]:
        return previous_run_context(
            history,
            current_snapshot_date=current_snapshot_date,
            current_model_version=current_model_version,
        )

    def load_sell_rules_policy(
        self, path: Path | None = None
    ) -> SellRulesPolicy:
        return load_sell_rules_policy(
            path or self.config / "sell_rules.yaml"
        )

    def portfolio_path(self, settings: Settings) -> Path:
        return self.root / settings.get(
            "portfolio_path", "config/portfolio.csv"
        )

    def load_portfolio(self, path: Path) -> Portfolio:
        return load_portfolio_csv(path)

    def save_history_snapshot(
        self,
        frame: pd.DataFrame,
        snapshot_date: str,
        model_version: str = "legacy",
    ) -> str:
        with HistoryDatabase(self.history_database) as database:
            database.save_snapshot(
                df=frame,
                snapshot_date=snapshot_date,
                model_version=model_version,
            )
        self.logger.info(
            "Snapshot histórico salvo em %s (model_version=%s).",
            snapshot_date,
            model_version,
        )
        return snapshot_date

    def save_outcome_decisions(
        self,
        frame: pd.DataFrame,
        snapshot_date: str,
        settings: Settings,
    ) -> OutcomeCaptureResult | None:
        if not settings.get("outcome_analytics_enabled", True):
            self.logger.info("Outcome Analytics desabilitado.")
            return None
        with HistoryDatabase(self.history_database) as database:
            result = capture_outcome_snapshots(
                database,
                frame,
                decision_date=snapshot_date,
                horizons_days=settings.get("outcome_horizons_days"),
            )
        self.logger.info(
            "Outcome snapshots salvos: %s; ignorados: %s.",
            result.saved_count,
            len(result.skipped_symbols),
        )
        return result

    def evaluate_outcome_decisions(
        self,
        frame: pd.DataFrame,
        snapshot_date: str,
        settings: Settings,
    ) -> OutcomeEvaluationResult | None:
        if not settings.get("outcome_analytics_enabled", True):
            return None
        with HistoryDatabase(self.history_database) as database:
            result = evaluate_due_outcomes(
                database,
                frame,
                evaluation_date=snapshot_date,
                horizons_days=settings.get("outcome_horizons_days"),
            )
        self.logger.info(
            "Outcome results avaliados: %s; pendentes: %s; sem preço: %s.",
            result.evaluated_count,
            result.pending_count,
            len(result.missing_price_symbols),
        )
        return result

    def generate_outcome_analytics(
        self, settings: Settings
    ) -> OutcomeAnalyticsReport | None:
        if not settings.get("outcome_analytics_enabled", True):
            return None
        with HistoryDatabase(self.history_database) as database:
            report = build_outcome_analytics_report(
                database,
                threshold_pct=settings.get(
                    "outcome_hit_threshold_pct", 0.0
                ),
                bucket_size=settings.get(
                    "outcome_calibration_bucket_size", 20
                ),
            )
        write_outcome_report(report, self.outcome_report_file)
        self.logger.info(
            "Outcome Analytics: %s resultados elegíveis; hit rate %s.",
            report.hit_rate.eligible_count,
            report.hit_rate.hit_rate,
        )
        return report

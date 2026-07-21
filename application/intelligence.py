from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio.pipeline import (
    build_portfolio_intelligence,
    write_portfolio_report,
)
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy
from reports.atlas_report.context import ReportContext, build_report_context
from reports.atlas_report.render import render_report
from reports.atlas_report.write import write_report
from storage.history_db import HistoryDatabase
from watchlist import (
    WatchlistError,
    WatchlistReport,
    attach_aging,
    evaluate_watchlist_triggers,
    load_watchlist_csv,
    normalize_current_row,
    write_watchlist_report,
)
from watchlist.auto_curation import AutoCurationResult, run_auto_curation
from watchlist.auto_policy import load_watchlist_auto_policy


Settings = dict[str, Any]
PreviousBySymbol = dict[str, dict[str, object]]


@dataclass(frozen=True)
class IntelligenceApplicationService:
    root: Path
    config: Path
    output_reports: Path
    history_database: Path
    portfolio_report_file: Path
    watchlist_report_file: Path
    logger: logging.Logger

    def read_status_md(self) -> str:
        try:
            return (self.root / "STATUS.md").read_text(encoding="utf-8")
        except OSError:
            return ""

    def generate_portfolio_intelligence(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        sell_rules_policy: SellRulesPolicy | None = None,
        previous_by_symbol: PreviousBySymbol | None = None,
        baseline_status: str = "first_run",
        previous_run_at: pd.Timestamp | None = None,
        current_run_at: str | None = None,
    ) -> tuple[Path, PortfolioReport] | None:
        portfolio_path = self.root / settings.get(
            "portfolio_path", "config/portfolio.csv"
        )
        if not portfolio_path.exists():
            self.logger.info(
                "Portfolio Intelligence ignorado: arquivo não encontrado "
                "em %s.",
                portfolio_path,
            )
            return None

        self.logger.info(
            "Executando Portfolio Intelligence com %s.", portfolio_path
        )
        report = build_portfolio_intelligence(
            portfolio_path,
            frame,
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
            report, self.portfolio_report_file
        )
        self.logger.info(
            "Portfolio Intelligence concluído em %s.", report_path
        )
        return report_path, report

    def run_watchlist_auto_curation(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        sp500_report_path: Path | None,
        broad_market_report_path: Path | None,
    ) -> AutoCurationResult:
        """
        Fluxo automático de inclusão/exclusão na watchlist -- adicional ao
        gate manual (promote_to_watchlist/planilha, inalterado). Roda antes
        de `generate_watchlist_report` no mesmo estágio: como esse método
        relê `config/watchlist.csv` do disco (não usa o DataFrame em
        memória do bootstrap), o resultado desta curadoria já aparece no
        mesmo relatório, sem plumbing extra.

        `config/watchlist_auto.yaml::enabled` é o circuit breaker -- com
        `False` (o padrão), `run_auto_curation` nem toca o CSV.
        """
        watchlist_path = self.root / settings.get(
            "watchlist_path", "config/watchlist.csv"
        )
        policy = load_watchlist_auto_policy(self.config / "watchlist_auto.yaml")
        result = run_auto_curation(
            watchlist_path=watchlist_path,
            sp500_report_path=sp500_report_path,
            broad_market_report_path=broad_market_report_path,
            scored_frame=frame,
            policy=policy,
        )
        if result.enabled and (result.included or result.excluded):
            self.logger.info(
                "Watchlist Auto Curation: %s incluído(s), %s removido(s).",
                len(result.included),
                len(result.excluded),
            )
        return result

    def generate_watchlist_report(
        self,
        frame: pd.DataFrame,
        settings: Settings,
        *,
        previous_by_symbol: PreviousBySymbol | None = None,
        baseline_status: str = "first_run",
        previous_run_at: pd.Timestamp | None = None,
        current_run_at: str | None = None,
        auto_curation: AutoCurationResult | None = None,
    ) -> tuple[Path, WatchlistReport] | None:
        watchlist_path = self.root / settings.get(
            "watchlist_path", "config/watchlist.csv"
        )
        if not watchlist_path.exists():
            self.logger.info(
                "Watchlist tracking ignorado: arquivo não encontrado em %s.",
                watchlist_path,
            )
            return None
        try:
            entries = load_watchlist_csv(watchlist_path)
        except WatchlistError as exc:
            self.logger.warning(
                "Não foi possível avaliar triggers da watchlist: %s", exc
            )
            return None

        current_by_symbol = {
            str(row.get("symbol", "")).strip().upper(): (
                normalize_current_row(row.to_dict())
            )
            for _, row in frame.iterrows()
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
        with HistoryDatabase(self.history_database) as database:
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

        report = WatchlistReport(
            results=results,
            auto_curation=auto_curation.to_dict() if auto_curation else None,
        )
        report_path = write_watchlist_report(
            report, self.watchlist_report_file
        )
        self.logger.info(
            "Watchlist tracking: %s trigger(s) disparado(s); %s "
            "sugestão(ões) de limpeza.",
            len(report.triggered),
            len(report.cleanup_candidates),
        )
        return report_path, report

    def build_report_context(self, **kwargs: Any) -> ReportContext:
        return build_report_context(**kwargs)

    def render_and_write_report(
        self, context: ReportContext, report_date: str
    ) -> tuple[Path, Path]:
        return write_report(
            render_report(context), self.output_reports, report_date
        )

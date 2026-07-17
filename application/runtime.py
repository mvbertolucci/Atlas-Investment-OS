from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from health.health_check import (
    HealthReport,
    print_health_report,
    run_health_check,
)
from metrics.execution import (
    ExecutionMetrics,
    print_execution_metrics,
    save_execution_metrics,
)


Settings = dict[str, Any]
HealthCheckRunner = Callable[[Path], HealthReport]
HealthReportWriter = Callable[[HealthReport], None]
MetricsSaver = Callable[[ExecutionMetrics, Path], None]
MetricsWriter = Callable[[ExecutionMetrics], None]
OutputWriter = Callable[[str], None]


@dataclass(frozen=True)
class OperationalRuntimeService:
    root: Path
    config: Path
    execution_metrics_file: Path
    logger: logging.Logger
    health_check_runner: HealthCheckRunner = run_health_check
    health_report_writer: HealthReportWriter = print_health_report
    metrics_saver: MetricsSaver = save_execution_metrics
    metrics_writer: MetricsWriter = print_execution_metrics
    output_writer: OutputWriter = print

    def run_health_check(self) -> HealthReport:
        return self.health_check_runner(self.root)

    def print_health_report(self, report: HealthReport) -> None:
        self.health_report_writer(report)

    def load_settings(self) -> Settings:
        settings_path = self.config / "settings.json"
        if not settings_path.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração não encontrado: {settings_path}"
            )
        return json.loads(settings_path.read_text(encoding="utf-8"))

    def safe_console_text(
        self,
        value: object,
        encoding: str | None = None,
    ) -> str:
        text = str(value)
        target_encoding = encoding or getattr(sys.stdout, "encoding", None)
        if not target_encoding:
            return text
        return text.encode(
            target_encoding, errors="replace"
        ).decode(target_encoding)

    def print_console_table(self, frame: pd.DataFrame) -> None:
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
            column for column in columns if column in frame.columns
        ]

        self.output_writer("")
        if available_columns:
            table = frame[available_columns].head(20).to_string(index=False)
            self.output_writer(self.safe_console_text(table))
        else:
            self.output_writer(
                "[AVISO] Nenhuma coluna de resumo foi encontrada."
            )
        self.output_writer("")

    def save_execution_metrics(self, metrics: ExecutionMetrics) -> None:
        self.metrics_saver(metrics, self.execution_metrics_file)

    def print_execution_metrics(self, metrics: ExecutionMetrics) -> None:
        self.metrics_writer(metrics)

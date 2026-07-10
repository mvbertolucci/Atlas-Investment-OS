from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ExecutionMetrics:
    """
    Armazena métricas da execução completa do Atlas.
    """

    started_at: float = field(default_factory=time.perf_counter)

    download_time: float = 0.0
    scoring_time: float = 0.0
    history_time: float = 0.0
    reports_time: float = 0.0
    morning_brief_time: float = 0.0

    companies: int = 0

    def total_time(self) -> float:
        return time.perf_counter() - self.started_at

    def processing_rate(self) -> float:
        total = self.total_time()

        if total <= 0:
            return 0.0

        return self.companies / total

    def summary(self) -> dict:

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "companies": self.companies,
            "download_time": round(self.download_time, 3),
            "scoring_time": round(self.scoring_time, 3),
            "history_time": round(self.history_time, 3),
            "reports_time": round(self.reports_time, 3),
            "morning_brief_time": round(self.morning_brief_time, 3),
            "total_time": round(self.total_time(), 3),
            "processing_rate": round(
                self.processing_rate(),
                2,
            ),
        }


class StageTimer:
    """
    Context manager para medir etapas do Atlas.

    Exemplo:

        with StageTimer(metrics, "download_time"):
            ...
    """

    def __init__(
        self,
        metrics: ExecutionMetrics,
        attribute: str,
    ):
        self.metrics = metrics
        self.attribute = attribute

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        elapsed = (
            time.perf_counter()
            - self.start
        )

        setattr(
            self.metrics,
            self.attribute,
            elapsed,
        )


def print_execution_metrics(
    metrics: ExecutionMetrics,
) -> None:

    print()

    print("=" * 70)
    print("ATLAS EXECUTION METRICS")
    print("=" * 70)

    print()

    print(
        f"Companies Processed : {metrics.companies}"
    )

    print(
        f"Download Time       : {metrics.download_time:.2f} s"
    )

    print(
        f"Scoring Time        : {metrics.scoring_time:.2f} s"
    )

    print(
        f"History Time        : {metrics.history_time:.2f} s"
    )

    print(
        f"Reports Time        : {metrics.reports_time:.2f} s"
    )

    print(
        f"Morning Brief       : {metrics.morning_brief_time:.2f} s"
    )

    print()

    print(
        f"Total Time          : {metrics.total_time():.2f} s"
    )

    print(
        f"Processing Rate     : {metrics.processing_rate():.2f} companies/sec"
    )

    print()


def save_execution_metrics(
    metrics: ExecutionMetrics,
    file_path: Path,
) -> None:
    """
    Salva histórico das execuções.
    """

    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    row = metrics.summary()

    file_exists = file_path.exists()

    with open(
        file_path,
        "a",
        newline="",
        encoding="utf-8",
    ) as csvfile:

        writer = csv.DictWriter(
            csvfile,
            fieldnames=row.keys(),
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)
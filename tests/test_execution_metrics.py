from __future__ import annotations

import csv
from pathlib import Path

import pytest

from metrics.execution import (
    ExecutionMetrics,
    StageTimer,
    print_execution_metrics,
    save_execution_metrics,
)


def test_execution_metrics_summary_and_rate(monkeypatch) -> None:
    metrics = ExecutionMetrics(started_at=10.0, companies=20)
    metrics.download_time = 1.23456
    monkeypatch.setattr(
        "metrics.execution.time.perf_counter",
        lambda: 14.0,
    )

    assert metrics.total_time() == 4.0
    assert metrics.processing_rate() == 5.0
    summary = metrics.summary()
    assert summary["companies"] == 20
    assert summary["download_time"] == 1.235
    assert summary["total_time"] == 4.0
    assert summary["processing_rate"] == 5.0


def test_processing_rate_handles_non_positive_time(monkeypatch) -> None:
    metrics = ExecutionMetrics(started_at=10.0, companies=20)
    monkeypatch.setattr(
        "metrics.execution.time.perf_counter",
        lambda: 10.0,
    )

    assert metrics.processing_rate() == 0.0


def test_stage_timer_records_elapsed_and_propagates_errors(
    monkeypatch,
) -> None:
    values = iter([10.0, 12.5, 20.0, 21.0])
    monkeypatch.setattr(
        "metrics.execution.time.perf_counter",
        lambda: next(values),
    )
    metrics = ExecutionMetrics(started_at=0.0)

    with StageTimer(metrics, "scoring_time"):
        pass
    assert metrics.scoring_time == 2.5

    with pytest.raises(RuntimeError):
        with StageTimer(metrics, "reports_time"):
            raise RuntimeError("boom")
    assert metrics.reports_time == 1.0


def test_save_execution_metrics_appends_single_header(
    tmp_path: Path,
    monkeypatch,
) -> None:
    metrics = ExecutionMetrics(started_at=10.0, companies=3)
    monkeypatch.setattr(
        "metrics.execution.time.perf_counter",
        lambda: 12.0,
    )
    output = tmp_path / "logs" / "execution.csv"

    save_execution_metrics(metrics, output)
    save_execution_metrics(metrics, output)

    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 2
    assert rows[0]["companies"] == "3"
    assert output.read_text(encoding="utf-8").count("timestamp") == 1


def test_print_execution_metrics(capsys, monkeypatch) -> None:
    metrics = ExecutionMetrics(started_at=10.0, companies=4)
    monkeypatch.setattr(
        "metrics.execution.time.perf_counter",
        lambda: 12.0,
    )

    print_execution_metrics(metrics)

    output = capsys.readouterr().out
    assert "ATLAS EXECUTION METRICS" in output
    assert "Companies Processed : 4" in output
    assert "Processing Rate     : 2.00 companies/sec" in output

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest

import run_all
from orchestration.pipeline import (
    CompletionOutput,
    PipelineContext,
    PipelineRequest,
    PipelineRunner,
    build_pipeline,
    parse_pipeline_request,
)


@dataclass(frozen=True)
class FirstOutput:
    value: int


@dataclass(frozen=True)
class SecondOutput:
    value: int


class FirstStage:
    name = "first"
    requires: tuple[type[Any], ...] = ()
    output_type = FirstOutput

    def run(self, context: PipelineContext) -> FirstOutput:
        return FirstOutput(1)


class SecondStage:
    name = "second"
    requires = (FirstOutput,)
    output_type = SecondOutput

    def run(self, context: PipelineContext) -> SecondOutput:
        return SecondOutput(context.require(FirstOutput).value + 1)


def _context() -> PipelineContext:
    return PipelineContext(
        request=PipelineRequest("full"),
        services=cast(Any, SimpleNamespace()),
    )


def test_pipeline_request_validates_mode_and_ticker_contract() -> None:
    assert PipelineRequest("ticker", "MSFT").ticker == "MSFT"
    with pytest.raises(ValueError, match="símbolo"):
        PipelineRequest("ticker")
    with pytest.raises(ValueError, match="só pode"):
        PipelineRequest("full", "MSFT")
    with pytest.raises(ValueError, match="inválido"):
        PipelineRequest(cast(Any, "unknown"))


@pytest.mark.parametrize(
    ("argv", "mode", "ticker"),
    [
        ([], "full", None),
        (["--full"], "full", None),
        (["--portfolio"], "portfolio", None),
        (["--ticker", "msft"], "ticker", "MSFT"),
    ],
)
def test_parse_pipeline_request(
    argv: list[str], mode: str, ticker: str | None
) -> None:
    request = parse_pipeline_request(argv)
    assert request.mode == mode
    assert request.ticker == ticker


def test_context_registry_rejects_missing_and_duplicate_artifacts() -> None:
    context = _context()
    with pytest.raises(RuntimeError, match="obrigatório ausente"):
        context.require(FirstOutput)

    artifact = context.publish(FirstOutput(7))
    assert context.require(FirstOutput) is artifact
    with pytest.raises(RuntimeError, match="já foi publicado"):
        context.publish(FirstOutput(8))


def test_runner_enforces_dependencies_and_typed_outputs() -> None:
    context = PipelineRunner((FirstStage(), SecondStage())).run(_context())
    assert context.require(SecondOutput) == SecondOutput(2)

    with pytest.raises(RuntimeError, match="FirstOutput"):
        PipelineRunner((SecondStage(),)).run(_context())

    bad_stage = SimpleNamespace(
        name="bad",
        requires=(),
        output_type=FirstOutput,
        run=lambda context: SecondOutput(2),
    )
    with pytest.raises(TypeError, match="esperado FirstOutput"):
        PipelineRunner((cast(Any, bad_stage),)).run(_context())


def test_pipeline_factory_exposes_explicit_stage_order_per_mode() -> None:
    expected = [
        "bootstrap",
        "collection",
        "scoring",
        "historical_context",
        "persistence",
        "intelligence",
        "reports",
        "completion",
    ]
    assert [stage.name for stage in build_pipeline("full").stages] == expected
    assert [stage.name for stage in build_pipeline("portfolio").stages] == expected
    assert [stage.name for stage in build_pipeline("ticker").stages] == ["ticker"]
    with pytest.raises(ValueError, match="inválido"):
        build_pipeline(cast(Any, "unknown"))


def test_run_all_main_only_assembles_and_executes_pipeline(monkeypatch) -> None:
    request = PipelineRequest("portfolio")
    captured: dict[str, Any] = {}

    class FakeRunner:
        def run(self, context: PipelineContext) -> None:
            captured["context"] = context

    monkeypatch.setattr(run_all, "parse_pipeline_request", lambda argv: request)
    monkeypatch.setattr(
        run_all,
        "build_pipeline",
        lambda mode: captured.update(mode=mode) or FakeRunner(),
    )

    run_all.main(["--portfolio"])

    assert captured["mode"] == "portfolio"
    assert captured["context"].request is request
    assert captured["context"].services is run_all


def test_portfolio_pipeline_connects_all_stages_offline(tmp_path: Path) -> None:
    calls: list[str] = []
    frame = pd.DataFrame([{"symbol": "MSFT", "price": 100.0}])

    class FakeServices:
        ROOT = tmp_path
        CONFIG = tmp_path
        LOGS = tmp_path
        OUTPUT_DATA = tmp_path
        OUTPUT_REPORTS = tmp_path
        HISTORY_DATABASE = tmp_path / "history.db"
        EXECUTION_METRICS_FILE = tmp_path / "metrics.json"
        OUTCOME_REPORT_FILE = tmp_path / "outcomes.json"
        UNIVERSE_REPORT_FILE = tmp_path / "universe.json"
        RANKING_REPORT_FILE = tmp_path / "ranking.json"
        logger = SimpleNamespace(
            info=lambda *args: calls.append("log_info"),
            warning=lambda *args: calls.append("log_warning"),
        )

        def run_health_check(self, root):
            calls.append("health")
            return object()

        def print_health_report(self, report):
            calls.append("health_report")

        def load_settings(self):
            return {}

        def load_official_scoring_reference(self, settings):
            return None

        def load_watchlist(self, settings):
            return tmp_path / "watchlist.csv", frame.copy()

        def merge_watchlist_with_portfolio(self, watchlist, settings):
            return watchlist.copy()

        def collect_market_data(self, settings, universe, *, failures):
            calls.append("collection")
            return universe.copy()

        def build_scores(self, collected, reference):
            calls.append("scoring")
            return collected.copy()

        def audit_feature_coverage(self, scored):
            return {"phantom_investment_share": 0.0}

        def load_yaml(self, path):
            return {"model_version": "test"}

        def load_score_history(self, path):
            return pd.DataFrame()

        def previous_run_context(self, history, **kwargs):
            return {}, "no_prior_run", None

        def load_sell_rules_policy(self, path):
            return object()

        def save_history_snapshot(self, scored, snapshot_date, model_version):
            calls.append("history")

        def save_outcome_decisions(self, scored, snapshot_date, settings):
            return None

        def evaluate_outcome_decisions(self, scored, snapshot_date, settings):
            return None

        def generate_outcome_analytics(self, settings):
            return None

        def generate_portfolio_intelligence(self, *args, **kwargs):
            return None

        def generate_watchlist_report(self, *args, **kwargs):
            return None

        def build_report_context(self, **kwargs):
            calls.append("intelligence")
            return object()

        def _read_status_md(self):
            return ""

        def render_report(self, report_context):
            return "html"

        def write_report(self, html, output, date):
            return tmp_path / "atlas-dated.html", tmp_path / "atlas-latest.html"

        def generate_excel_reports(self, scored, **kwargs):
            calls.append("reports")
            return tmp_path / "history.xlsx", tmp_path / "latest.xlsx"

        def generate_morning_brief(self, scored, **kwargs):
            return tmp_path / "brief.txt", "brief"

        def generate_priority_report(self, *args, **kwargs):
            return None

        def generate_performance_validation(self, *args, **kwargs):
            return None

        def generate_dashboard(self, *args, **kwargs):
            return None

        def print_console_table(self, scored):
            calls.append("console")

        def _safe_console_text(self, value):
            return value

        def save_execution_metrics(self, metrics, path):
            calls.append("metrics_saved")

        def print_execution_metrics(self, metrics):
            calls.append("metrics_printed")

    context = PipelineContext(
        request=PipelineRequest("portfolio"),
        services=cast(Any, FakeServices()),
    )
    result = build_pipeline("portfolio").run(context)

    assert result.require(CompletionOutput).snapshot_date is not None
    assert calls[:5] == [
        "health",
        "health_report",
        "collection",
        "scoring",
        "history",
    ]
    assert calls[-3:] == ["metrics_saved", "metrics_printed", "log_info"]

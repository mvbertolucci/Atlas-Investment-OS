from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest

import run_all
from application import (
    CollectionApplicationService,
    HistoryApplicationService,
    IntelligenceApplicationService,
    OperationalRuntimeService,
    ReportingApplicationService,
    ScoringApplicationService,
    TickerAnalysisApplicationService,
)
from orchestration.pipeline import (
    CompletionOutput,
    PipelineContext,
    PipelineRequest,
    PipelineRunner,
    TickerOutput,
    build_pipeline,
    parse_pipeline_request,
)
from orchestration.services import (
    CollectionServices,
    HistoryServices,
    IntelligenceServices,
    PipelinePaths,
    PipelineServices,
    ReportingServices,
    RuntimeServices,
    ScoringServices,
    TickerServices,
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
    service_container = cast(Any, object())

    class FakeRunner:
        def run(self, context: PipelineContext) -> None:
            captured["context"] = context

    monkeypatch.setattr(run_all, "parse_pipeline_request", lambda argv: request)
    monkeypatch.setattr(
        run_all, "build_pipeline_services", lambda: service_container
    )
    monkeypatch.setattr(
        run_all,
        "build_pipeline",
        lambda mode: captured.update(mode=mode) or FakeRunner(),
    )

    run_all.main(["--portfolio"])

    assert captured["mode"] == "portfolio"
    assert captured["context"].request is request
    assert captured["context"].services is service_container


def test_run_all_builds_narrow_typed_service_groups() -> None:
    services = run_all.build_pipeline_services()

    assert isinstance(services, PipelineServices)
    assert isinstance(services.runtime, RuntimeServices)
    assert isinstance(services.ticker, TickerServices)
    assert isinstance(services.collection, CollectionServices)
    assert isinstance(services.scoring, ScoringServices)
    assert isinstance(services.history, HistoryServices)
    assert isinstance(services.intelligence, IntelligenceServices)
    assert isinstance(services.reporting, ReportingServices)
    assert services.runtime.paths.root == run_all.ROOT
    assert isinstance(
        services.collection._collect_market_data.__self__,
        CollectionApplicationService,
    )
    assert isinstance(
        services.scoring._build_scores.__self__,
        ScoringApplicationService,
    )
    assert isinstance(
        services.history._save_history_snapshot.__self__,
        HistoryApplicationService,
    )
    assert isinstance(
        services.intelligence._generate_watchlist_report.__self__,
        IntelligenceApplicationService,
    )
    assert isinstance(
        services.reporting._generate_excel_reports.__self__,
        ReportingApplicationService,
    )
    assert isinstance(
        services.runtime._load_settings.__self__,
        OperationalRuntimeService,
    )
    assert isinstance(
        services.ticker._run_ticker_mode.__self__,
        TickerAnalysisApplicationService,
    )


def test_ticker_pipeline_uses_composed_ticker_service(
    monkeypatch, tmp_path: Path
) -> None:
    report_path = tmp_path / "MSFT.html"
    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        OperationalRuntimeService,
        "load_settings",
        lambda self: {"source": "test"},
    )
    ticker_service = SimpleNamespace(
        run_ticker_mode=lambda symbol, settings: (
            calls.append((symbol, settings)) or report_path
        )
    )
    monkeypatch.setattr(
        run_all,
        "_ticker_analysis_application_service",
        lambda *args: ticker_service,
    )
    context = PipelineContext(
        request=PipelineRequest("ticker", "MSFT"),
        services=run_all.build_pipeline_services(),
    )

    build_pipeline("ticker").run(context)

    assert context.require(TickerOutput).report_path == report_path
    assert calls == [("MSFT", {"source": "test"})]


def test_portfolio_pipeline_connects_all_stages_offline(tmp_path: Path) -> None:
    calls: list[str] = []
    frame = pd.DataFrame([{"symbol": "MSFT", "price": 100.0}])

    class FakeServices:
        paths = SimpleNamespace(
            root=tmp_path,
            config=tmp_path,
            logs=tmp_path,
            output_data=tmp_path,
            output_reports=tmp_path,
            history_database=tmp_path / "history.db",
            execution_metrics_file=tmp_path / "metrics.json",
            outcome_report_file=tmp_path / "outcomes.json",
            universe_report_file=tmp_path / "universe.json",
            ranking_report_file=tmp_path / "ranking.json",
        )
        logger = SimpleNamespace(
            info=lambda *args: calls.append("log_info"),
            warning=lambda *args: calls.append("log_warning"),
        )

        def run_health_check(self):
            calls.append("health")
            return object()

        def print_health_report(self, report):
            calls.append("health_report")

        def load_settings(self):
            return {}

        def load_official_reference(self, settings):
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

        def load_model_config(self):
            return {"model_version": "test"}

        def load_score_history(self):
            return pd.DataFrame()

        def previous_run_context(self, history, **kwargs):
            return {}, "no_prior_run", None

        def load_sell_rules_policy(self):
            return object()

        def portfolio_path(self, settings):
            return tmp_path / "portfolio.csv"

        def load_portfolio(self, path):
            raise AssertionError("portfolio ausente não deve ser carregado")

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

        def run_watchlist_auto_curation(self, *args, **kwargs):
            return None

        def generate_watchlist_report(self, *args, **kwargs):
            return None

        def build_report_context(self, **kwargs):
            calls.append("intelligence")
            return object()

        def read_status_md(self):
            return ""

        def render_and_write_report(self, report_context, date):
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

        def safe_console_text(self, value, encoding=None):
            return value

        def save_execution_metrics(self, metrics):
            calls.append("metrics_saved")

        def print_execution_metrics(self, metrics):
            calls.append("metrics_printed")

    fake = FakeServices()
    paths = PipelinePaths(**vars(fake.paths))
    services = PipelineServices(
        runtime=RuntimeServices(
            paths=paths,
            logger=fake.logger,
            _run_health_check=fake.run_health_check,
            _print_health_report=fake.print_health_report,
            _load_settings=fake.load_settings,
            _print_console_table=fake.print_console_table,
            _safe_console_text=fake.safe_console_text,
            _save_execution_metrics=fake.save_execution_metrics,
            _print_execution_metrics=fake.print_execution_metrics,
        ),
        ticker=TickerServices(
            _run_ticker_mode=lambda symbol, settings: tmp_path / "ticker.html",
        ),
        collection=CollectionServices(
            _load_watchlist=fake.load_watchlist,
            _merge_watchlist_with_portfolio=fake.merge_watchlist_with_portfolio,
            _collect_market_data=fake.collect_market_data,
        ),
        scoring=ScoringServices(
            paths=paths,
            _load_official_reference=fake.load_official_reference,
            _build_scores=fake.build_scores,
            _audit_feature_coverage=fake.audit_feature_coverage,
            _generate_universe_report=lambda frame, settings: None,
            _generate_ranking_report=lambda frame, settings, universe: None,
        ),
        history=HistoryServices(
            paths=paths,
            logger=fake.logger,
            _load_model_config=lambda path: fake.load_model_config(),
            _load_score_history=lambda path: fake.load_score_history(),
            _previous_run_context=fake.previous_run_context,
            _load_sell_rules_policy=lambda path: fake.load_sell_rules_policy(),
            _load_portfolio=fake.load_portfolio,
            _save_history_snapshot=fake.save_history_snapshot,
            _save_outcome_decisions=fake.save_outcome_decisions,
            _evaluate_outcome_decisions=fake.evaluate_outcome_decisions,
            _generate_outcome_analytics=fake.generate_outcome_analytics,
        ),
        intelligence=IntelligenceServices(
            paths=paths,
            _read_status_md=fake.read_status_md,
            _generate_portfolio_intelligence=fake.generate_portfolio_intelligence,
            _run_watchlist_auto_curation=fake.run_watchlist_auto_curation,
            _generate_watchlist_report=fake.generate_watchlist_report,
            _build_report_context=fake.build_report_context,
            _render_and_write_report=fake.render_and_write_report,
        ),
        reporting=ReportingServices(
            _generate_excel_reports=fake.generate_excel_reports,
            _generate_morning_brief=fake.generate_morning_brief,
            _generate_priority_report=fake.generate_priority_report,
            _generate_performance_validation=fake.generate_performance_validation,
            _generate_dashboard=fake.generate_dashboard,
        ),
    )
    context = PipelineContext(
        request=PipelineRequest("portfolio"),
        services=services,
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


def _minimal_intelligence_stage_context(
    tmp_path: Path,
    *,
    run_watchlist_auto_curation: Any,
) -> PipelineContext:
    """Publica só o que IntelligenceStage.requires exige, com valores
    mínimos viáveis -- suficiente para rodar o estágio isolado, sem montar
    o pipeline inteiro."""
    from datetime import datetime

    from orchestration.pipeline import (
        BootstrapOutput,
        CollectionOutput,
        HistoricalContextOutput,
        PersistenceOutput,
        ScoringOutput,
    )
    from portfolio.sell_rules import SellRulesPolicy

    frame = pd.DataFrame([{"symbol": "MSFT", "price": 100.0, "origin": "watchlist"}])
    paths = PipelinePaths(
        root=tmp_path,
        config=tmp_path,
        logs=tmp_path,
        output_data=tmp_path,
        output_reports=tmp_path,
        history_database=tmp_path / "history.db",
        execution_metrics_file=tmp_path / "metrics.json",
        outcome_report_file=tmp_path / "outcomes.json",
        universe_report_file=tmp_path / "universe.json",
        ranking_report_file=tmp_path / "ranking.json",
    )
    intelligence_services = IntelligenceServices(
        paths=paths,
        _read_status_md=lambda: "",
        _generate_portfolio_intelligence=lambda *a, **k: None,
        _run_watchlist_auto_curation=run_watchlist_auto_curation,
        _generate_watchlist_report=lambda *a, **k: None,
        _build_report_context=lambda **k: object(),
        _render_and_write_report=lambda ctx, date: (
            tmp_path / "dated.html",
            tmp_path / "latest.html",
        ),
    )
    services = SimpleNamespace(intelligence=intelligence_services)
    context = PipelineContext(
        request=PipelineRequest("full"),
        services=cast(Any, services),
    )
    context.publish(
        BootstrapOutput(
            settings={},
            scoring_reference=None,
            watchlist_path=tmp_path / "watchlist.csv",
            watchlist=frame.copy(),
            analysis_universe=frame.copy(),
        )
    )
    context.publish(CollectionOutput(frame=frame.copy(), fetch_failures=()))
    context.publish(
        ScoringOutput(
            frame=frame.copy(),
            feature_coverage_summary={"phantom_investment_share": 0.0},
            universe_report=None,
            ranking_report=None,
            broad_market_report_path=None,
            adr_report_path=None,
            research_ranking_report_path=None,
        )
    )
    context.publish(
        HistoricalContextOutput(
            frame=frame.copy(),
            run_at=datetime.now(),
            snapshot_date="2026-07-21T00:00:00",
            model_version="test",
            score_history=pd.DataFrame(),
            previous_by_symbol={},
            baseline_status="first_run",
            previous_run_at=None,
            sell_rules_policy=cast(SellRulesPolicy, object()),
        )
    )
    context.publish(PersistenceOutput(None, None, None))
    return context


def test_intelligence_stage_threads_watchlist_auto_curation_through(
    tmp_path: Path,
) -> None:
    from orchestration.pipeline import IntelligenceOutput, IntelligenceStage
    from watchlist.auto_curation import AutoCurationResult
    from watchlist.promote import PromotionResult

    expected = AutoCurationResult(
        included=(
            PromotionResult(
                symbol="NEM",
                name="Newmont",
                included_at="2026-07-21",
                note="Auto-inclusão",
                watchlist_path=tmp_path / "watchlist.csv",
                source="auto",
            ),
        ),
        excluded=(),
        included_failures=(),
        excluded_failures=(),
        enabled=True,
    )
    context = _minimal_intelligence_stage_context(
        tmp_path, run_watchlist_auto_curation=lambda *a, **k: expected
    )

    output = IntelligenceStage().run(context)

    assert isinstance(output, IntelligenceOutput)
    assert output.watchlist_auto_curation is expected


def test_completion_stage_prints_watchlist_auto_curation_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from orchestration.pipeline import (
        CompletionStage,
        IntelligenceOutput,
        PersistenceOutput,
        ReportsOutput,
        ScoringOutput,
    )
    from watchlist.auto_curation import AutoCurationResult
    from watchlist.promote import PromotionResult, RemovalResult

    context = _minimal_intelligence_stage_context(
        tmp_path, run_watchlist_auto_curation=lambda *a, **k: None
    )
    # CompletionStage também exige ReportsOutput -- publica um mínimo.
    context.publish(
        ReportsOutput(
            history_file=tmp_path / "history.xlsx",
            latest_file=None,
            brief_file=tmp_path / "brief.md",
            brief_text="",
            priority_file=None,
            priority_report=None,
            performance_validation_file=None,
            dashboard_file=None,
        )
    )
    context.services.runtime = SimpleNamespace(
        paths=context.services.intelligence.paths,
        print_console_table=lambda frame: None,
        safe_console_text=lambda value, encoding=None: str(value),
        save_execution_metrics=lambda metrics: None,
        print_execution_metrics=lambda metrics: None,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )
    context.publish(
        IntelligenceOutput(
            portfolio_result=None,
            portfolio_report=None,
            watchlist_result=None,
            watchlist_report=None,
            report_context=object(),
            atlas_report_dated=tmp_path / "dated.html",
            atlas_report_latest=tmp_path / "latest.html",
            watchlist_auto_curation=AutoCurationResult(
                included=(
                    PromotionResult(
                        symbol="NEM",
                        name="Newmont",
                        included_at="2026-07-21",
                        note="Auto-inclusão: top 30",
                        watchlist_path=tmp_path / "watchlist.csv",
                        source="auto",
                    ),
                ),
                excluded=(
                    RemovalResult(
                        symbol="STALE",
                        reason="Investment Score 12.0 < 40.0",
                        watchlist_path=tmp_path / "watchlist.csv",
                    ),
                ),
                included_failures=(),
                excluded_failures=(),
                enabled=True,
            ),
        )
    )

    CompletionStage().run(context)

    printed = capsys.readouterr().out
    assert "Watchlist Auto  : +1 incluído(s), -1 removido(s)" in printed
    assert "[AUTO-IN]  NEM -- Auto-inclusão: top 30" in printed
    assert "[AUTO-OUT] STALE -- Investment Score 12.0 < 40.0" in printed

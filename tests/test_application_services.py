from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import application.collection as collection_module
import application.intelligence as intelligence_module
import application.reporting as reporting_module
import application.scoring as scoring_module
import application.ticker as ticker_module
from application import (
    CollectionApplicationService,
    HistoryApplicationService,
    IntelligenceApplicationService,
    OperationalRuntimeService,
    ReportingApplicationService,
    ScoringApplicationService,
    TickerAnalysisApplicationService,
)
from storage.history_db import HistoryDatabase
from watchlist.loader import load_watchlist_csv
from watchlist.models import WatchlistEntry, WatchlistTriggerResult


def _logger() -> logging.Logger:
    return logging.getLogger("test_application_services")


def test_collection_service_preserves_origin_and_provider_policy(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "data_quality.yaml").write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_fetch(watchlist, **kwargs):
        captured.update(kwargs)
        return [
            {
                "symbol": "MSFT",
                "price": 100.0,
                "history": object(),
            }
        ]

    monkeypatch.setattr(collection_module, "fetch_watchlist", fake_fetch)
    sec_provider = object()
    monkeypatch.setattr(
        collection_module,
        "build_sec_secondary_provider",
        lambda *args: sec_provider,
    )
    fmp_provider = SimpleNamespace(
        fetch_float=lambda symbol: {},
        prefetch=lambda symbols: {"mode": "on_demand"},
    )
    monkeypatch.setattr(
        collection_module,
        "build_fmp_secondary_provider",
        lambda *args: fmp_provider,
    )
    massive_provider = object()
    massive_kwargs = {}

    def build_massive(*args, **kwargs):
        massive_kwargs.update(kwargs)
        return massive_provider

    monkeypatch.setattr(
        collection_module, "build_massive_secondary_provider", build_massive
    )
    monkeypatch.setattr(
        collection_module, "enrich_technicals", lambda row: row
    )
    monkeypatch.setattr(
        collection_module, "compute_fundamentals", lambda row: row
    )
    monkeypatch.setattr(
        collection_module, "ensure_field_evidence", lambda row: row
    )
    monkeypatch.setattr(
        collection_module,
        "apply_sector_applicability",
        lambda row, policy: row,
    )
    service = CollectionApplicationService(tmp_path, config, _logger())

    result = service.collect_market_data(
        {
            "provider_timeout_seconds": 7,
            "provider_max_retries": 4,
            "provider_rate_limit_per_second": 3,
        },
        pd.DataFrame([{"symbol": "MSFT", "origin": "portfolio"}]),
    )

    assert result.loc[0, "origin"] == "portfolio"
    assert "history" not in result.columns
    policy = captured["provider_policy"]
    assert policy.timeout_seconds == 7
    assert policy.max_retries == 4
    assert policy.rate_limit_per_second == 3
    assert captured["secondary_fetchers"] == (
        massive_provider,
        fmp_provider,
    )
    assert captured["secondary_fetcher"] is sec_provider
    assert massive_kwargs["fundamentals_fetcher"] is sec_provider


def test_scoring_service_uses_governed_paths(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    captured: dict[str, object] = {}

    def fake_normalize(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["normalized"] = True
        return result

    def fake_score(frame, model_path, breakers_path, *, scoring_reference):
        captured.update(
            model_path=model_path,
            breakers_path=breakers_path,
            scoring_reference=scoring_reference,
        )
        return frame

    monkeypatch.setattr(scoring_module, "normalize_columns", fake_normalize)
    monkeypatch.setattr(scoring_module, "score_dataframe", fake_score)
    service = ScoringApplicationService(
        root=tmp_path,
        config=config,
        universe_report_file=tmp_path / "universe.json",
        ranking_report_file=tmp_path / "ranking.json",
        logger=_logger(),
    )

    result = service.build_scores(pd.DataFrame([{"symbol": "MSFT"}]))

    assert bool(result.loc[0, "normalized"])
    assert captured["model_path"] == config / "model.yaml"
    assert captured["breakers_path"] == config / "deal_breakers.json"
    assert captured["scoring_reference"] is None


def test_scoring_service_falls_back_when_reference_is_missing(
    tmp_path: Path,
) -> None:
    service = ScoringApplicationService(
        root=tmp_path,
        config=tmp_path,
        universe_report_file=tmp_path / "universe.json",
        ranking_report_file=tmp_path / "ranking.json",
        logger=_logger(),
    )

    assert service.load_official_reference({}) is None


def test_scoring_service_rejects_incompatible_reference(
    tmp_path: Path, monkeypatch
) -> None:
    reference_path = tmp_path / "reference.json"
    reference_path.write_text("{}", encoding="utf-8")
    reference = SimpleNamespace(
        universe_id="WRONG_UNIVERSE",
        model_version="test-model",
    )
    monkeypatch.setattr(
        scoring_module, "load_scoring_reference", lambda path: reference
    )
    monkeypatch.setattr(
        scoring_module,
        "load_yaml",
        lambda path: {"model_version": "test-model"},
    )
    service = ScoringApplicationService(
        root=tmp_path,
        config=tmp_path,
        universe_report_file=tmp_path / "universe.json",
        ranking_report_file=tmp_path / "ranking.json",
        logger=_logger(),
    )

    assert service.load_official_reference(
        {"scoring_reference_path": str(reference_path)}
    ) is None


def test_scoring_service_audits_phantom_weight(
    tmp_path: Path, monkeypatch
) -> None:
    coverage = object()
    monkeypatch.setattr(
        scoring_module, "audit_coverage", lambda *args: coverage
    )
    monkeypatch.setattr(
        scoring_module,
        "phantom_weight_summary",
        lambda value: {"phantom_investment_share": 12.5},
    )
    monkeypatch.setattr(
        scoring_module,
        "format_coverage_report",
        lambda value, summary: "coverage",
    )
    service = ScoringApplicationService(
        root=tmp_path,
        config=tmp_path,
        universe_report_file=tmp_path / "universe.json",
        ranking_report_file=tmp_path / "ranking.json",
        logger=_logger(),
    )

    summary = service.audit_feature_coverage(pd.DataFrame())

    assert summary["phantom_investment_share"] == 12.5


def test_collection_service_rejects_empty_watchlist(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.csv"
    path.write_text("symbol,name\n", encoding="utf-8")
    service = CollectionApplicationService(tmp_path, tmp_path, _logger())

    try:
        service.load_watchlist({"watchlist_path": str(path)})
    except RuntimeError as exc:
        assert "vazia" in str(exc)
    else:
        raise AssertionError("watchlist vazia deveria falhar")


def test_history_service_persists_and_recovers_previous_run(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "model.yaml").write_text(
        "model_version: test-model\n", encoding="utf-8"
    )
    service = HistoryApplicationService(
        root=tmp_path,
        config=config,
        history_database=tmp_path / "history.db",
        outcome_report_file=tmp_path / "outcomes.json",
        logger=_logger(),
    )
    frame = pd.DataFrame(
        [{"symbol": "AAA", "Investment Score": 72.0, "price": 10.0}]
    )

    saved = service.save_history_snapshot(
        frame, "2026-07-16T10:00:00", "test-model"
    )
    history = service.load_score_history()
    previous, status, run_at = service.previous_run_context(
        history,
        current_snapshot_date="2026-07-17T10:00:00",
        current_model_version="test-model",
    )

    assert saved == "2026-07-16T10:00:00"
    assert service.load_model_config()["model_version"] == "test-model"
    assert previous["AAA"]["investment_score"] == 72.0
    assert status == "comparable"
    assert str(run_at).startswith("2026-07-16")


def _intelligence_service(tmp_path: Path) -> IntelligenceApplicationService:
    return IntelligenceApplicationService(
        root=tmp_path,
        config=tmp_path / "config",
        output_reports=tmp_path / "reports",
        history_database=tmp_path / "history.db",
        portfolio_report_file=tmp_path / "portfolio.json",
        watchlist_report_file=tmp_path / "watchlist.json",
        logger=_logger(),
    )


def _reporting_service(tmp_path: Path, **kwargs) -> ReportingApplicationService:
    return ReportingApplicationService(
        output_reports=tmp_path / "reports",
        history_database=tmp_path / "history.db",
        morning_brief_file=tmp_path / "morning.md",
        performance_validation_file=tmp_path / "performance.json",
        dashboard_report_file=tmp_path / "dashboard.json",
        priority_report_file=tmp_path / "priority.json",
        research_ranking_report_file=tmp_path / "research.json",
        logger=_logger(),
        **kwargs,
    )


def test_reporting_service_respects_disabled_publications(
    tmp_path: Path,
) -> None:
    service = _reporting_service(tmp_path)

    assert service.generate_dashboard(
        pd.DataFrame(), {"dashboard_enabled": False}
    ) is None
    assert service.generate_performance_validation(
        pd.DataFrame(), {"performance_validation_enabled": False}
    ) is None


def test_reporting_service_includes_configured_historical_validation(
    tmp_path: Path,
) -> None:
    validation_path = tmp_path / "historical.json"
    validation_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "summary": {"annualized_return": 0.1},
                "periods": [{}],
                "incomplete_periods": [],
                "return_sources": ["test"],
            }
        ),
        encoding="utf-8",
    )
    service = _reporting_service(tmp_path)
    output = service.generate_performance_validation(
        pd.DataFrame({"Investment Score": [50]}),
        {
            "performance_validation_enabled": True,
            "portfolio_validation_report_path": str(validation_path),
        },
    )

    assert output is not None
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["historical_validation"]["status"] == "complete"
    assert report["historical_validation"]["summary"]["annualized_return"] == 0.1
    assert service.generate_priority_report(
        {"priority_enabled": False},
        ranking_report=None,
        portfolio_report=None,
    ) is None


def test_reporting_service_uses_governed_excel_paths(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    def fake_write(frame, output, **kwargs):
        captured.update(output=output, **kwargs)
        return output / "history.xlsx", output / "latest.xlsx"

    monkeypatch.setattr(
        reporting_module, "write_latest_and_history", fake_write
    )
    service = _reporting_service(tmp_path)

    result = service.generate_excel_reports(pd.DataFrame())

    assert result[0] == tmp_path / "reports" / "history.xlsx"
    assert captured["output"] == tmp_path / "reports"
    assert captured["database_path"] == tmp_path / "history.db"


def test_reporting_service_injects_morning_brief_ports(
    tmp_path: Path,
) -> None:
    received: list[Path] = []

    def fake_write(**kwargs):
        received.append(kwargs["output_path"])
        return kwargs["output_path"]

    service = _reporting_service(
        tmp_path,
        morning_brief_writer=fake_write,
        morning_brief_renderer=lambda **kwargs: "brief",
    )

    assert service.generate_morning_brief(pd.DataFrame()) == (
        tmp_path / "morning.md",
        "brief",
    )
    assert received == [tmp_path / "morning.md"]


def test_ticker_service_composes_analysis_and_one_pager(
    tmp_path: Path, monkeypatch
) -> None:
    portfolio_path = tmp_path / "portfolio.csv"
    portfolio_path.write_text("placeholder", encoding="utf-8")
    reference = object()
    captured: dict[str, object] = {}

    class Collection:
        def collect_market_data(self, settings, universe, **kwargs):
            captured["universe"] = universe.copy()
            return pd.DataFrame(
                [{"symbol": "MSFT", "name": "Microsoft", "raw": 1}]
            )

    class Scoring:
        def load_official_reference(self, settings):
            return reference

        def build_scores(self, frame, scoring_reference=None):
            captured["reference"] = scoring_reference
            result = frame.copy()
            result["Investment Score"] = 81.0
            return result

    class History:
        def load_score_history(self, path=None):
            return pd.DataFrame(
                [
                    {"symbol": "MSFT", "Investment Score": 79.0},
                    {"symbol": "OTHER", "Investment Score": 20.0},
                ]
            )

        def portfolio_path(self, settings):
            return portfolio_path

        def load_portfolio(self, path):
            return SimpleNamespace(
                holding=lambda symbol: SimpleNamespace(thesis="Cloud thesis")
            )

    monkeypatch.setattr(
        ticker_module,
        "compute_symbol_contributions",
        lambda *args: ([{"feature": "quality"}], []),
    )

    def fake_render(**kwargs):
        captured["render"] = kwargs
        return "<main />"

    monkeypatch.setattr(ticker_module, "render_one_pager", fake_render)
    monkeypatch.setattr(
        ticker_module, "page_shell", lambda title, body: f"{title}{body}"
    )
    monkeypatch.setattr(
        ticker_module,
        "write_one_pager",
        lambda html, output, symbol, stamp: output / f"{symbol}.html",
    )
    messages: list[str] = []
    service = TickerAnalysisApplicationService(
        config=tmp_path / "config",
        output_reports=tmp_path / "reports",
        collection=Collection(),
        scoring=Scoring(),
        history=History(),
        logger=_logger(),
        output_writer=messages.append,
    )

    path = service.run_ticker_mode(" msft ", {})

    assert path == tmp_path / "reports" / "MSFT.html"
    assert captured["reference"] is reference
    assert captured["universe"].iloc[0].to_dict() == {
        "symbol": "MSFT",
        "name": "MSFT",
        "origin": "ticker",
    }
    render = captured["render"]
    assert render["investment_score"] == 81.0
    assert render["thesis"] == "Cloud thesis"
    assert render["score_history"]["symbol"].tolist() == ["MSFT"]
    assert messages == [f"One-pager de MSFT gerado em {path}"]


def test_ticker_service_rejects_missing_collected_symbol(
    tmp_path: Path,
) -> None:
    collection = SimpleNamespace(
        collect_market_data=lambda *args, **kwargs: pd.DataFrame(
            [{"symbol": "OTHER"}]
        )
    )
    scoring = SimpleNamespace(
        load_official_reference=lambda settings: None,
        build_scores=lambda frame, reference: frame,
    )
    history = SimpleNamespace()
    service = TickerAnalysisApplicationService(
        config=tmp_path,
        output_reports=tmp_path,
        collection=collection,
        scoring=scoring,
        history=history,
        logger=_logger(),
    )

    try:
        service.run_ticker_mode("MSFT", {})
    except RuntimeError as exc:
        assert "MSFT" in str(exc)
    else:
        raise AssertionError("símbolo ausente deveria falhar")


def test_operational_runtime_loads_settings_and_formats_console(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text(
        '{"source": "test"}', encoding="utf-8"
    )
    output: list[str] = []
    service = OperationalRuntimeService(
        root=tmp_path,
        config=config,
        execution_metrics_file=tmp_path / "metrics.csv",
        logger=_logger(),
        output_writer=output.append,
    )

    assert service.load_settings() == {"source": "test"}
    assert service.safe_console_text("Rating: ★", "cp1252") == "Rating: ?"

    service.print_console_table(
        pd.DataFrame([{"symbol": "MSFT", "Investment Score": 81.0}])
    )

    assert output[0] == ""
    assert "MSFT" in output[1]
    assert "81.0" in output[1]
    assert output[2] == ""


def test_operational_runtime_delegates_health_and_metrics(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, object]] = []
    health_report = object()
    metrics = SimpleNamespace(name="metrics")
    metrics_path = tmp_path / "metrics.csv"
    service = OperationalRuntimeService(
        root=tmp_path,
        config=tmp_path,
        execution_metrics_file=metrics_path,
        logger=_logger(),
        health_check_runner=lambda root: (
            calls.append(("health", root)) or health_report
        ),
        health_report_writer=lambda report: calls.append(
            ("health_report", report)
        ),
        metrics_saver=lambda value, path: calls.append(
            ("metrics_saved", (value, path))
        ),
        metrics_writer=lambda value: calls.append(
            ("metrics_printed", value)
        ),
    )

    assert service.run_health_check() is health_report
    service.print_health_report(health_report)
    service.save_execution_metrics(metrics)
    service.print_execution_metrics(metrics)

    assert calls == [
        ("health", tmp_path),
        ("health_report", health_report),
        ("metrics_saved", (metrics, metrics_path)),
        ("metrics_printed", metrics),
    ]


def test_operational_runtime_reports_missing_settings(tmp_path: Path) -> None:
    service = OperationalRuntimeService(
        root=tmp_path,
        config=tmp_path / "missing",
        execution_metrics_file=tmp_path / "metrics.csv",
        logger=_logger(),
    )

    try:
        service.load_settings()
    except FileNotFoundError as exc:
        assert "settings.json" in str(exc)
    else:
        raise AssertionError("configuração ausente deveria falhar")


def test_intelligence_service_skips_absent_inputs(tmp_path: Path) -> None:
    service = _intelligence_service(tmp_path)

    assert service.generate_portfolio_intelligence(
        pd.DataFrame(), {}
    ) is None
    assert service.generate_watchlist_report(pd.DataFrame(), {}) is None
    assert service.read_status_md() == ""


def test_intelligence_service_builds_portfolio_with_governed_mode(
    tmp_path: Path, monkeypatch
) -> None:
    portfolio_path = tmp_path / "portfolio.csv"
    portfolio_path.write_text("placeholder", encoding="utf-8")
    report = object()
    captured: dict[str, object] = {}

    def fake_build(path, frame, **kwargs):
        captured.update(path=path, **kwargs)
        return report

    monkeypatch.setattr(
        intelligence_module, "build_portfolio_intelligence", fake_build
    )
    monkeypatch.setattr(
        intelligence_module,
        "write_portfolio_report",
        lambda value, path: path,
    )
    service = _intelligence_service(tmp_path)

    result = service.generate_portfolio_intelligence(
        pd.DataFrame(),
        {
            "portfolio_path": str(portfolio_path),
            "portfolio_rebalance_mode": "sell_only",
        },
    )

    assert result == (tmp_path / "portfolio.json", report)
    assert captured["path"] == portfolio_path
    assert captured["rebalance_mode"] == "sell_only"


def test_intelligence_service_renders_and_writes_atlas_report(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        intelligence_module, "render_report", lambda context: "<html />"
    )

    def fake_write(html, output, date):
        captured.update(html=html, output=output, date=date)
        return output / "dated.html", output / "latest.html"

    monkeypatch.setattr(intelligence_module, "write_report", fake_write)
    service = _intelligence_service(tmp_path)

    result = service.render_and_write_report(
        object(), "2026-07-17"
    )

    assert result[0] == tmp_path / "reports" / "dated.html"
    assert captured == {
        "html": "<html />",
        "output": tmp_path / "reports",
        "date": "2026-07-17",
    }


def test_intelligence_service_persists_watchlist_trigger(
    tmp_path: Path, monkeypatch
) -> None:
    watchlist_path = tmp_path / "watchlist.csv"
    watchlist_path.write_text("symbol,name\nMSFT,Microsoft\n", encoding="utf-8")
    entry = WatchlistEntry(
        "MSFT",
        "Microsoft",
        included_at="2026-01-01",
        trigger_condition="price > 100",
    )
    trigger = WatchlistTriggerResult(
        symbol="MSFT",
        trigger_condition="price > 100",
        status="triggered",
        message="Preço acima do limite",
    )
    monkeypatch.setattr(
        intelligence_module, "load_watchlist_csv", lambda path: (entry,)
    )
    monkeypatch.setattr(
        intelligence_module,
        "normalize_current_row",
        lambda row: row,
    )
    monkeypatch.setattr(
        intelligence_module,
        "evaluate_watchlist_triggers",
        lambda *args, **kwargs: (trigger,),
    )
    service = _intelligence_service(tmp_path)

    result = service.generate_watchlist_report(
        pd.DataFrame([{"symbol": "MSFT", "price": 110.0}]),
        {"watchlist_path": str(watchlist_path)},
        current_run_at="2026-07-17T10:00:00",
    )

    assert result is not None
    assert len(result[1].triggered) == 1
    assert (tmp_path / "watchlist.json").exists()
    with HistoryDatabase(tmp_path / "history.db") as database:
        history = database.load_watchlist_triggers()
    assert history["MSFT"]["last_triggered_at"] == "2026-07-17T10:00:00"


def test_intelligence_service_runs_watchlist_auto_curation_end_to_end(
    tmp_path: Path,
) -> None:
    """
    Exercita o caminho real (sem mock) de
    IntelligenceApplicationService.run_watchlist_auto_curation até o disco:
    policy carregada de um watchlist_auto.yaml real, promote_to_watchlist/
    remove_from_watchlist reais gravando um config/watchlist.csv real --
    prova que o wiring de ponta a ponta (não só as peças isoladas já
    testadas em test_watchlist_auto_curation.py) funciona.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist_auto.yaml").write_text(
        "enabled: true\n"
        "selection: {top_n: 30, "
        "qualifying_decisions: [STRONG_BUY, BUY, ACCUMULATE], "
        "min_confidence_score: 60.0}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {protect_portfolio_holdings: true, "
        "protect_manual_entries: true}\n",
        encoding="utf-8",
    )
    watchlist_path = config_dir / "watchlist.csv"
    watchlist_path.write_text(
        "symbol,name,source\nSTALE,Stale Co,auto\nKEPT,Kept Co,manual\n",
        encoding="utf-8",
    )
    sp500_path = tmp_path / "research_ranking_report.json"
    sp500_path.write_text(
        json.dumps(
            {
                "companies": [
                    {
                        "symbol": "FRESH",
                        "name": "Fresh Co",
                        "sector": "Technology",
                        "safeguard_passed": True,
                        "candidate_rank": 1,
                        "investment_score": 88.0,
                        "opportunity_score": 90.0,
                        "conviction_score": 90.0,
                        "confidence_score": 75.0,
                        "deal_breakers": [],
                        "already_held": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        [
            {"symbol": "STALE", "origin": "watchlist", "Investment Score": 12.0},
            {"symbol": "KEPT", "origin": "watchlist", "Investment Score": 12.0},
        ]
    )
    service = _intelligence_service(tmp_path)

    result = service.run_watchlist_auto_curation(
        frame,
        {},
        sp500_report_path=sp500_path,
        broad_market_report_path=None,
        adr_report_path=None,
    )

    assert [c.symbol for c in result.included] == ["FRESH"]
    assert [c.symbol for c in result.excluded] == ["STALE"]

    entries = load_watchlist_csv(watchlist_path)
    by_symbol = {entry.symbol: entry for entry in entries}
    assert set(by_symbol) == {"KEPT", "FRESH"}
    assert by_symbol["FRESH"].source == "auto"
    assert by_symbol["KEPT"].source == "manual"


def test_intelligence_service_auto_curates_adr_candidate_end_to_end(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist_auto.yaml").write_text(
        "enabled: true\n"
        "selection: {top_n: 30, "
        "qualifying_decisions: [STRONG_BUY, BUY, ACCUMULATE], "
        "min_confidence_score: 60.0}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {protect_portfolio_holdings: true, "
        "protect_manual_entries: true}\n",
        encoding="utf-8",
    )
    watchlist_path = config_dir / "watchlist.csv"
    watchlist_path.write_text(
        "symbol,name,source\nADBE,Adobe,manual\n", encoding="utf-8"
    )
    adr_path = tmp_path / "research_ranking_report_adr.json"
    adr_path.write_text(
        json.dumps(
            {
                "companies": [
                    {
                        "symbol": "KGC",
                        "name": "Kinross Gold",
                        "sector": "Basic Materials",
                        "safeguard_passed": True,
                        "investment_score": 88.0,
                        "opportunity_score": 90.0,
                        "conviction_score": 90.0,
                        "confidence_score": 100.0,
                        "deal_breakers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _intelligence_service(tmp_path).run_watchlist_auto_curation(
        pd.DataFrame(columns=["symbol", "origin"]),
        {},
        sp500_report_path=None,
        broad_market_report_path=None,
        adr_report_path=adr_path,
    )

    assert [item.symbol for item in result.included] == ["KGC"]
    entries = load_watchlist_csv(watchlist_path)
    by_symbol = {entry.symbol: entry for entry in entries}
    assert set(by_symbol) == {"ADBE", "KGC"}
    assert by_symbol["KGC"].source == "auto"
    assert "Auto-inclusão (adr)" in by_symbol["KGC"].note


def test_intelligence_service_watchlist_auto_curation_respects_disabled_flag(
    tmp_path: Path,
) -> None:
    """O arquivo real ship com enabled: false -- o método precisa honrar
    isso sem tocar o CSV, mesmo quando chamado."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist_auto.yaml").write_text(
        "enabled: false\n", encoding="utf-8"
    )
    watchlist_path = config_dir / "watchlist.csv"
    original = "symbol,name,source\nSTALE,Stale Co,auto\n"
    watchlist_path.write_text(original, encoding="utf-8")
    frame = pd.DataFrame(
        [{"symbol": "STALE", "origin": "watchlist", "Investment Score": 1.0}]
    )
    service = _intelligence_service(tmp_path)

    result = service.run_watchlist_auto_curation(
        frame,
        {},
        sp500_report_path=None,
        broad_market_report_path=None,
        adr_report_path=None,
    )

    assert result.enabled is False
    assert watchlist_path.read_text(encoding="utf-8") == original

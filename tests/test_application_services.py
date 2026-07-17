from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import application.collection as collection_module
import application.intelligence as intelligence_module
import application.reporting as reporting_module
import application.scoring as scoring_module
from application import (
    CollectionApplicationService,
    HistoryApplicationService,
    IntelligenceApplicationService,
    ReportingApplicationService,
    ScoringApplicationService,
)
from storage.history_db import HistoryDatabase
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
    monkeypatch.setattr(
        collection_module, "build_sec_secondary_provider", lambda *args: None
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

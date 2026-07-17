from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import application.collection as collection_module
import application.scoring as scoring_module
from application import (
    CollectionApplicationService,
    HistoryApplicationService,
    ScoringApplicationService,
)


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

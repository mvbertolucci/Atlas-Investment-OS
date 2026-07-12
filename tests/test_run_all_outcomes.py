from __future__ import annotations

from pathlib import Path

import pandas as pd

import run_all
from storage.history_db import HistoryDatabase


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "name": ["Alpha"],
            "price": [25.0],
            "Decision": ["BUY"],
            "Decision Rating": ["Comprar"],
            "Investment Score": [80],
            "Opportunity Score": [85],
            "Conviction Score": [88],
            "Decision Confidence": [90],
            "Risk Penalty": [5],
        }
    )


def test_save_outcome_decisions_integrates_with_history_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "atlas_history.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )

    result = run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-07-12T10:00:00",
        {
            "outcome_analytics_enabled": True,
            "outcome_horizons_days": [30, 90],
        },
    )

    with HistoryDatabase(database_path) as database:
        saved = database.load_outcome_snapshots("AAA")

    assert result is not None
    assert result.saved_count == 1
    assert result.horizons_days == (30, 90)
    assert len(saved) == 1


def test_save_outcome_decisions_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "disabled.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )

    result = run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-07-12T10:00:00",
        {"outcome_analytics_enabled": False},
    )

    assert result is None
    assert not database_path.exists()


def test_evaluate_outcome_decisions_integrates_with_pipeline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "evaluation.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )
    settings = {
        "outcome_analytics_enabled": True,
        "outcome_horizons_days": [30],
    }

    run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-01-01T10:00:00",
        settings,
    )
    current = _analysis_frame()
    current["price"] = [30.0]
    result = run_all.evaluate_outcome_decisions(
        current,
        "2026-02-02T10:00:00",
        settings,
    )

    assert result is not None
    assert result.evaluated_count == 1
    assert result.results[0].return_pct == 20.0


def test_evaluate_outcome_decisions_can_be_disabled() -> None:
    result = run_all.evaluate_outcome_decisions(
        _analysis_frame(),
        "2026-02-02T10:00:00",
        {"outcome_analytics_enabled": False},
    )

    assert result is None

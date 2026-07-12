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

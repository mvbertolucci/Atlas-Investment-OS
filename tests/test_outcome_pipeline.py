from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcomes.pipeline import (
    DEFAULT_OUTCOME_HORIZONS_DAYS,
    build_outcome_snapshots,
    capture_outcome_snapshots,
    normalize_outcome_horizons,
)
from storage.history_db import HistoryDatabase


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "name": ["Alpha", "Beta", "Gamma"],
            "price": [10.0, None, 0.0],
            "Decision": ["BUY", "HOLD", "WATCH"],
            "Decision Rating": ["Comprar", "Manter", "Observar"],
            "Investment Score": [80, 60, 50],
            "Opportunity Score": [85, 62, 45],
            "Conviction Score": [88, 60, 42],
            "Decision Confidence": [90, 70, 55],
            "Risk Penalty": [5, 10, 15],
            "Deal Breakers": ["", "", "Liquidity"],
        }
    )


def test_normalize_outcome_horizons() -> None:
    assert normalize_outcome_horizons(None) == (
        DEFAULT_OUTCOME_HORIZONS_DAYS
    )
    assert normalize_outcome_horizons([90, 30, 90, "180"]) == (
        30,
        90,
        180,
    )


@pytest.mark.parametrize(
    "value",
    [[], "30,90", [0], [-1], [30.5], [True], ["invalid"]],
)
def test_normalize_outcome_horizons_rejects_invalid(value) -> None:
    with pytest.raises(ValueError):
        normalize_outcome_horizons(value)


def test_build_outcome_snapshots_skips_invalid_prices() -> None:
    result = build_outcome_snapshots(
        _analysis_frame(),
        decision_date="2026-07-12T10:00:00",
        horizons_days=[30, 90],
    )

    assert result.saved_count == 1
    assert result.snapshots[0].symbol == "AAA"
    assert result.snapshots[0].decision_price == 10.0
    assert result.skipped_symbols == ("BBB", "CCC")
    assert result.horizons_days == (30, 90)


def test_capture_outcome_snapshots_persists_valid_rows(
    tmp_path: Path,
) -> None:
    with HistoryDatabase(tmp_path / "history.db") as database:
        result = capture_outcome_snapshots(
            database,
            _analysis_frame(),
            decision_date="2026-07-12T10:00:00",
        )
        saved = database.load_outcome_snapshots()

    assert result.saved_count == 1
    assert len(saved) == 1
    assert saved.loc[0, "symbol"] == "AAA"


def test_capture_outcome_snapshots_requires_history_database() -> None:
    with pytest.raises(TypeError):
        capture_outcome_snapshots(
            object(),
            _analysis_frame(),
            decision_date="2026-07-12T10:00:00",
        )

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import run_all

from scoring.investment import score_dataframe
from scoring.reference import (
    build_scoring_reference,
    load_scoring_reference,
    percentile_rank,
    write_scoring_reference,
)
from reports.atlas_report.one_pager import compute_symbol_contributions
from storage.history_db import HistoryDatabase


def _config(tmp_path: Path) -> tuple[Path, Path, Path]:
    features = tmp_path / "features.yaml"
    features.write_text(
        "business:\n"
        "  roe:\n"
        "    label: ROE\n"
        "    weight: 1.0\n"
        "    higher_is_better: true\n"
        "    percentile_scope: sector\n"
        "timing:\n"
        "  momentum_3m:\n"
        "    label: Momentum 3M\n"
        "    weight: 1.0\n"
        "    higher_is_better: true\n",
        encoding="utf-8",
    )
    model = tmp_path / "model.yaml"
    model.write_text(
        'model_version: "test-1"\n'
        "factor_weights:\n"
        "  business: 0.5\n"
        "  timing: 0.5\n",
        encoding="utf-8",
    )
    breakers = tmp_path / "deal_breakers.json"
    breakers.write_text("{}", encoding="utf-8")
    return features, model, breakers


def _reference_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [f"T{i}" for i in range(5)] + [f"E{i}" for i in range(5)],
            "sector": ["Technology"] * 5 + ["Energy"] * 5,
            "roe": [10, 20, 30, 40, 50, 1, 2, 3, 4, 5],
            "momentum_3m": [-10, -5, 0, 5, 10, -20, -10, 0, 10, 20],
        }
    )


def _reference(tmp_path: Path):
    features, model, _ = _config(tmp_path)
    return build_scoring_reference(
        _reference_frame(),
        features_path=features,
        model_path=model,
        universe_id="US_MARKET_ELIGIBLE",
        reference_date="2026-07-13",
        reference_version="7",
        min_sector_size=5,
    )


def test_reference_roundtrip_preserves_versioned_contract(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    output = write_scoring_reference(reference, tmp_path / "reference.json")
    loaded = load_scoring_reference(output)

    assert loaded == reference
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["contract_version"] == "1.0"
    assert payload["universe_id"] == "US_MARKET_ELIGIBLE"
    assert payload["reference_date"] == "2026-07-13"
    assert payload["reference_count"] == 10
    assert payload["reference_version"] == "7"


def test_score_is_invariant_to_companion_rows_with_official_reference(
    tmp_path: Path,
) -> None:
    _, model, breakers = _config(tmp_path)
    reference = _reference(tmp_path)
    target = {
        "symbol": "TARGET",
        "sector": "Technology",
        "roe": 35.0,
        "momentum_3m": 2.0,
    }
    alone = score_dataframe(
        pd.DataFrame([target]), model, breakers, scoring_reference=reference
    )
    with_companion = score_dataframe(
        pd.DataFrame(
            [target, {"symbol": "OTHER", "sector": "Energy", "roe": 999, "momentum_3m": 999}]
        ),
        model,
        breakers,
        scoring_reference=reference,
    )

    score_columns = [
        "Business Score",
        "Timing Score",
        "Investment Score",
    ]
    assert alone.loc[0, score_columns].to_dict() == (
        with_companion.loc[with_companion["symbol"] == "TARGET", score_columns]
        .iloc[0]
        .to_dict()
    )
    assert alone.loc[0, "reference_universe"] == "US_MARKET_ELIGIBLE"
    assert alone.loc[0, "reference_date"] == "2026-07-13"
    assert alone.loc[0, "reference_count"] == 10
    assert alone.loc[0, "reference_version"] == "7"
    positive, negative = compute_symbol_contributions(
        alone,
        "TARGET",
        tmp_path / "features.yaml",
        model,
    )
    assert positive or negative
    assert any(item.percentile != 50.0 for item in (*positive, *negative))


def test_sector_scope_uses_sector_distribution(tmp_path: Path) -> None:
    reference = _reference(tmp_path)
    targets = pd.DataFrame(
        {
            "symbol": ["TECH", "ENERGY"],
            "sector": ["Technology", "Energy"],
            "roe": [6.0, 6.0],
        }
    )
    scores = percentile_rank(
        targets,
        "roe",
        higher_is_better=True,
        reference=reference,
        scope="sector",
    )

    assert scores.iloc[0] < scores.iloc[1]


def test_missing_reference_keeps_legacy_current_batch_metadata(
    tmp_path: Path,
) -> None:
    _, model, breakers = _config(tmp_path)
    result = score_dataframe(
        pd.DataFrame(
            [
                {"symbol": "A", "sector": "Technology", "roe": 10, "momentum_3m": 1},
                {"symbol": "B", "sector": "Technology", "roe": 20, "momentum_3m": 2},
            ]
        ),
        model,
        breakers,
    )
    assert set(result["reference_universe"]) == {"CURRENT_BATCH"}
    assert set(result["reference_count"]) == {2}
    assert set(result["reference_version"]) == {"legacy-cross-sectional"}


def test_run_all_loads_compatible_official_reference(tmp_path: Path) -> None:
    reference = replace(_reference(tmp_path), model_version="0.3")
    path = write_scoring_reference(reference, tmp_path / "official.json")
    loaded = run_all.load_official_scoring_reference(
        {
            "scoring_reference_path": str(path),
            "scoring_reference_universe_id": "US_MARKET_ELIGIBLE",
        }
    )
    assert loaded == reference


def test_history_persists_score_reference_metadata(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "Investment Score": 75.0,
                "reference_universe": "US_MARKET_ELIGIBLE",
                "reference_date": "2026-07-13",
                "reference_count": 2429,
                "reference_version": "1",
                "Data Coverage": 88.0,
                "Source Quality": 80.0,
                "Data Freshness": 100.0,
                "Missing Required Features": "valuation:pe",
                "Risk Evidence Missing": "short_float",
                "Observed Risk Penalty": 4.0,
                "Risk Uncertainty Penalty": 3.0,
                "field_evidence": {
                    "market_cap": {
                        "status": "present",
                        "retrieved_at": "2026-07-17T09:59:00+00:00",
                    }
                },
                "raw_snapshot_hash": "abc123",
                "raw_snapshot_path": "data/raw_snapshots/abc123.json",
            }
        ]
    )
    with HistoryDatabase(tmp_path / "history.db") as database:
        database.save_snapshot(frame, "2026-07-17T10:00:00", "0.3")
        history = database.load_history("AAA")
    row = history.iloc[0]
    assert row["reference_universe"] == "US_MARKET_ELIGIBLE"
    assert row["reference_date"] == "2026-07-13"
    assert row["reference_count"] == 2429
    assert row["reference_version"] == "1"
    assert row["score_coverage"] == 88.0
    assert row["source_quality"] == 80.0
    assert row["data_freshness"] == 100.0
    assert row["missing_required_features"] == "valuation:pe"
    assert row["risk_evidence_missing"] == "short_float"
    assert row["observed_risk_penalty"] == 4.0
    assert row["risk_uncertainty_penalty"] == 3.0
    assert json.loads(row["field_evidence_json"])["market_cap"]["status"] == (
        "present"
    )
    assert row["raw_snapshot_hash"] == "abc123"
    assert row["raw_snapshot_path"] == "data/raw_snapshots/abc123.json"

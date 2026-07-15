from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from reports.atlas_report.broad_screener import load_broad_screener_summary


def _write_report(path: Path, *, generated_at: str) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "policy": {"name": "Test"},
                "summary": {
                    "total_count": 100,
                    "universe_eligible_count": 40,
                    "candidate_count": 5,
                    "blocked_by_reason": {"DEAL_BREAKER_TRIGGERED": 10},
                },
                "companies": [
                    {
                        "symbol": "ZZZ",
                        "sector": "Tech",
                        "safeguard_passed": True,
                        "candidate_rank": 2,
                        "investment_score": 70.0,
                        "confidence_score": 80.0,
                    },
                    {
                        "symbol": "AAA",
                        "sector": "Health",
                        "safeguard_passed": True,
                        "candidate_rank": 1,
                        "investment_score": 80.0,
                        "confidence_score": 90.0,
                    },
                    {
                        "symbol": "BLOCKED",
                        "sector": "Energy",
                        "safeguard_passed": False,
                        "candidate_rank": None,
                        "investment_score": 20.0,
                        "confidence_score": 30.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_missing_file_is_not_included(tmp_path: Path) -> None:
    summary = load_broad_screener_summary(
        "Mercado Amplo", tmp_path / "does_not_exist.json", as_of=pd.Timestamp("2026-07-14")
    )
    assert summary.included is False


def test_malformed_json_is_not_included_not_a_crash(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    summary = load_broad_screener_summary(
        "Mercado Amplo", path, as_of=pd.Timestamp("2026-07-14")
    )
    assert summary.included is False


def test_valid_report_ranks_candidates_and_excludes_non_candidates(tmp_path: Path) -> None:
    path = tmp_path / "research_ranking_report_market.json"
    _write_report(path, generated_at="2026-07-01T00:00:00")
    summary = load_broad_screener_summary(
        "Mercado Amplo", path, as_of=pd.Timestamp("2026-07-14T00:00:00")
    )
    assert summary.included is True
    assert summary.total_count == 100
    assert summary.candidate_count == 5
    assert [c["symbol"] for c in summary.top_candidates] == ["AAA", "ZZZ"]
    assert "BLOCKED" not in [c["symbol"] for c in summary.top_candidates]
    assert summary.age_days == pytest.approx(13.0, abs=0.1)
    assert summary.stale is False


def test_old_collection_is_flagged_stale(tmp_path: Path) -> None:
    path = tmp_path / "research_ranking_report_adr.json"
    _write_report(path, generated_at="2026-01-01T00:00:00")
    summary = load_broad_screener_summary(
        "ADR", path, as_of=pd.Timestamp("2026-07-14T00:00:00")
    )
    assert summary.stale is True

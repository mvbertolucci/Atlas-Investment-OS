from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import run_all
from universe import UniversePolicy, evaluate_universe


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "symbol": "AAA", "sector": "Technology",
            "quote_type": "EQUITY", "currency": "USD",
            "country": "United States", "price": 100.0,
            "market_cap": 10_000_000_000.0, "volume": 1_000_000.0,
            "Investment Score": 80.0, "Opportunity Score": 90.0,
            "Conviction Score": 85.0, "Confidence Score": 100.0,
            "Data Coverage": 100.0, "Source Quality": 80.0,
            "Data Freshness": 100.0, "Missing Required Features": "Nenhum",
            "Deal Breakers": "Nenhum",
        }])


def _universe(frame: pd.DataFrame):
    return evaluate_universe(
        frame,
        UniversePolicy("US", "S&P 500", "monthly"),
    )


def test_generate_ranking_report_writes_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "ranking.json"
    monkeypatch.setattr(run_all, "RANKING_REPORT_FILE", output)
    frame = _frame()

    report = run_all.generate_ranking_report(
        frame,
        {"ranking_policy_path": "config/ranking.yaml"},
        _universe(frame),
    )

    assert report is not None
    assert report.candidate_count == 1
    assert json.loads(output.read_text(encoding="utf-8"))["companies"][0][
        "candidate_rank"
    ] == 1


def test_generate_ranking_report_requires_enabled_universe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "ranking.json"
    monkeypatch.setattr(run_all, "RANKING_REPORT_FILE", output)

    assert run_all.generate_ranking_report(
        _frame(), {"ranking_enabled": False}, None
    ) is None
    assert run_all.generate_ranking_report(
        _frame(), {"ranking_enabled": True}, None
    ) is None
    assert not output.exists()

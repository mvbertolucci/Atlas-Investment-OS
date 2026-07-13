from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import run_all


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "quote_type": "EQUITY",
                "currency": "USD",
                "country": "United States",
                "sector": "Technology",
                "industry": "Software",
                "price": 100.0,
                "market_cap": 10_000_000_000.0,
                "volume": 1_000_000.0,
            }
        ]
    )


def test_generate_universe_report_writes_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "universe_report.json"
    monkeypatch.setattr(run_all, "UNIVERSE_REPORT_FILE", output)

    report = run_all.generate_universe_report(
        _frame(),
        {
            "universe_enabled": True,
            "universe_policy_path": "config/universe.yaml",
        },
    )

    assert report is not None
    assert report.eligible_count == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["eligible_count"] == 1


def test_generate_universe_report_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "universe_report.json"
    monkeypatch.setattr(run_all, "UNIVERSE_REPORT_FILE", output)

    report = run_all.generate_universe_report(
        _frame(),
        {"universe_enabled": False},
    )

    assert report is None
    assert not output.exists()

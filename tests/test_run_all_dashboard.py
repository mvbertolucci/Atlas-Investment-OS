from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import run_all


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "name": ["Alpha", "Beta"],
            "Decision": ["BUY", "AVOID"],
            "Decision Rating": ["Comprar", "Evitar"],
            "Investment Score": [80, 40],
            "Opportunity Score": [85, 30],
            "Risk Penalty": [5, 15],
        }
    )


class _Stub:
    """Duck-typed report with a to_dict(), like PortfolioReport/outcomes."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


def test_generate_dashboard_writes_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "dashboard.json"
    monkeypatch.setattr(run_all, "DASHBOARD_REPORT_FILE", output)

    path = run_all.generate_dashboard(
        _analysis_frame(),
        {"dashboard_enabled": True},
    )

    assert path == output
    snapshots = list((tmp_path / "history" / "decision_queue").glob("decision_queue_*.json"))
    assert len(snapshots) == 1
    delta = json.loads((tmp_path / "decision_delta.json").read_text(encoding="utf-8"))
    assert delta["contract_version"] == "1.0"
    assert delta["baseline_generated_at"] is None
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["contract_version"]
    assert [c["symbol"] for c in data["companies"]] == ["AAA", "BBB"]
    # Read-only: not wired yet -> market None; no portfolio/outcomes passed.
    assert data["market"] is None
    assert data["portfolio"] is None
    assert data["outcomes"] is None


def test_generate_dashboard_includes_all_optional_views(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "dashboard.json"
    monkeypatch.setattr(run_all, "DASHBOARD_REPORT_FILE", output)

    run_all.generate_dashboard(
        _analysis_frame(),
        {"dashboard_enabled": True},
        portfolio_report=_Stub({"portfolio_name": "Main"}),
        outcome_report=_Stub({"hit_rate": {"hit_rate": 100.0}}),
        universe_report=_Stub({"summary": {"eligible_count": 2}}),
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["portfolio"] == {"portfolio_name": "Main"}
    assert data["outcomes"] == {"hit_rate": {"hit_rate": 100.0}}
    assert data["market"] == {"summary": {"eligible_count": 2}}


def test_generate_dashboard_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "dashboard.json"
    monkeypatch.setattr(run_all, "DASHBOARD_REPORT_FILE", output)

    result = run_all.generate_dashboard(
        _analysis_frame(),
        {"dashboard_enabled": False},
    )

    assert result is None
    assert not output.exists()

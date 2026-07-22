from __future__ import annotations

import json

from backtesting.readiness import audit_historical_readiness, write_readiness_report


def test_readiness_reports_missing_point_in_time_inputs(tmp_path) -> None:
    prices = tmp_path / "prices"
    prices.mkdir()
    (prices / "AAA.csv").write_text(
        "Date,Close\n2025-01-01,10\n2025-02-01,11\n", encoding="utf-8"
    )
    (prices / "SPY.csv").write_text(
        "Date,Close\n2025-01-01,100\n2025-02-01,102\n", encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"constituent_count": 2}), encoding="utf-8")

    report = audit_historical_readiness(
        price_dir=prices,
        universe_manifest_path=manifest,
    )

    assert report.status == "BLOCKED"
    assert report.price_file_count == 2
    assert report.price_coverage == 1.0
    assert "POINT_IN_TIME_FUNDAMENTALS_MISSING" in report.blockers
    assert "EXECUTION_EVIDENCE_MISSING" in report.blockers


def test_readiness_report_round_trips(tmp_path) -> None:
    report = audit_historical_readiness(price_dir=tmp_path / "missing")
    path = write_readiness_report(report, tmp_path / "readiness.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED"
    assert payload["price_file_count"] == 0

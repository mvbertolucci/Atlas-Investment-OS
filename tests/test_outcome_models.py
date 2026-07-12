from __future__ import annotations

from datetime import datetime

import pytest

from outcomes.models import OutcomeSnapshot
from reports.report_models import CompanyReport


def test_outcome_snapshot_normalizes_and_serializes() -> None:
    snapshot = OutcomeSnapshot(
        decision_date="2026-07-12T10:30:00",
        symbol=" aaa ",
        company_name=" Alpha ",
        decision_price="123.4567891",
        decision=" buy ",
        investment_score=101,
        opportunity_score=-2,
        conviction_score=float("nan"),
        decision_confidence="invalid",
        risk_penalty=12.34,
        has_deal_breaker=1,
    )

    assert snapshot.symbol == "AAA"
    assert snapshot.decision == "BUY"
    assert snapshot.decision_price == 123.456789
    assert snapshot.investment_score == 100.0
    assert snapshot.opportunity_score == 0.0
    assert snapshot.conviction_score is None
    assert snapshot.decision_confidence is None
    assert snapshot.risk_penalty == 12.3
    assert snapshot.has_deal_breaker is True
    assert snapshot.to_dict()["decision_date"] == (
        "2026-07-12T10:30:00"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", ""),
        ("decision", "UNKNOWN"),
        ("decision_price", 0),
        ("decision_price", -1),
        ("decision_price", "invalid"),
        ("decision_date", "not-a-date"),
    ],
)
def test_outcome_snapshot_rejects_invalid_contract(
    field: str,
    value,
) -> None:
    values = {
        "decision_date": datetime(2026, 7, 12),
        "symbol": "AAA",
        "decision_price": 100.0,
        "decision": "HOLD",
    }
    values[field] = value

    with pytest.raises(ValueError):
        OutcomeSnapshot(**values)


def test_outcome_snapshot_builds_from_company_report() -> None:
    report = CompanyReport(
        symbol="AAA",
        company_name="Alpha",
        decision="BUY",
        decision_rating="★★★★ Comprar",
        investment_score=80,
        opportunity_score=85,
        conviction_score=88,
        decision_confidence=90,
        risk_penalty=5,
        deal_breakers=("Liquidity",),
        generated_at=datetime(2026, 7, 12, 9, 0, 0),
    )

    snapshot = OutcomeSnapshot.from_company_report(
        report,
        decision_price=42.5,
    )

    assert snapshot.symbol == "AAA"
    assert snapshot.decision_date == report.generated_at
    assert snapshot.decision_price == 42.5
    assert snapshot.opportunity_score == 85.0
    assert snapshot.has_deal_breaker is True


def test_outcome_snapshot_requires_company_report() -> None:
    with pytest.raises(TypeError):
        OutcomeSnapshot.from_company_report(
            object(),
            decision_price=10,
        )

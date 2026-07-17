from __future__ import annotations

import pandas as pd

from providers.evidence import (
    DataValueStatus,
    apply_sector_applicability,
    ensure_field_evidence,
    field_status,
    reconcile_critical_fields,
)
from universe import UniversePolicy, evaluate_universe


def _record(source: str, **values):
    record = {
        "symbol": "AAA",
        "source": source,
        "as_of": "2026-07-17T12:00:00+00:00",
        **values,
    }
    return ensure_field_evidence(record, source=source)


def test_field_evidence_distinguishes_all_non_present_states() -> None:
    record = {
        "symbol": "AAA",
        "sector": "Banks",
        "missing_value": None,
        "unavailable_value": None,
        "invalid_value": None,
        "stale_value": 1.0,
        "altman_z": 2.0,
        "source": "Test",
        "as_of": "2025-01-01T00:00:00+00:00",
    }
    ensure_field_evidence(
        record,
        raw_presence={
            "missing_value": False,
            "unavailable_value": True,
            "invalid_value": True,
            "stale_value": True,
            "altman_z": True,
        },
        raw_values={
            "unavailable_value": None,
            "invalid_value": "not-a-number",
            "stale_value": 1.0,
            "altman_z": 2.0,
        },
        observed_at_by_category={"fundamentals": "2025-01-01T00:00:00+00:00"},
    )
    apply_sector_applicability(
        record,
        {
            "freshness": {"acceptable_days": 35},
            "not_applicable_by_sector": {"Banks": ["altman_z"]},
        },
    )

    assert field_status(record, "missing_value") == DataValueStatus.MISSING
    assert field_status(record, "unavailable_value") == DataValueStatus.UNAVAILABLE
    assert field_status(record, "invalid_value") == DataValueStatus.INVALID
    assert field_status(record, "stale_value") == DataValueStatus.STALE
    assert field_status(record, "altman_z") == DataValueStatus.NOT_APPLICABLE


def test_critical_field_uses_secondary_fallback_and_confirmation() -> None:
    primary = _record("Primary", market_cap=None, total_debt=100.0)
    secondary = _record("Secondary", market_cap=500.0, total_debt=102.0)

    result = reconcile_critical_fields(
        primary,
        secondary,
        ("market_cap", "total_debt"),
        tolerance=0.05,
    )

    assert result["market_cap"] == 500.0
    assert result["field_evidence"]["market_cap"]["confirmation_status"] == "fallback"
    assert result["field_evidence"]["total_debt"]["confirmation_status"] == "confirmed"
    assert result["field_evidence"]["total_debt"]["confirmed_by"] == "Secondary"


def test_conflicting_critical_sources_invalidate_value() -> None:
    primary = _record("Primary", market_cap=100.0)
    secondary = _record("Secondary", market_cap=200.0)

    result = reconcile_critical_fields(primary, secondary, ("market_cap",))

    assert result["market_cap"] is None
    assert field_status(result, "market_cap") == DataValueStatus.INVALID
    assert result["field_evidence"]["market_cap"]["confirmation_status"] == "conflict"


def test_critical_field_records_absent_secondary() -> None:
    result = reconcile_critical_fields(
        _record("Primary", market_cap=100.0),
        None,
        ("market_cap",),
    )
    assert result["field_evidence"]["market_cap"]["confirmation_status"] == (
        "secondary_unavailable"
    )


def test_universe_exclusion_preserves_required_field_state() -> None:
    row = {
        "symbol": "AAA",
        "quote_type": "EQUITY",
        "currency": "USD",
        "country": "United States",
        "sector": "Technology",
        "price": 10.0,
        "market_cap": 1_000_000_000.0,
        "volume": 1_000_000.0,
        "field_evidence": {"market_cap": {"status": "stale"}},
    }
    report = evaluate_universe(
        pd.DataFrame([row]),
        UniversePolicy("US", "Benchmark", "monthly"),
    )

    assert report.members[0].eligible is False
    assert "REQUIRED_FIELD_STALE:market_cap" in report.members[0].exclusion_reasons

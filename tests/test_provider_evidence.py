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
    return ensure_field_evidence(
        record,
        source=source,
        observed_at_by_category={"fundamentals": "2026-06-30"},
    )


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


def test_different_fiscal_periods_are_not_compared() -> None:
    primary = _record("Primary", total_debt=100.0)
    secondary = _record("Secondary", total_debt=200.0)
    secondary["field_evidence"]["total_debt"]["observed_at"] = "2025-12-31"

    result = reconcile_critical_fields(primary, secondary, ("total_debt",))

    assert result["total_debt"] == 100.0
    assert result["field_evidence"]["total_debt"]["confirmation_status"] == (
        "period_mismatch"
    )


def test_different_metric_definitions_are_not_compared() -> None:
    primary = _record("Primary", free_cashflow=100.0)
    secondary = _record("Secondary", free_cashflow=200.0)
    primary["field_evidence"]["free_cashflow"]["detail"] = (
        "TTM; not directly comparable to annual"
    )

    result = reconcile_critical_fields(primary, secondary, ("free_cashflow",))

    assert result["free_cashflow"] == 100.0
    assert result["field_evidence"]["free_cashflow"]["confirmation_status"] == (
        "definition_mismatch"
    )


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


# --- Frescor ancorado na cadência de divulgação do emissor -------------------
#
# Casos reproduzidos a partir da carteira real (medição de 2026-07-24): um
# fundamento trimestral passa a maior parte da vida útil com mais de 35 dias,
# e um emissor semestral, quase toda ela. A janela fixa marcava os dois como
# defasados sem que existisse nada mais recente a coletar.

FRESHNESS_POLICY = {
    "freshness": {
        "acceptable_days": 35,
        "period_cadence_categories": ["fundamentals"],
        "default_reporting_period_days": 91,
        "filing_lag_days": 45,
        "max_reporting_period_days": 400,
    }
}


def _dated_record(observed_at: str, *, reporting_period_days: int | None = None):
    record = {
        "symbol": "AAA",
        "source": "Yahoo Finance",
        "as_of": pd.Timestamp.now("UTC").isoformat(),
        "ebitda": 1_000.0,
        "price": 10.0,
    }
    if reporting_period_days is not None:
        record["_reporting_period_days"] = reporting_period_days
    ensure_field_evidence(
        record,
        observed_at_by_field={
            "ebitda": observed_at,
            "price": pd.Timestamp.now("UTC").isoformat(),
        },
    )
    return record


def _days_ago(days: int) -> str:
    return (pd.Timestamp.now("UTC") - pd.Timedelta(days=days)).isoformat()


def test_quarterly_fundamental_within_publication_cycle_is_not_stale() -> None:
    """AVAV: balanço de 30/04 avaliado em 24/07 (85 dias) é o mais recente
    publicado -- o trimestre seguinte nem venceu o prazo de arquivamento."""
    record = _dated_record(_days_ago(85), reporting_period_days=91)
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "ebitda") == DataValueStatus.PRESENT


def test_semiannual_issuer_is_not_stale_at_two_hundred_days() -> None:
    """BTI (Reino Unido) reporta semestralmente: 205 dias após o fechamento
    ainda está dentro do próprio ciclo dele."""
    record = _dated_record(_days_ago(205), reporting_period_days=182)
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "ebitda") == DataValueStatus.PRESENT


def test_quarterly_fundamental_past_filing_deadline_is_stale() -> None:
    """O sinal precisa sobreviver: passado período + prazo de arquivamento,
    existe algo mais novo publicado e nós não temos."""
    record = _dated_record(_days_ago(200), reporting_period_days=91)
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "ebitda") == DataValueStatus.STALE


def test_market_field_keeps_the_wall_clock_window() -> None:
    """Cadência só vale para fundamentos; preço parado há 60 dias continua
    defasado, porque a bolsa não tem calendário de divulgação."""
    record = {
        "symbol": "AAA",
        "source": "Yahoo Finance",
        "as_of": pd.Timestamp.now("UTC").isoformat(),
        "price": 10.0,
    }
    ensure_field_evidence(record, observed_at_by_field={"price": _days_ago(60)})
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "price") == DataValueStatus.STALE


def test_reporting_cadence_is_capped_so_it_cannot_hide_a_collection_gap() -> None:
    """Uma série malformada não pode virar janela infinita."""
    record = _dated_record(_days_ago(900), reporting_period_days=5_000)
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "ebitda") == DataValueStatus.STALE


def test_missing_cadence_falls_back_to_the_quarterly_default() -> None:
    record = _dated_record(_days_ago(85))
    apply_sector_applicability(record, FRESHNESS_POLICY)

    assert field_status(record, "ebitda") == DataValueStatus.PRESENT

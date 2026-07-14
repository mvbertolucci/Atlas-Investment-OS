from __future__ import annotations

from datetime import date

from watchlist.aging import attach_aging
from watchlist.models import WatchlistEntry, WatchlistTriggerResult


def _result(symbol: str, status: str = "clear") -> WatchlistTriggerResult:
    return WatchlistTriggerResult(
        symbol=symbol,
        trigger_condition="score > 75",
        status=status,
        message="x",
    )


def test_age_computed_against_included_at_without_prior_trigger() -> None:
    entries = (WatchlistEntry(symbol="AAA", included_at="2026-01-01"),)
    results = (_result("AAA"),)

    enriched = attach_aging(
        results,
        entries,
        trigger_history={},
        aging_threshold_days=180,
        today=date(2026, 7, 14),
    )
    assert enriched[0].age_days == 194
    assert enriched[0].cleanup_suggested is True


def test_age_computed_against_last_triggered_at_after_firing() -> None:
    entries = (WatchlistEntry(symbol="AAA", included_at="2026-01-01"),)
    results = (_result("AAA"),)

    enriched = attach_aging(
        results,
        entries,
        trigger_history={
            "AAA": {
                "condition_text": "score > 75",
                "last_triggered_at": "2026-07-10",
            }
        },
        aging_threshold_days=180,
        today=date(2026, 7, 14),
    )
    assert enriched[0].age_days == 4
    assert enriched[0].cleanup_suggested is False


def test_missing_both_dates_excludes_from_cleanup_never_assumes_age() -> None:
    entries = (WatchlistEntry(symbol="AAA"),)  # legado, sem included_at
    results = (_result("AAA", status="no_condition"),)

    enriched = attach_aging(
        results,
        entries,
        trigger_history={},
        aging_threshold_days=180,
        today=date(2026, 7, 14),
    )
    assert enriched[0].age_days is None
    assert enriched[0].cleanup_suggested is False


def test_below_threshold_is_not_suggested() -> None:
    entries = (WatchlistEntry(symbol="AAA", included_at="2026-06-01"),)
    results = (_result("AAA"),)

    enriched = attach_aging(
        results,
        entries,
        trigger_history={},
        aging_threshold_days=180,
        today=date(2026, 7, 14),
    )
    assert enriched[0].age_days == 43
    assert enriched[0].cleanup_suggested is False


def test_configurable_threshold_is_respected() -> None:
    entries = (WatchlistEntry(symbol="AAA", included_at="2026-06-01"),)
    results = (_result("AAA"),)

    enriched = attach_aging(
        results,
        entries,
        trigger_history={},
        aging_threshold_days=30,
        today=date(2026, 7, 14),
    )
    assert enriched[0].cleanup_suggested is True

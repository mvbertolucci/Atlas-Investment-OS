from __future__ import annotations

from datetime import date

from watchlist.active_queue import build_active_queue
from watchlist.models import WatchlistEntry, WatchlistTriggerResult


def _result(symbol: str, status: str, *, cleanup: bool = False) -> WatchlistTriggerResult:
    return WatchlistTriggerResult(
        symbol=symbol,
        trigger_condition="score > 80",
        status=status,
        message=status,
        cleanup_suggested=cleanup,
    )


def test_triggered_condition_moves_entry_to_promotion_ready() -> None:
    entry = WatchlistEntry(
        symbol="KGC",
        source="auto",
        lifecycle_state="analyzing",
        analytical_origin="adr",
        entry_rank=1,
        entry_score=72.2,
        review_due_at="2026-08-21",
        promotion_condition="score > 80",
        discard_condition="investment_score < 40",
    )
    queue = build_active_queue(
        [entry], [_result("KGC", "triggered")], as_of=date(2026, 7, 22)
    )

    assert queue[0]["effective_state"] == "promotion_ready"
    assert queue[0]["analytical_origin"] == "adr"
    assert queue[0]["entry_rank"] == 1
    assert queue[0]["entry_score"] == 72.2


def test_clear_condition_waits_and_due_review_requires_attention() -> None:
    waiting = WatchlistEntry(
        symbol="WAIT", promotion_condition="score > 80", review_due_at="2026-08-01"
    )
    due = WatchlistEntry(symbol="DUE", review_due_at="2026-07-22")
    queue = build_active_queue(
        [waiting, due],
        [_result("WAIT", "clear"), _result("DUE", "no_condition")],
        as_of=date(2026, 7, 22),
    )
    by_symbol = {str(item["symbol"]): item for item in queue}

    assert by_symbol["WAIT"]["effective_state"] == "waiting_trigger"
    assert by_symbol["DUE"]["effective_state"] == "review_required"


def test_cleanup_signal_is_discard_review_not_automatic_rejection() -> None:
    entry = WatchlistEntry(symbol="OLD", included_at="2026-01-01")
    queue = build_active_queue(
        [entry],
        [_result("OLD", "clear", cleanup=True)],
        as_of=date(2026, 7, 22),
    )

    assert queue[0]["effective_state"] == "discard_review"
    assert queue[0]["cleanup_suggested"] is True

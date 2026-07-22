from __future__ import annotations

from datetime import date
from typing import Iterable

from watchlist.models import WatchlistEntry, WatchlistTriggerResult


def build_active_queue(
    entries: Iterable[WatchlistEntry],
    results: Iterable[WatchlistTriggerResult],
    *,
    as_of: date,
) -> tuple[dict[str, object], ...]:
    results_by_symbol = {item.symbol: item for item in results}
    queue: list[dict[str, object]] = []
    for entry in entries:
        result = results_by_symbol.get(entry.symbol)
        state = entry.lifecycle_state
        state_reason = "estado-base persistido"
        if result is not None and result.triggered_this_run:
            state, state_reason = "promotion_ready", "condição de promoção disparada"
        elif result is not None and result.cleanup_suggested:
            state, state_reason = "discard_review", "prazo de acompanhamento excedido"
        elif result is not None and result.status in {"invalid_condition", "not_evaluated"}:
            state, state_reason = "review_required", result.message
        elif entry.review_due_at is not None and as_of >= entry.review_due_at:
            state, state_reason = "review_required", "prazo de revisão atingido"
        elif result is not None and result.status == "clear":
            state, state_reason = "waiting_trigger", "condição de promoção ainda não atingida"

        queue.append(
            {
                **entry.to_dict(),
                "effective_state": state,
                "state_reason": state_reason,
                "trigger_status": result.status if result is not None else "not_evaluated",
                "age_days": result.age_days if result is not None else None,
                "cleanup_suggested": (
                    result.cleanup_suggested if result is not None else False
                ),
            }
        )
    priority = {
        "promotion_ready": 0,
        "review_required": 1,
        "discard_review": 2,
        "analyzing": 3,
        "waiting_trigger": 4,
        "monitoring": 5,
    }
    queue.sort(key=lambda item: (priority[str(item["effective_state"])], str(item["symbol"])))
    return tuple(queue)

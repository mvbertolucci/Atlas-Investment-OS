from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Iterable, Mapping

from watchlist.models import WatchlistEntry, WatchlistTriggerResult

DEFAULT_AGING_THRESHOLD_DAYS = 180


def attach_aging(
    results: Iterable[WatchlistTriggerResult],
    entries: Iterable[WatchlistEntry],
    *,
    trigger_history: Mapping[str, Mapping[str, str]],
    aging_threshold_days: int = DEFAULT_AGING_THRESHOLD_DAYS,
    today: date | None = None,
) -> tuple[WatchlistTriggerResult, ...]:
    """
    Enriquece cada resultado com idade e sugestão de limpeza -- segunda
    passada, separada da avaliação de trigger (evaluate_watchlist_triggers).

    Idade = hoje - (last_triggered_at, se já disparou alguma vez; senão
    included_at do CSV). Sem os dois, idade é desconhecida -- o símbolo fica
    de fora da sugestão de limpeza (nunca assume idade sem dado). O sistema
    NUNCA remove um nome sozinho -- só sugere, e a regra vale igual para
    acompanhamento passivo (sem condição) e para condição nunca disparada.
    """
    today = today or date.today()
    entries_by_symbol = {entry.symbol: entry for entry in entries}
    enriched: list[WatchlistTriggerResult] = []

    for result in results:
        entry = entries_by_symbol.get(result.symbol)
        history_row = trigger_history.get(result.symbol)

        last_triggered_at_text = (
            history_row.get("last_triggered_at") if history_row else None
        )
        reference_date: date | None = None
        if last_triggered_at_text:
            try:
                reference_date = date.fromisoformat(
                    last_triggered_at_text[:10]
                )
            except ValueError:
                reference_date = None
        elif entry is not None and entry.included_at is not None:
            reference_date = entry.included_at

        age_days = (
            (today - reference_date).days
            if reference_date is not None
            else None
        )
        cleanup_suggested = (
            age_days is not None and age_days >= aging_threshold_days
        )

        enriched.append(
            replace(
                result,
                age_days=age_days,
                last_triggered_at=last_triggered_at_text,
                cleanup_suggested=cleanup_suggested,
            )
        )

    return tuple(enriched)

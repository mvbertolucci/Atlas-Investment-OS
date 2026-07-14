"""Watchlist como instrumento de acompanhamento (metadado, triggers, aging, promoção)."""

from watchlist.aging import DEFAULT_AGING_THRESHOLD_DAYS, attach_aging
from watchlist.exceptions import WatchlistError
from watchlist.loader import entries_from_dataframe, load_watchlist_csv
from watchlist.models import (
    WatchlistEntry,
    WatchlistReport,
    WatchlistTriggerResult,
)
from watchlist.promote import (
    PromotionResult,
    SymbolAlreadyInWatchlistError,
    promote_to_watchlist,
)
from watchlist.report import write_watchlist_report
from watchlist.triggers import (
    EARNINGS_PASSED,
    FIELD_ALIASES,
    InvalidTriggerConditionError,
    TriggerCondition,
    evaluate_watchlist_triggers,
    normalize_current_row,
    parse_trigger_condition,
)

__all__ = [
    "DEFAULT_AGING_THRESHOLD_DAYS",
    "EARNINGS_PASSED",
    "FIELD_ALIASES",
    "InvalidTriggerConditionError",
    "PromotionResult",
    "SymbolAlreadyInWatchlistError",
    "TriggerCondition",
    "WatchlistEntry",
    "WatchlistError",
    "WatchlistReport",
    "WatchlistTriggerResult",
    "attach_aging",
    "entries_from_dataframe",
    "evaluate_watchlist_triggers",
    "load_watchlist_csv",
    "normalize_current_row",
    "parse_trigger_condition",
    "promote_to_watchlist",
    "write_watchlist_report",
]

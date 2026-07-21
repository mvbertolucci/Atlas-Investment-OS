from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from storage.atomic_write import replace_with_retry


def write_watchlist_rows(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
    *,
    replace_attempts: int = 10,
    retry_delay: float = 0.2,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Rewrite `config/watchlist.csv` atomically, with OneDrive-lock retry.

    Shared by `promote_to_watchlist`/`remove_from_watchlist` so both call
    sites get `storage.atomic_write.replace_with_retry` (already proven for
    `universe/collector.py`/`backtesting/sec_edgar_collector.py`) instead of
    each reimplementing a raw `open("w")` that can lose to a transient
    `PermissionError` from the sync client. `replace_attempts`/`retry_delay`/
    `sleeper` pass straight through, same as `atomic_write_json`, so tests
    can exercise the retry path without a real sleep.
    """
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})
    replace_with_retry(
        temporary,
        path,
        replace_attempts=replace_attempts,
        retry_delay=retry_delay,
        sleeper=sleeper,
    )

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable


def replace_with_retry(
    temporary: Path,
    target: Path,
    *,
    replace_attempts: int = 10,
    retry_delay: float = 0.2,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """`Path.replace()` with bounded retry for a transient `PermissionError`.

    Windows can briefly lock a file mid-write while a sync client (this
    repository lives under OneDrive) is reading it -- `os.replace` then
    raises `WinError 5`. Nothing else in this repository writes these
    files concurrently, so this is not a real conflict; it resolves
    itself within a few hundred milliseconds. Any error other than
    `PermissionError` propagates immediately -- it is not the failure mode
    this guards against, and retrying it would just hide a real bug.

    Originally proven in `universe/collector.py::write_collection_state`
    and `backtesting/sec_edgar_collector.py`; this extracts the same
    behavior so every atomic-write call site in the repository gets it,
    not just the two that happened to hit the failure first.
    """
    if replace_attempts <= 0:
        raise ValueError("replace_attempts deve ser positivo.")
    for attempt in range(replace_attempts):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == replace_attempts - 1:
                raise
            sleeper(retry_delay)


def atomic_write_json(
    path: str | Path,
    payload: Any,
    *,
    replace_attempts: int = 10,
    retry_delay: float = 0.2,
    sleeper: Callable[[float], None] = time.sleep,
    **json_kwargs: Any,
) -> Path:
    """Write `payload` as JSON to `path` atomically, with the same retry.

    `json_kwargs` pass straight through to `json.dumps` -- each caller
    keeps its own formatting (`indent`/`sort_keys` vs. compact
    `separators`) instead of this helper imposing one.
    """
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, **json_kwargs), encoding="utf-8")
    replace_with_retry(
        temporary,
        output,
        replace_attempts=replace_attempts,
        retry_delay=retry_delay,
        sleeper=sleeper,
    )
    return output

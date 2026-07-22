from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


RAW_SNAPSHOT_PATH_ENV = "ATLAS_RAW_SNAPSHOT_PATH"


def resolve_raw_snapshot_path(
    project_root: str | Path,
    configured_path: str | Path = "data/raw_snapshots",
) -> Path:
    """Resolve the workstation override without making config machine-specific."""
    override = os.environ.get(RAW_SNAPSHOT_PATH_ENV)
    candidate = Path(override or configured_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(project_root) / candidate
    return candidate


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, pd.DataFrame):
        return {
            "__type__": "dataframe",
            "columns": [_canonical(item) for item in value.columns.tolist()],
            "index": [_canonical(item) for item in value.index.tolist()],
            "data": [[_canonical(item) for item in row] for row in value.to_numpy().tolist()],
        }
    if isinstance(value, pd.Series):
        return {
            "__type__": "series",
            "index": [_canonical(item) for item in value.index.tolist()],
            "data": [_canonical(item) for item in value.tolist()],
        }
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_canonical(item) for item in value]
    if hasattr(value, "item"):
        return _canonical(value.item())
    return str(value)


def canonical_snapshot_bytes(payload: Mapping[str, Any]) -> bytes:
    normalized = _canonical(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class RawSnapshotReceipt:
    provider: str
    symbol: str
    collected_at: str
    sha256: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "symbol": self.symbol,
            "collected_at": self.collected_at,
            "sha256": self.sha256,
            "path": str(self.path),
        }


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return segment or "unknown"


def store_raw_snapshot(
    payload: Mapping[str, Any],
    root: str | Path,
    *,
    provider: str,
    symbol: str,
    collected_at: str,
) -> RawSnapshotReceipt:
    content = canonical_snapshot_bytes(payload)
    digest = hashlib.sha256(content).hexdigest()
    day = str(collected_at)[:10]
    output = (
        Path(root)
        / _safe_segment(provider)
        / _safe_segment(day)
        / _safe_segment(symbol.upper())
        / f"{digest}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY,
        )
    except FileExistsError:
        if output.read_bytes() != content:
            raise RuntimeError("Snapshot imutável existente diverge do hash.")
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    return RawSnapshotReceipt(
        provider=provider,
        symbol=symbol.upper(),
        collected_at=collected_at,
        sha256=digest,
        path=output,
    )

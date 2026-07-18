from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping


CACHE_VERSION = 1
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FinnhubMetricCache:
    """Per-symbol TTL cache for the Finnhub Basic Financials response."""

    path: Path
    clock: Clock = _utc_now
    _state: dict[str, Any] | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"version": CACHE_VERSION, "updated_at": None, "records": {}}

    def load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            payload = self._empty()
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            payload = self._empty()
        if not isinstance(payload.get("records"), dict):
            payload["records"] = {}
        self._state = payload
        return self._state

    def _save(self) -> None:
        payload = self.load()
        payload["version"] = CACHE_VERSION
        payload["updated_at"] = self.clock().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(self.path)

    def get(self, symbol: str, *, max_age_days: float) -> Any | None:
        entry = self.load()["records"].get(str(symbol).strip().upper())
        if not isinstance(entry, Mapping) or "payload" not in entry:
            return None
        try:
            cached_at = datetime.fromisoformat(str(entry["cached_at"]))
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            return None
        age_days = (
            self.clock().astimezone(timezone.utc)
            - cached_at.astimezone(timezone.utc)
        ).total_seconds() / 86400
        return entry["payload"] if age_days <= max_age_days else None

    def put(self, symbol: str, payload: Any) -> None:
        normalized = str(symbol).strip().upper()
        self.load()["records"][normalized] = {
            "cached_at": self.clock().isoformat(timespec="seconds"),
            "payload": payload,
        }
        self._save()

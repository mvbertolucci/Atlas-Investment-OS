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
class MassiveTickerDetailsCache:
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


@dataclass
class MassiveFloatSnapshotCache:
    path: Path
    clock: Clock = _utc_now
    _state: dict[str, Any] | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "updated_at": None,
            "complete": False,
            "page_count": 0,
            "next_request": None,
            "records": {},
        }

    def load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            payload = self._empty()
        required = {"records": dict, "complete": bool}
        if (
            not isinstance(payload, dict)
            or payload.get("version") != CACHE_VERSION
            or any(
                not isinstance(payload.get(key), kind)
                for key, kind in required.items()
            )
        ):
            payload = self._empty()
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

    def prepare(self, *, max_age_days: float) -> dict[str, Any]:
        payload = self.load()
        try:
            updated_at = datetime.fromisoformat(str(payload["updated_at"]))
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            age_days = (
                self.clock().astimezone(timezone.utc)
                - updated_at.astimezone(timezone.utc)
            ).total_seconds() / 86400
        except (KeyError, TypeError, ValueError):
            age_days = float("inf")
        if age_days > max_age_days:
            self._state = self._empty()
        return self.load()

    def next_request(
        self, *, initial_limit: int
    ) -> tuple[str, dict[str, str]] | None:
        payload = self.load()
        if payload["complete"]:
            return None
        request = payload.get("next_request")
        if isinstance(request, Mapping):
            path = str(request.get("path") or "")
            params = request.get("params")
            if path and isinstance(params, Mapping):
                return path, {str(key): str(value) for key, value in params.items()}
        return "/stocks/vX/float", {
            "limit": str(initial_limit),
            "sort": "ticker.asc",
        }

    def append_page(
        self,
        rows: list[Mapping[str, Any]],
        next_request: tuple[str, Mapping[str, str]] | None,
    ) -> None:
        payload = self.load()
        for row in rows:
            symbol = str(row.get("ticker") or "").strip().upper()
            if symbol:
                payload["records"][symbol] = dict(row)
        payload["page_count"] = max(0, int(payload.get("page_count", 0))) + 1
        payload["complete"] = next_request is None
        payload["next_request"] = (
            None
            if next_request is None
            else {
                "path": next_request[0],
                "params": dict(next_request[1]),
            }
        )
        self._save()

    def lookup(
        self, symbol: str, *, max_age_days: float
    ) -> tuple[Mapping[str, Any] | None, bool]:
        payload = self.prepare(max_age_days=max_age_days)
        normalized = str(symbol).strip().upper()
        candidates = (normalized, normalized.replace("-", "."))
        row = next(
            (
                payload["records"].get(candidate)
                for candidate in candidates
                if isinstance(payload["records"].get(candidate), Mapping)
            ),
            None,
        )
        return (row if isinstance(row, Mapping) else None, payload["complete"])


@dataclass
class MassiveGroupedDailyCache:
    """Caches one full-market end-of-day bar snapshot per trade date.

    A past trade date's OHLC bars never change, so entries never expire --
    unlike ticker details or float snapshots, which describe current state.
    """

    path: Path
    clock: Clock = _utc_now
    _state: dict[str, Any] | None = field(default=None, init=False, repr=False)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"version": CACHE_VERSION, "updated_at": None, "dates": {}}

    def load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            payload = self._empty()
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            payload = self._empty()
        if not isinstance(payload.get("dates"), dict):
            payload["dates"] = {}
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

    def get_date(self, trade_date: str) -> dict[str, Mapping[str, Any]] | None:
        entry = self.load()["dates"].get(str(trade_date))
        if not isinstance(entry, Mapping) or not isinstance(
            entry.get("records"), Mapping
        ):
            return None
        return dict(entry["records"])

    def put_date(
        self, trade_date: str, records: Mapping[str, Mapping[str, Any]]
    ) -> None:
        self.load()["dates"][str(trade_date)] = {
            "fetched_at": self.clock().isoformat(timespec="seconds"),
            "record_count": len(records),
            "records": {
                str(symbol): dict(bar) for symbol, bar in records.items()
            },
        }
        self._save()

    def lookup(
        self, trade_date: str, symbol: str
    ) -> Mapping[str, Any] | None:
        records = self.get_date(trade_date)
        if records is None:
            return None
        normalized = str(symbol).strip().upper()
        candidates = (normalized, normalized.replace("-", "."))
        for candidate in candidates:
            row = records.get(candidate)
            if isinstance(row, Mapping):
                return row
        return None

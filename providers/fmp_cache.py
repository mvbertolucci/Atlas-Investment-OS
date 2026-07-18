from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from providers.contracts import ProviderError, ProviderErrorKind
from storage.atomic_write import replace_with_retry


CACHE_VERSION = 1
Clock = Callable[[], datetime]


class FmpQuotaExceeded(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "Financial Modeling Prep",
            "reserve_call",
            ProviderErrorKind.RATE_LIMITED,
            message,
            retryable=False,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FmpCacheStore:
    path: Path
    clock: Clock = _utc_now
    _state: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _quota_state: dict[str, Any] | None = field(
        default=None, init=False, repr=False
    )

    @property
    def quota_path(self) -> Path:
        return self.path.with_name(
            f"{self.path.stem}_quota{self.path.suffix}"
        )

    def _empty(self) -> dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "updated_at": None,
            "records": {},
        }

    def load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        if not self.path.exists():
            self._state = self._empty()
            return self._state
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            self._state = self._empty()
            return self._state
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            self._state = self._empty()
            return self._state
        if not isinstance(payload.get("records"), dict):
            payload["records"] = {}
        self._state = payload
        return self._state

    def _load_quota(self) -> dict[str, Any]:
        if self._quota_state is not None:
            return self._quota_state
        try:
            payload = json.loads(self.quota_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            payload = {}
        calls = payload.get("calls_by_utc_date")
        self._quota_state = {
            "version": CACHE_VERSION,
            "calls_by_utc_date": calls if isinstance(calls, dict) else {},
        }
        return self._quota_state

    def _save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(payload)
        data["version"] = CACHE_VERSION
        data["updated_at"] = self.clock().isoformat(timespec="seconds")
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        replace_with_retry(temporary, self.path)
        self._state = data

    def _save_quota(self, payload: Mapping[str, Any]) -> None:
        self.quota_path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(payload)
        data["version"] = CACHE_VERSION
        temporary = self.quota_path.with_suffix(
            self.quota_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        replace_with_retry(temporary, self.quota_path)
        self._quota_state = data

    def get(
        self,
        symbol: str,
        category: str,
        *,
        max_age_days: float,
    ) -> Any | None:
        payload = self.load()
        entry = (
            payload.get("records", {})
            .get(str(symbol).strip().upper(), {})
            .get(category)
        )
        if not isinstance(entry, dict) or "payload" not in entry:
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
        if age_days > max_age_days:
            return None
        return entry["payload"]

    def put(self, symbol: str, category: str, value: Any) -> None:
        self.put_many(category, {symbol: value})

    def put_many(
        self,
        category: str,
        values_by_symbol: Mapping[str, Any],
    ) -> None:
        if not values_by_symbol:
            return
        payload = self.load()
        records = payload.setdefault("records", {})
        cached_at = self.clock().isoformat(timespec="seconds")
        for symbol, value in values_by_symbol.items():
            symbol_record = records.setdefault(
                str(symbol).strip().upper(), {}
            )
            symbol_record[category] = {
                "cached_at": cached_at,
                "payload": value,
            }
        self._save(payload)

    def calls_used_today(self) -> int:
        payload = self._load_quota()
        key = self.clock().astimezone(timezone.utc).date().isoformat()
        try:
            return max(0, int(payload["calls_by_utc_date"].get(key, 0)))
        except (TypeError, ValueError):
            return 0

    def reserve_call(
        self,
        *,
        daily_limit: int,
        reserve_calls: int = 0,
    ) -> int:
        if daily_limit <= 0:
            raise ValueError("FMP daily_limit deve ser positivo.")
        if reserve_calls < 0 or reserve_calls >= daily_limit:
            raise ValueError("FMP reserve_calls fora do intervalo válido.")
        payload = self._load_quota()
        key = self.clock().astimezone(timezone.utc).date().isoformat()
        used = max(0, int(payload["calls_by_utc_date"].get(key, 0)))
        ceiling = daily_limit - reserve_calls
        if used >= ceiling:
            raise FmpQuotaExceeded(
                f"FMP daily quota reserved: used={used}, ceiling={ceiling}"
            )
        payload["calls_by_utc_date"][key] = used + 1
        self._save_quota(payload)
        return used + 1

    def remaining(self, *, daily_limit: int) -> int:
        return max(0, daily_limit - self.calls_used_today())

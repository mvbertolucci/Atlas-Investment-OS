from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.evidence import DataValueStatus, FieldEvidence
from providers.fmp_cache import FmpCacheStore, FmpQuotaExceeded


JsonTransport = Callable[[str, Mapping[str, str], str, float], Any]
FMP_BASE_URL = "https://financialmodelingprep.com"


def load_fmp_api_key(
    root: str | Path,
    settings: Mapping[str, Any],
) -> str | None:
    if not bool(settings.get("fmp_secondary_enabled", False)):
        return None
    environment_value = str(os.getenv("FMP_API_KEY") or "").strip()
    if environment_value:
        return environment_value
    configured = Path(
        str(
            settings.get(
                "provider_secrets_path", "config/provider_secrets.json"
            )
        )
    )
    path = configured if configured.is_absolute() else Path(root) / configured
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return None
    value = str(payload.get("fmp_api_key") or "").strip()
    return value or None


def _request_json(
    path: str,
    params: Mapping[str, str],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    request = Request(
        f"{FMP_BASE_URL}{path}?{urlencode(params)}",
        headers={"Accept": "application/json", "apikey": api_key},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"FMP HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"FMP unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("FMP returned invalid JSON") from exc


def _latest_row(payload: Any, date_field: str = "date") -> Mapping[str, Any]:
    if not isinstance(payload, list):
        raise ValueError("FMP response must be a list")
    rows = [item for item in payload if isinstance(item, Mapping)]
    if not rows:
        return {}
    return max(rows, key=lambda item: str(item.get(date_field) or ""))


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _evidence(
    value: float | None,
    *,
    retrieved_at: str,
    observed_at: str | None,
    detail: str,
) -> dict[str, Any]:
    return FieldEvidence(
        status=(
            DataValueStatus.PRESENT
            if value is not None
            else DataValueStatus.UNAVAILABLE
        ),
        source="Financial Modeling Prep",
        category="fundamentals",
        retrieved_at=retrieved_at,
        observed_at=observed_at,
        available_at=retrieved_at,
        detail=detail,
    ).to_dict()


@dataclass(frozen=True)
class FmpMarketDataProvider:
    provider_name = "Financial Modeling Prep"
    supported_fields = frozenset({"market_cap", "enterprise_value"})

    api_key: str
    timeout_seconds: float = 30.0
    transport: JsonTransport = _request_json
    cache: FmpCacheStore | None = None
    daily_call_limit: int = 250
    prefetch_reserve_calls: int = 25
    prefetch_threshold: int = 100
    market_batch_size: int = 100
    float_page_size: int = 1000
    float_max_pages: int = 100
    market_cache_days: float = 2.0
    float_cache_days: float = 7.0
    enterprise_cache_days: float = 120.0
    prefetch_rate_limit_per_second: float = 2.0
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    monotonic: Callable[[], float] = field(
        default=time.monotonic, repr=False
    )
    prefetch_clock_state: list[float] = field(
        default_factory=list, repr=False
    )
    cache_only_symbols: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if not str(self.api_key).strip():
            raise ValueError("FMP api_key não pode ser vazia.")
        if self.timeout_seconds <= 0:
            raise ValueError("FMP timeout_seconds deve ser positivo.")
        if self.daily_call_limit <= 0:
            raise ValueError("FMP daily_call_limit deve ser positivo.")
        if not 0 <= self.prefetch_reserve_calls < self.daily_call_limit:
            raise ValueError("FMP prefetch_reserve_calls inválido.")
        if self.prefetch_threshold <= 0 or self.market_batch_size <= 0:
            raise ValueError("FMP batch settings devem ser positivos.")
        if self.float_page_size <= 0 or self.float_max_pages <= 0:
            raise ValueError("FMP float pagination deve ser positiva.")
        if self.prefetch_rate_limit_per_second <= 0:
            raise ValueError("FMP prefetch rate limit deve ser positivo.")

    def _pace_prefetch(self) -> None:
        minimum_interval = 1.0 / self.prefetch_rate_limit_per_second
        now = self.monotonic()
        if self.prefetch_clock_state:
            wait = minimum_interval - (now - self.prefetch_clock_state[0])
            if wait > 0:
                self.sleeper(wait)
                now = self.monotonic()
        self.prefetch_clock_state[:] = [now]

    def _get(
        self,
        path: str,
        *,
        prefetch: bool = False,
        **params: str,
    ) -> Any:
        if self.cache is not None:
            self.cache.reserve_call(
                daily_limit=self.daily_call_limit,
                reserve_calls=(
                    self.prefetch_reserve_calls if prefetch else 0
                ),
            )
        if prefetch:
            self._pace_prefetch()
        return self.transport(
            path,
            params,
            self.api_key,
            self.timeout_seconds,
        )

    def _payload(
        self,
        cache_symbol: str,
        category: str,
        max_age_days: float,
        path: str,
        **params: str,
    ) -> Any:
        normalized = str(cache_symbol).strip().upper()
        if self.cache is not None:
            cached = self.cache.get(
                normalized,
                category,
                max_age_days=max_age_days,
            )
            if cached is not None:
                return cached
            if normalized in self.cache_only_symbols:
                return []
        payload = self._get(path, **params)
        if self.cache is not None:
            self.cache.put(normalized, category, payload)
        return payload

    def fetch_float(self, symbol: str) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        payload = self._payload(
            normalized,
            "float",
            self.float_cache_days,
            "/stable/shares-float",
            symbol=normalized,
        )
        row = _latest_row(payload)
        return {
            "symbol": normalized,
            "source": "Financial Modeling Prep",
            "free_float": _number(row.get("floatShares")),
            "observed_at": str(row.get("date") or "") or None,
            "_raw_fmp_float": payload,
        }

    @staticmethod
    def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
        for start in range(0, len(values), size):
            yield values[start : start + size]

    @staticmethod
    def _has_row(payload: Any) -> bool:
        return isinstance(payload, list) and any(
            isinstance(row, Mapping) for row in payload
        )

    def prefetch(self, symbols: Iterable[str]) -> dict[str, Any]:
        normalized = sorted(
            {
                str(symbol).strip().upper()
                for symbol in symbols
                if str(symbol).strip()
            }
        )
        used_before = self.cache.calls_used_today() if self.cache else 0
        summary: dict[str, Any] = {
            "requested": len(normalized),
            "mode": "on_demand",
            "market_cached": 0,
            "market_available": 0,
            "float_cached": 0,
            "float_available": 0,
            "enterprise_cached": 0,
            "enterprise_available": 0,
            "quota_used_before": used_before,
            "quota_used_after": used_before,
            "quota_remaining": (
                self.cache.remaining(daily_limit=self.daily_call_limit)
                if self.cache
                else self.daily_call_limit
            ),
            "quota_exhausted": False,
            "error_count": 0,
            "errors": [],
        }

        def record_error(message: str) -> None:
            summary["error_count"] += 1
            if len(summary["errors"]) < 20:
                summary["errors"].append(message)
        if self.cache is None or len(normalized) < self.prefetch_threshold:
            return summary

        summary["mode"] = "batch_cache"
        missing_market = [
            symbol
            for symbol in normalized
            if self.cache.get(
                symbol,
                "market_cap",
                max_age_days=self.market_cache_days,
            )
            is None
        ]
        summary["market_cached"] = len(normalized) - len(missing_market)
        market_complete = True
        for chunk in self._chunks(missing_market, self.market_batch_size):
            try:
                payload = self._get(
                    "/stable/market-capitalization-batch",
                    prefetch=True,
                    symbols=",".join(chunk),
                )
                rows = payload if isinstance(payload, list) else []
                mapped = {
                    str(row.get("symbol") or "").strip().upper(): [row]
                    for row in rows
                    if isinstance(row, Mapping) and row.get("symbol")
                }
                self.cache.put_many("market_cap", mapped)
                summary["market_cached"] += len(mapped)
            except FmpQuotaExceeded:
                summary["quota_exhausted"] = True
                market_complete = False
                break
            except (RuntimeError, ValueError) as exc:
                record_error(f"market_batch:{type(exc).__name__}:{exc}")
                market_complete = False
                break
        missing_market_after = [
            symbol
            for symbol in normalized
            if self.cache.get(
                symbol,
                "market_cap",
                max_age_days=self.market_cache_days,
            )
            is None
        ]
        if market_complete:
            self.cache.put_many(
                "market_cap",
                {symbol: [] for symbol in missing_market_after},
            )

        missing_float = {
            symbol
            for symbol in normalized
            if self.cache.get(
                symbol,
                "float",
                max_age_days=self.float_cache_days,
            )
            is None
        }
        summary["float_cached"] = len(normalized) - len(missing_float)
        float_complete = not summary["quota_exhausted"]
        for page in range(self.float_max_pages):
            if not missing_float or summary["quota_exhausted"]:
                break
            try:
                payload = self._get(
                    "/stable/shares-float-all",
                    prefetch=True,
                    page=str(page),
                    limit=str(self.float_page_size),
                )
                rows = payload if isinstance(payload, list) else []
                mapped = {
                    str(row.get("symbol") or "").strip().upper(): [row]
                    for row in rows
                    if isinstance(row, Mapping)
                    and str(row.get("symbol") or "").strip().upper()
                    in missing_float
                }
                self.cache.put_many("float", mapped)
                missing_float.difference_update(mapped)
                summary["float_cached"] += len(mapped)
                if len(rows) < self.float_page_size:
                    break
            except FmpQuotaExceeded:
                summary["quota_exhausted"] = True
                float_complete = False
                break
            except (RuntimeError, ValueError) as exc:
                record_error(f"float_page:{type(exc).__name__}:{exc}")
                float_complete = False
                break
        if float_complete:
            self.cache.put_many(
                "float", {symbol: [] for symbol in missing_float}
            )

        missing_enterprise = [
            symbol
            for symbol in normalized
            if self._has_row(
                self.cache.get(
                    symbol,
                    "market_cap",
                    max_age_days=self.market_cache_days,
                )
            )
            if self.cache.get(
                symbol,
                "enterprise",
                max_age_days=self.enterprise_cache_days,
            )
            is None
        ]
        summary["enterprise_cached"] = (
            len(normalized) - len(missing_enterprise)
        )
        enterprise_values: dict[str, Any] = {}
        for symbol in missing_enterprise:
            if summary["quota_exhausted"]:
                break
            try:
                payload = self._get(
                    "/stable/enterprise-values",
                    prefetch=True,
                    symbol=symbol,
                )
                enterprise_values[symbol] = payload
                summary["enterprise_cached"] += 1
            except FmpQuotaExceeded:
                summary["quota_exhausted"] = True
            except (RuntimeError, ValueError) as exc:
                record_error(
                    f"enterprise:{symbol}:{type(exc).__name__}:{exc}"
                )
                if "402" in str(exc):
                    enterprise_values[symbol] = []
        self.cache.put_many("enterprise", enterprise_values)

        self.cache_only_symbols.update(normalized)
        used_after = self.cache.calls_used_today()
        summary["quota_used_after"] = used_after
        summary["quota_remaining"] = self.cache.remaining(
            daily_limit=self.daily_call_limit
        )
        for category in ("market_cap", "float", "enterprise"):
            key = "market" if category == "market_cap" else category
            payloads = [
                self.cache.get(
                    symbol,
                    category,
                    max_age_days=(
                        self.market_cache_days
                        if category == "market_cap"
                        else self.float_cache_days
                        if category == "float"
                        else self.enterprise_cache_days
                    ),
                )
                for symbol in normalized
            ]
            summary[f"{key}_cached"] = sum(
                payload is not None for payload in payloads
            )
            summary[f"{key}_available"] = sum(
                self._has_row(payload) for payload in payloads
            )
            summary[f"{key}_missing"] = (
                len(normalized) - summary[f"{key}_available"]
            )
        return summary

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        market_payload = self._payload(
            normalized,
            "market_cap",
            self.market_cache_days,
            "/stable/market-capitalization",
            symbol=normalized,
        )
        enterprise_payload = self._payload(
            normalized,
            "enterprise",
            self.enterprise_cache_days,
            "/stable/enterprise-values",
            symbol=normalized,
        )
        market = _latest_row(market_payload)
        enterprise = _latest_row(enterprise_payload)
        market_cap = _number(market.get("marketCap"))
        debt = _number(enterprise.get("addTotalDebt"))
        cash = _number(enterprise.get("minusCashAndCashEquivalents"))
        enterprise_value = None
        if market_cap is not None and debt is not None and cash is not None:
            enterprise_value = market_cap + debt - cash
        market_date = str(market.get("date") or "") or None
        balance_date = str(enterprise.get("date") or "") or None
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "symbol": normalized,
            "source": "Financial Modeling Prep",
            "as_of": retrieved_at,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "fmp_enterprise_components_observed_at": balance_date,
            "_raw_fmp": {
                "market_capitalization": market_payload,
                "enterprise_values": enterprise_payload,
            },
            "field_evidence": {
                "market_cap": _evidence(
                    market_cap,
                    retrieved_at=retrieved_at,
                    observed_at=market_date,
                    detail="FMP market capitalization",
                ),
                "enterprise_value": _evidence(
                    enterprise_value,
                    retrieved_at=retrieved_at,
                    observed_at=market_date,
                    detail=(
                        "current market cap + latest reported debt - cash; "
                        f"balance_sheet_period={balance_date or 'unavailable'}"
                    ),
                ),
            },
        }


def build_fmp_secondary_provider(
    root: str | Path,
    settings: Mapping[str, Any],
) -> FmpMarketDataProvider | None:
    api_key = load_fmp_api_key(root, settings)
    if not api_key:
        return None
    return FmpMarketDataProvider(
        api_key,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
        cache=FmpCacheStore(
            Path(root)
            / str(
                settings.get(
                    "fmp_cache_path", "data/provider_cache/fmp.json"
                )
            )
        ),
        daily_call_limit=int(settings.get("fmp_daily_call_limit", 250)),
        prefetch_reserve_calls=int(
            settings.get("fmp_prefetch_reserve_calls", 25)
        ),
        prefetch_threshold=int(settings.get("fmp_prefetch_threshold", 100)),
        market_batch_size=int(settings.get("fmp_market_batch_size", 100)),
        float_page_size=int(settings.get("fmp_float_page_size", 1000)),
        float_max_pages=int(settings.get("fmp_float_max_pages", 100)),
        market_cache_days=float(settings.get("fmp_market_cache_days", 2)),
        float_cache_days=float(settings.get("fmp_float_cache_days", 7)),
        enterprise_cache_days=float(
            settings.get("fmp_enterprise_cache_days", 120)
        ),
        prefetch_rate_limit_per_second=float(
            settings.get("provider_rate_limit_per_second", 2)
        ),
    )

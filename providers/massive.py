from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.contracts import (
    ProviderClient,
    ProviderError,
    ProviderErrorKind,
    ProviderPolicy,
)
from providers.evidence import DataValueStatus, FieldEvidence
from providers.massive_cache import MassiveTickerDetailsCache


JsonTransport = Callable[[str, Mapping[str, str], str, float], Any]
FloatFetcher = Callable[[str], Mapping[str, Any]]
FundamentalsFetcher = Callable[[str], Mapping[str, Any]]
MASSIVE_BASE_URL = "https://api.massive.com"


def load_massive_api_key(
    root: str | Path,
    settings: Mapping[str, Any],
) -> str | None:
    if not bool(settings.get("massive_secondary_enabled", False)):
        return None
    environment_value = str(os.getenv("MASSIVE_API_KEY") or "").strip()
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
    value = str(payload.get("massive_api_key") or "").strip()
    return value or None


def _request_json(
    path: str,
    params: Mapping[str, str],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    query = urlencode({**params, "apiKey": api_key})
    request = Request(
        f"{MASSIVE_BASE_URL}{path}?{query}",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Massive HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Massive unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Massive returned invalid JSON") from exc


def _latest_result(payload: Any, date_field: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Massive response must be an object")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Massive response has no results list")
    candidates = [item for item in results if isinstance(item, Mapping)]
    if not candidates:
        return {}
    return max(candidates, key=lambda item: str(item.get(date_field) or ""))


def _result_object(payload: Any) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Massive response must be an object")
    result = payload.get("results")
    if not isinstance(result, Mapping):
        raise ValueError("Massive response has no results object")
    return result


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _evidence(
    value: float | None,
    *,
    source: str = "Massive",
    category: str,
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
        source=source,
        category=category,
        retrieved_at=retrieved_at,
        observed_at=observed_at,
        available_at=retrieved_at,
        detail=detail,
    ).to_dict()


def _dates_within_days(
    left: str | None,
    right: str | None,
    tolerance_days: int,
) -> bool:
    if not left or not right:
        return False
    try:
        difference = date.fromisoformat(left[:10]) - date.fromisoformat(
            right[:10]
        )
        return abs(difference.days) <= tolerance_days
    except ValueError:
        return False


@dataclass(frozen=True)
class MassiveMarketDataProvider:
    provider_name = "Massive"
    supported_fields = frozenset(
        {"market_cap", "enterprise_value", "short_float"}
    )

    api_key: str
    timeout_seconds: float = 30.0
    transport: JsonTransport = _request_json
    float_fetcher: FloatFetcher | None = None
    fundamentals_fetcher: FundamentalsFetcher | None = None
    use_ratios: bool = False
    ticker_details_cache: MassiveTickerDetailsCache | None = None
    ticker_details_cache_days: float = 7.0
    prefetch_policy: ProviderPolicy = ProviderPolicy()
    request_limit_per_minute: int = 5
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    monotonic: Callable[[], float] = field(
        default=time.monotonic, repr=False
    )
    request_times: list[float] = field(default_factory=list, repr=False)
    request_lock: Any = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not str(self.api_key).strip():
            raise ValueError("Massive api_key não pode ser vazia.")
        if self.timeout_seconds <= 0:
            raise ValueError("Massive timeout_seconds deve ser positivo.")
        if self.ticker_details_cache_days <= 0:
            raise ValueError("Massive ticker_details_cache_days deve ser positivo.")
        if self.request_limit_per_minute <= 0:
            raise ValueError(
                "Massive request_limit_per_minute deve ser positivo."
            )

    def _pace_request(self) -> None:
        with self.request_lock:
            now = self.monotonic()
            self.request_times[:] = [
                started
                for started in self.request_times
                if now - started < 60.0
            ]
            if len(self.request_times) >= self.request_limit_per_minute:
                wait = 60.0 - (now - self.request_times[0])
                if wait > 0:
                    self.sleeper(wait)
                    now = self.monotonic()
                self.request_times[:] = [
                    started
                    for started in self.request_times
                    if now - started < 60.0
                ]
            self.request_times.append(now)

    def _get(self, path: str, **params: str) -> Any:
        self._pace_request()
        return self.transport(
            path,
            params,
            self.api_key,
            self.timeout_seconds,
        )

    def fetch_ticker_details(self, symbol: str) -> Any:
        normalized = str(symbol).strip().upper()
        if self.ticker_details_cache is not None:
            cached = self.ticker_details_cache.get(
                normalized, max_age_days=self.ticker_details_cache_days
            )
            if cached is not None:
                return cached
        payload = self._get(f"/v3/reference/tickers/{normalized}")
        _result_object(payload)
        if self.ticker_details_cache is not None:
            self.ticker_details_cache.put(normalized, payload)
        return payload

    def prefetch_ticker_details(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        max_symbols: int | None,
    ) -> dict[str, Any]:
        if self.ticker_details_cache is None:
            raise RuntimeError("Massive ticker-details cache não configurado.")
        if max_symbols is not None and max_symbols <= 0:
            raise ValueError("Massive max_symbols deve ser positivo.")
        normalized = sorted(
            {
                str(symbol).strip().upper()
                for symbol in symbols
                if str(symbol).strip()
            }
        )
        pending = [
            symbol
            for symbol in normalized
            if self.ticker_details_cache.get(
                symbol, max_age_days=self.ticker_details_cache_days
            )
            is None
        ]
        selected = pending if max_symbols is None else pending[:max_symbols]
        summary: dict[str, Any] = {
            "requested": len(normalized),
            "selected": len(selected),
            "attempted": 0,
            "succeeded": 0,
            "negative_cached": 0,
            "error_count": 0,
            "errors": [],
            "stopped_reason": None,
        }
        client = ProviderClient("Massive", self.prefetch_policy)
        for symbol in selected:
            summary["attempted"] += 1
            try:
                client.execute(
                    "ticker_details",
                    self.fetch_ticker_details,
                    symbol,
                )
                summary["succeeded"] += 1
            except ProviderError as exc:
                summary["error_count"] += 1
                if len(summary["errors"]) < 20:
                    summary["errors"].append(
                        {"symbol": symbol, **exc.to_dict()}
                    )
                if exc.kind == ProviderErrorKind.NOT_FOUND:
                    self.ticker_details_cache.put(symbol, {"results": {}})
                    summary["negative_cached"] += 1
                if exc.kind in {
                    ProviderErrorKind.AUTHENTICATION,
                    ProviderErrorKind.RATE_LIMITED,
                }:
                    summary["stopped_reason"] = exc.kind.value
                    break
        payloads = [
            self.ticker_details_cache.get(
                symbol, max_age_days=self.ticker_details_cache_days
            )
            for symbol in normalized
        ]
        available = 0
        for payload in payloads:
            try:
                details = _result_object(payload)
            except ValueError:
                continue
            if _number(details.get("market_cap")) is not None:
                available += 1
        cached = sum(payload is not None for payload in payloads)
        summary.update(
            cached=cached,
            available=available,
            missing=len(normalized) - available,
            remaining=len(normalized) - cached,
            coverage_pct=(
                round(100 * available / len(normalized), 2)
                if normalized
                else 0.0
            ),
            complete=cached == len(normalized),
        )
        return summary

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        endpoint_errors: dict[str, dict[str, str]] = {}
        raw_payloads: dict[str, Any] = {}
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def latest(
            label: str,
            path: str,
            date_field: str,
            **params: str,
        ) -> Mapping[str, Any]:
            try:
                payload = self._get(path, **params)
                raw_payloads[label] = payload
                return _latest_result(payload, date_field)
            except (ProviderError, RuntimeError, ValueError) as exc:
                endpoint_errors[label] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                raw_payloads[label] = {
                    "unavailable": True,
                    "error_type": type(exc).__name__,
                }
                return {}

        try:
            details_payload = self.fetch_ticker_details(normalized)
            raw_payloads["ticker_details"] = details_payload
            details = _result_object(details_payload)
        except (ProviderError, RuntimeError, ValueError) as exc:
            endpoint_errors["ticker_details"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            raw_payloads["ticker_details"] = {
                "unavailable": True,
                "error_type": type(exc).__name__,
            }
            details = {}
        short = latest(
            "short_interest",
            "/stocks/v1/short-interest",
            "settlement_date",
            ticker=normalized,
            limit="10",
            sort="settlement_date.desc",
        )
        float_source = "Massive"
        float_data = latest(
            "float",
            "/stocks/vX/float",
            "effective_date",
            ticker=normalized,
            limit="10",
        )
        native_float = _number(float_data.get("free_float"))
        native_float_date = (
            str(float_data.get("effective_date") or "") or None
        )
        short_date = str(short.get("settlement_date") or "") or None
        if self.float_fetcher is not None and (
            native_float is None
            or not _dates_within_days(short_date, native_float_date, 45)
        ):
            try:
                external_float = self.float_fetcher(normalized)
                raw_payloads["float_fallback"] = external_float.get(
                    "_raw_fmp_float", external_float
                )
                fallback_float = {
                    "free_float": external_float.get("free_float"),
                    "effective_date": external_float.get("observed_at"),
                }
                fallback_value = _number(fallback_float.get("free_float"))
                fallback_date = (
                    str(fallback_float.get("effective_date") or "") or None
                )
                if fallback_value is not None and _dates_within_days(
                    short_date, fallback_date, 45
                ):
                    float_data = fallback_float
                    float_source = "Financial Modeling Prep"
            except (ProviderError, RuntimeError, ValueError) as exc:
                endpoint_errors["float_fallback"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                raw_payloads["float_fallback"] = {
                    "unavailable": True,
                    "error_type": type(exc).__name__,
                }
        market_cap = _number(details.get("market_cap"))
        market_date = (
            str(details.get("last_updated_utc") or "") or retrieved_at
        )
        fundamentals: Mapping[str, Any] = {}
        if self.fundamentals_fetcher is not None:
            try:
                fundamentals = self.fundamentals_fetcher(normalized)
                evidence = fundamentals.get("field_evidence") or {}
                raw_payloads["sec_components"] = {
                    "total_debt": fundamentals.get("total_debt"),
                    "total_cash": fundamentals.get("total_cash"),
                    "field_evidence": {
                        name: evidence.get(name)
                        for name in ("total_debt", "total_cash")
                    },
                }
            except (ProviderError, RuntimeError, ValueError) as exc:
                endpoint_errors["sec_components"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                raw_payloads["sec_components"] = {
                    "unavailable": True,
                    "error_type": type(exc).__name__,
                }
        debt = _number(fundamentals.get("total_debt"))
        cash = _number(fundamentals.get("total_cash"))
        component_evidence = fundamentals.get("field_evidence") or {}
        debt_date = str(
            (component_evidence.get("total_debt") or {}).get("observed_at")
            or ""
        ) or None
        cash_date = str(
            (component_evidence.get("total_cash") or {}).get("observed_at")
            or ""
        ) or None
        components_aligned = _dates_within_days(debt_date, cash_date, 45)
        enterprise_value = None
        if (
            market_cap is not None
            and debt is not None
            and cash is not None
            and components_aligned
        ):
            enterprise_value = market_cap + debt - cash
        short_interest = _number(short.get("short_interest"))
        free_float = _number(float_data.get("free_float"))
        float_date = str(float_data.get("effective_date") or "") or None

        short_float = None
        short_detail = (
            f"Massive short_interest / {float_source} free_float"
        )
        if (
            short_interest is not None
            and free_float is not None
            and free_float > 0
            and _dates_within_days(short_date, float_date, 45)
        ):
            short_float = short_interest / free_float
        elif short_date and float_date:
            short_detail += "; source periods differ by more than 45 days"
        else:
            short_detail += "; source period unavailable"

        sources = ["Massive"]
        if self.fundamentals_fetcher is not None:
            sources.append("SEC EDGAR Company Facts")
        if float_source == "Financial Modeling Prep":
            sources.append("Financial Modeling Prep")
        record_source = " + ".join(sources)
        short_source = (
            "Massive + Financial Modeling Prep"
            if float_source == "Financial Modeling Prep"
            else "Massive"
        )
        return {
            "symbol": normalized,
            "source": record_source,
            "as_of": retrieved_at,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "short_float": short_float,
            "massive_short_interest": short_interest,
            "massive_free_float": free_float,
            "massive_endpoint_errors": endpoint_errors,
            "_raw_massive": raw_payloads,
            "field_evidence": {
                "market_cap": _evidence(
                    market_cap,
                    category="fundamentals",
                    retrieved_at=retrieved_at,
                    observed_at=market_date,
                    detail=(
                        "Massive Basic ticker details market_cap"
                        if "ticker_details" not in endpoint_errors
                        else "Massive ticker details endpoint unavailable"
                    ),
                ),
                "enterprise_value": _evidence(
                    enterprise_value,
                    source="Massive + SEC EDGAR Company Facts",
                    category="fundamentals",
                    retrieved_at=retrieved_at,
                    observed_at=market_date,
                    detail=(
                        "Massive current market cap + SEC reported debt - cash; "
                        f"debt_period={debt_date or 'unavailable'}; "
                        f"cash_period={cash_date or 'unavailable'}"
                    ),
                ),
                "short_float": _evidence(
                    short_float,
                    source=short_source,
                    category="ownership",
                    retrieved_at=retrieved_at,
                    observed_at=short_date,
                    detail=short_detail,
                ),
            },
        }


def build_massive_secondary_provider(
    root: str | Path,
    settings: Mapping[str, Any],
    *,
    float_fetcher: FloatFetcher | None = None,
    fundamentals_fetcher: FundamentalsFetcher | None = None,
) -> MassiveMarketDataProvider | None:
    api_key = load_massive_api_key(root, settings)
    if not api_key:
        return None
    return MassiveMarketDataProvider(
        api_key,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
        float_fetcher=float_fetcher,
        fundamentals_fetcher=fundamentals_fetcher,
        ticker_details_cache=MassiveTickerDetailsCache(
            Path(root)
            / str(
                settings.get(
                    "massive_ticker_details_cache_path",
                    "data/provider_cache/massive_ticker_details.json",
                )
            )
        ),
        ticker_details_cache_days=float(
            settings.get("massive_ticker_details_cache_days", 7)
        ),
        prefetch_policy=ProviderPolicy(
            timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
            max_retries=int(settings.get("provider_max_retries", 2)),
            backoff_seconds=float(settings.get("provider_backoff_seconds", 0.5)),
            rate_limit_per_second=float(
                settings.get("massive_prefetch_rate_limit_per_second", 0.075)
            ),
        ),
        request_limit_per_minute=int(
            settings.get("massive_request_limit_per_minute", 5)
        ),
    )

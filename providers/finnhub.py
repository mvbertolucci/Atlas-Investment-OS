from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.contracts import ProviderClient, ProviderError, ProviderErrorKind, ProviderPolicy
from providers.evidence import DataValueStatus, FieldEvidence
from providers.finnhub_cache import FinnhubMetricCache


JsonTransport = Callable[[str, Mapping[str, str], str, float], Any]
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
MILLIONS = 1_000_000.0


def load_finnhub_api_key(
    root: str | Path,
    settings: Mapping[str, Any],
) -> str | None:
    if not bool(settings.get("finnhub_secondary_enabled", False)):
        return None
    environment_value = str(os.getenv("FINNHUB_API_KEY") or "").strip()
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
    value = str(payload.get("finnhub_api_key") or "").strip()
    return value or None


def _request_json(
    path: str,
    params: Mapping[str, str],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    query = urlencode({**params, "token": api_key})
    request = Request(
        f"{FINNHUB_BASE_URL}{path}?{query}",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Finnhub HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Finnhub unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Finnhub returned invalid JSON") from exc


def _number_millions(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result * MILLIONS if result >= 0 else None


def _ratio_from_percent(value: Any) -> float | None:
    """Finnhub reports ROE as a percentage (26.26 == 26.26%); the Atlas
    pipeline (and Yahoo's ``returnOnEquity``) express it as a fraction
    (0.2626). Convert so a reconciled value is directly comparable and scores
    on the same scale as the primary source."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result / 100.0


def _evidence(
    value: float | None,
    *,
    retrieved_at: str,
    detail: str,
) -> dict[str, Any]:
    return FieldEvidence(
        status=(
            DataValueStatus.PRESENT
            if value is not None
            else DataValueStatus.UNAVAILABLE
        ),
        source="Finnhub",
        category="fundamentals",
        retrieved_at=retrieved_at,
        observed_at=retrieved_at,
        available_at=retrieved_at,
        detail=detail,
    ).to_dict()


@dataclass(frozen=True)
class FinnhubMarketDataProvider:
    """Basic-plan market cap and enterprise value, one call per symbol.

    `/stock/metric?metric=all` returns both fields as vendor-computed
    absolute values (in millions) -- no debt/cash composition needed, unlike
    Massive or FMP. It does not return raw debt or cash, only ratios, so it
    cannot feed Atlas's own Altman Z / ROIC / Interest Coverage formulas;
    those keep using SEC EDGAR components. This provider only claims
    `market_cap` and `enterprise_value`.
    """

    provider_name = "Finnhub"
    supported_fields = frozenset({"market_cap", "enterprise_value", "roe"})

    api_key: str
    timeout_seconds: float = 30.0
    transport: JsonTransport = _request_json
    cache: FinnhubMetricCache | None = None
    cache_days: float = 2.0
    request_limit_per_minute: int = 55
    prefetch_policy: ProviderPolicy = ProviderPolicy()
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
            raise ValueError("Finnhub api_key não pode ser vazia.")
        if self.timeout_seconds <= 0:
            raise ValueError("Finnhub timeout_seconds deve ser positivo.")
        if self.request_limit_per_minute <= 0:
            raise ValueError(
                "Finnhub request_limit_per_minute deve ser positivo."
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
        return self.transport(path, params, self.api_key, self.timeout_seconds)

    def fetch_metric(self, symbol: str) -> Mapping[str, Any]:
        normalized = str(symbol).strip().upper()
        if self.cache is not None:
            cached = self.cache.get(normalized, max_age_days=self.cache_days)
            if cached is not None:
                return cached
        client = ProviderClient("Finnhub", self.prefetch_policy)
        payload = client.execute(
            "metric",
            self._get,
            "/stock/metric",
            symbol=normalized,
            metric="all",
        )
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("metric"), Mapping
        ):
            raise ProviderError(
                "Finnhub",
                "metric",
                ProviderErrorKind.INVALID_RESPONSE,
                "Finnhub metric response has no metric object",
                retryable=False,
            )
        if self.cache is not None:
            self.cache.put(normalized, payload)
        return payload

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        endpoint_errors: dict[str, dict[str, str]] = {}
        try:
            payload = self.fetch_metric(normalized)
            metric = payload.get("metric") or {}
        except (ProviderError, RuntimeError, ValueError) as exc:
            endpoint_errors["metric"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            payload = {"unavailable": True, "error_type": type(exc).__name__}
            metric = {}
        market_cap = _number_millions(metric.get("marketCapitalization"))
        enterprise_value = _number_millions(metric.get("enterpriseValue"))
        roe = _ratio_from_percent(metric.get("roeTTM"))
        return {
            "symbol": normalized,
            "source": "Finnhub",
            "as_of": retrieved_at,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "roe": roe,
            "finnhub_endpoint_errors": endpoint_errors,
            "_raw_finnhub": payload,
            "field_evidence": {
                "roe": _evidence(
                    roe,
                    retrieved_at=retrieved_at,
                    detail=(
                        "Finnhub Basic Financials roeTTM "
                        "(vendor-computed TTM, percent converted to fraction)"
                        if "metric" not in endpoint_errors
                        else "Finnhub metric endpoint unavailable"
                    ),
                ),
                "market_cap": _evidence(
                    market_cap,
                    retrieved_at=retrieved_at,
                    detail=(
                        "Finnhub Basic Financials marketCapitalization"
                        if "metric" not in endpoint_errors
                        else "Finnhub metric endpoint unavailable"
                    ),
                ),
                "enterprise_value": _evidence(
                    enterprise_value,
                    retrieved_at=retrieved_at,
                    detail=(
                        "Finnhub Basic Financials enterpriseValue "
                        "(vendor-computed, not SEC-composed)"
                        if "metric" not in endpoint_errors
                        else "Finnhub metric endpoint unavailable"
                    ),
                ),
            },
        }


def build_finnhub_secondary_provider(
    root: str | Path,
    settings: Mapping[str, Any],
) -> FinnhubMarketDataProvider | None:
    api_key = load_finnhub_api_key(root, settings)
    if not api_key:
        return None
    return FinnhubMarketDataProvider(
        api_key,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
        cache=FinnhubMetricCache(
            Path(root)
            / str(
                settings.get(
                    "finnhub_cache_path", "data/provider_cache/finnhub.json"
                )
            )
        ),
        cache_days=float(settings.get("finnhub_cache_days", 2)),
        request_limit_per_minute=int(
            settings.get("finnhub_request_limit_per_minute", 55)
        ),
        prefetch_policy=ProviderPolicy(
            timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
            max_retries=int(settings.get("provider_max_retries", 2)),
            backoff_seconds=float(settings.get("provider_backoff_seconds", 0.5)),
            rate_limit_per_second=float(
                settings.get("finnhub_rate_limit_per_second", 0.9)
            ),
        ),
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.evidence import DataValueStatus, FieldEvidence


JsonTransport = Callable[[str, Mapping[str, str], str, float], Any]
FloatFetcher = Callable[[str], Mapping[str, Any]]
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
    use_ratios: bool = True

    def __post_init__(self) -> None:
        if not str(self.api_key).strip():
            raise ValueError("Massive api_key não pode ser vazia.")
        if self.timeout_seconds <= 0:
            raise ValueError("Massive timeout_seconds deve ser positivo.")

    def _get(self, path: str, **params: str) -> Any:
        return self.transport(
            path,
            params,
            self.api_key,
            self.timeout_seconds,
        )

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        endpoint_errors: dict[str, dict[str, str]] = {}
        raw_payloads: dict[str, Any] = {}

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
            except (RuntimeError, ValueError) as exc:
                endpoint_errors[label] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                raw_payloads[label] = {
                    "unavailable": True,
                    "error_type": type(exc).__name__,
                }
                return {}

        ratios = (
            latest(
                "ratios",
                "/stocks/financials/v1/ratios",
                "date",
                ticker=normalized,
                limit="10",
                sort="date.desc",
            )
            if self.use_ratios
            else {}
        )
        short = latest(
            "short_interest",
            "/stocks/v1/short-interest",
            "settlement_date",
            ticker=normalized,
            limit="10",
            sort="settlement_date.desc",
        )
        float_source = "Massive"
        if self.float_fetcher is None:
            float_data = latest(
                "float",
                "/stocks/vX/float",
                "effective_date",
                ticker=normalized,
                limit="10",
            )
        else:
            float_source = "Financial Modeling Prep"
            try:
                external_float = self.float_fetcher(normalized)
                raw_payloads["float"] = external_float.get(
                    "_raw_fmp_float", external_float
                )
                float_data = {
                    "free_float": external_float.get("free_float"),
                    "effective_date": external_float.get("observed_at"),
                }
            except (RuntimeError, ValueError) as exc:
                endpoint_errors["float"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                raw_payloads["float"] = {
                    "unavailable": True,
                    "error_type": type(exc).__name__,
                }
                float_data = {}
        market_cap = _number(ratios.get("market_cap"))
        enterprise_value = _number(ratios.get("enterprise_value"))
        short_interest = _number(short.get("short_interest"))
        free_float = _number(float_data.get("free_float"))
        ratio_date = str(ratios.get("date") or "") or None
        short_date = str(short.get("settlement_date") or "") or None
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

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record_source = (
            "Massive + Financial Modeling Prep"
            if self.float_fetcher is not None
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
                    observed_at=ratio_date,
                    detail=(
                        "Massive daily ratios market_cap"
                        if "ratios" not in endpoint_errors
                        else "Massive ratios endpoint unavailable"
                    ),
                ),
                "enterprise_value": _evidence(
                    enterprise_value,
                    category="fundamentals",
                    retrieved_at=retrieved_at,
                    observed_at=ratio_date,
                    detail=(
                        "Massive daily ratios enterprise_value"
                        if "ratios" not in endpoint_errors
                        else "Massive ratios endpoint unavailable"
                    ),
                ),
                "short_float": _evidence(
                    short_float,
                    source=record_source,
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
) -> MassiveMarketDataProvider | None:
    api_key = load_massive_api_key(root, settings)
    if not api_key:
        return None
    return MassiveMarketDataProvider(
        api_key,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
        float_fetcher=float_fetcher,
        use_ratios=float_fetcher is None,
    )

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
        source="Massive",
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
        ratios_payload = self._get(
            "/stocks/financials/v1/ratios",
            ticker=normalized,
            limit="10",
            sort="date.desc",
        )
        short_payload = self._get(
            "/stocks/v1/short-interest",
            ticker=normalized,
            limit="10",
            sort="settlement_date.desc",
        )
        float_payload = self._get(
            "/stocks/vX/float",
            ticker=normalized,
            limit="10",
        )

        ratios = _latest_result(ratios_payload, "date")
        short = _latest_result(short_payload, "settlement_date")
        float_data = _latest_result(float_payload, "effective_date")
        market_cap = _number(ratios.get("market_cap"))
        enterprise_value = _number(ratios.get("enterprise_value"))
        short_interest = _number(short.get("short_interest"))
        free_float = _number(float_data.get("free_float"))
        ratio_date = str(ratios.get("date") or "") or None
        short_date = str(short.get("settlement_date") or "") or None
        float_date = str(float_data.get("effective_date") or "") or None

        short_float = None
        short_detail = "short_interest / free_float"
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
        return {
            "symbol": normalized,
            "source": "Massive",
            "as_of": retrieved_at,
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "short_float": short_float,
            "massive_short_interest": short_interest,
            "massive_free_float": free_float,
            "_raw_massive": {
                "ratios": ratios_payload,
                "short_interest": short_payload,
                "float": float_payload,
            },
            "field_evidence": {
                "market_cap": _evidence(
                    market_cap,
                    category="fundamentals",
                    retrieved_at=retrieved_at,
                    observed_at=ratio_date,
                    detail="Massive daily ratios market_cap",
                ),
                "enterprise_value": _evidence(
                    enterprise_value,
                    category="fundamentals",
                    retrieved_at=retrieved_at,
                    observed_at=ratio_date,
                    detail="Massive daily ratios enterprise_value",
                ),
                "short_float": _evidence(
                    short_float,
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
) -> MassiveMarketDataProvider | None:
    api_key = load_massive_api_key(root, settings)
    if not api_key:
        return None
    return MassiveMarketDataProvider(
        api_key,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
    )

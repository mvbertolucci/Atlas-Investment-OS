from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from providers.evidence import DataValueStatus, FieldEvidence


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

    def __post_init__(self) -> None:
        if not str(self.api_key).strip():
            raise ValueError("FMP api_key não pode ser vazia.")
        if self.timeout_seconds <= 0:
            raise ValueError("FMP timeout_seconds deve ser positivo.")

    def _get(self, path: str, **params: str) -> Any:
        return self.transport(
            path,
            params,
            self.api_key,
            self.timeout_seconds,
        )

    def fetch_float(self, symbol: str) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        payload = self._get("/stable/shares-float", symbol=normalized)
        row = _latest_row(payload)
        return {
            "symbol": normalized,
            "source": "Financial Modeling Prep",
            "free_float": _number(row.get("floatShares")),
            "observed_at": str(row.get("date") or "") or None,
            "_raw_fmp_float": payload,
        }

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        normalized = str(symbol).strip().upper()
        market_payload = self._get(
            "/stable/market-capitalization", symbol=normalized
        )
        enterprise_payload = self._get(
            "/stable/enterprise-values", symbol=normalized
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
    )

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from backtesting.point_in_time import HistoricalObservation
from backtesting.sec_edgar import (
    available_at_from_filed,
    extract_observations,
    fetch_company_facts,
    fetch_ticker_cik_map,
)
from providers.evidence import DataValueStatus, FieldEvidence


def load_sec_user_agent(
    root: str | Path,
    settings: Mapping[str, Any],
) -> str | None:
    if not bool(settings.get("sec_secondary_enabled", False)):
        return None
    environment_value = str(os.getenv("SEC_EDGAR_USER_AGENT") or "").strip()
    if environment_value:
        return environment_value
    configured = Path(
        str(settings.get("provider_secrets_path", "config/provider_secrets.json"))
    )
    path = configured if configured.is_absolute() else Path(root) / configured
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return None
    value = str(payload.get("sec_user_agent") or "").strip()
    return value or None


def _latest_by_field(
    observations: Iterable[HistoricalObservation],
) -> dict[str, dict[str, HistoricalObservation]]:
    result: dict[str, dict[str, HistoricalObservation]] = {}
    for item in observations:
        observed_on = item.observed_on.isoformat()
        current = result.setdefault(item.field_name, {}).get(observed_on)
        if current is None or (item.available_at, item.revision_id) > (
            current.available_at,
            current.revision_id,
        ):
            result[item.field_name][observed_on] = item
    return result


_PUBLIC_FLOAT_FORMS = frozenset(
    {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
)


def extract_entity_public_float_observation(
    symbol: str,
    company_facts: Mapping[str, Any],
) -> HistoricalObservation | None:
    concept = (
        company_facts.get("facts", {})
        .get("dei", {})
        .get("EntityPublicFloat", {})
    )
    entries = concept.get("units", {}).get("USD", [])
    candidates: list[HistoricalObservation] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, Mapping):
            continue
        required = ("end", "val", "filed", "accn", "form")
        if any(key not in entry for key in required):
            continue
        form = str(entry["form"]).strip().upper()
        if form not in _PUBLIC_FLOAT_FORMS:
            continue
        try:
            value = float(entry["val"])
            available_at = available_at_from_filed(str(entry["filed"]))
            observation = HistoricalObservation(
                symbol=symbol,
                field_name="entity_public_float_value",
                value=value,
                observed_on=str(entry["end"]),
                available_at=available_at,
                source=(
                    "SEC EDGAR Company Facts "
                    f"({form}, dei:EntityPublicFloat)"
                ),
                revision_id=str(entry["accn"]),
            )
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0:
            candidates.append(observation)
    return (
        max(
            candidates,
            key=lambda item: (
                item.observed_on,
                item.available_at,
                item.revision_id,
            ),
        )
        if candidates
        else None
    )


def _common_period(
    indexed: Mapping[str, Mapping[str, HistoricalObservation]],
    fields: Iterable[str],
    *,
    source_contains: str | None = None,
) -> str | None:
    names = tuple(fields)
    if not names or any(not indexed.get(name) for name in names):
        return None
    periods = {
        period
        for period, item in indexed[names[0]].items()
        if source_contains is None or source_contains in item.source
    }
    for name in names[1:]:
        periods &= {
            period
            for period, item in indexed[name].items()
            if source_contains is None or source_contains in item.source
        }
    return max(periods) if periods else None


def _evidence(
    observations: Iterable[HistoricalObservation],
    *,
    status: DataValueStatus = DataValueStatus.PRESENT,
    detail: str | None = None,
    category: str = "fundamentals",
) -> dict[str, Any]:
    items = tuple(observations)
    if not items:
        return FieldEvidence(
            status=DataValueStatus.UNAVAILABLE,
            source="SEC EDGAR Company Facts",
            category=category,
            retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            detail=detail,
        ).to_dict()
    return FieldEvidence(
        status=status,
        source=" | ".join(sorted({item.source for item in items})),
        category=category,
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        observed_at=max(item.observed_on for item in items).isoformat(),
        available_at=max(item.available_at for item in items).isoformat(),
        detail=detail,
    ).to_dict()


def record_from_company_facts(
    symbol: str,
    company_facts: Mapping[str, Any],
    *,
    cik: str,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    observations = extract_observations(symbol, dict(company_facts))
    indexed = _latest_by_field(observations)
    values: dict[str, Any] = {
        "symbol": symbol.upper(),
        "source": "SEC EDGAR Company Facts",
        "as_of": retrieved,
        "sec_cik": cik,
        "_raw_company_facts": dict(company_facts),
    }
    evidence: dict[str, dict[str, Any]] = {}

    def direct(target: str, source_field: str) -> None:
        period = max(indexed.get(source_field, {}), default=None)
        if period is None:
            values[target] = None
            evidence[target] = _evidence((), detail=f"{source_field} unavailable")
            return
        item = indexed[source_field][period]
        values[target] = float(item.value)
        evidence[target] = _evidence((item,))

    direct("total_cash", "cash_and_equivalents")
    direct("operating_cashflow", "operating_cash_flow")
    direct("shares_outstanding", "shares_outstanding")

    public_float = extract_entity_public_float_observation(symbol, company_facts)
    if public_float is None:
        values["entity_public_float_value"] = None
        evidence["entity_public_float_value"] = _evidence(
            (),
            detail=(
                "dei:EntityPublicFloat unavailable; SEC public float is a "
                "monetary value, not a share count"
            ),
            category="ownership",
        )
    else:
        values["entity_public_float_value"] = float(public_float.value)
        evidence["entity_public_float_value"] = _evidence(
            (public_float,),
            detail=(
                "USD aggregate market value held by non-affiliates; not a "
                "free-float share count"
            ),
            category="ownership",
        )

    debt_fields = ("long_term_debt", "long_term_debt_current", "short_term_debt")
    # Anchor the debt total on the latest fiscal period of the main long-term
    # debt line, then add only the current/short components reported for that
    # SAME period. Summing "the latest period any component appears" let a
    # stray current-portion filed after a company stopped tagging its
    # long-term debt stand in for the whole balance: COP stopped tagging
    # LongTermDebtNoncurrent after 2021-Q3 while DebtCurrent continued into
    # 2026, so the old code returned the ~$1.07B current piece alone instead
    # of the real ~$23B. Anchoring keeps components period-consistent; when the
    # anchor is old (COP), the resulting observed_at makes the value
    # legitimately STALE downstream rather than silently wrong. total_debt is
    # no longer a critical cross-vendor field (ADR-042), so this only sharpens
    # the SEC secondary's own value.
    if indexed.get("long_term_debt"):
        period: str | None = sorted(indexed["long_term_debt"])[-1]
    elif any(indexed.get(name) for name in debt_fields):
        # No long-term line at all -> best effort on the latest period any
        # remaining component appears (filers that only carry short-term debt).
        period = sorted(
            {p for name in debt_fields for p in indexed.get(name, {})}
        )[-1]
    else:
        period = None
    if period is not None:
        debt_items = [
            indexed[name][period]
            for name in debt_fields
            if period in indexed.get(name, {})
        ]
        values["total_debt"] = sum(float(item.value) for item in debt_items)
        evidence["total_debt"] = _evidence(
            debt_items,
            detail="sum of debt components at the latest long-term-debt period",
        )
    else:
        values["total_debt"] = None
        evidence["total_debt"] = _evidence((), detail="debt components unavailable")

    ratio_period = _common_period(indexed, ("current_assets", "current_liabilities"))
    if ratio_period is not None:
        assets = indexed["current_assets"][ratio_period]
        liabilities = indexed["current_liabilities"][ratio_period]
        denominator = float(liabilities.value)
        values["current_ratio"] = (
            float(assets.value) / denominator if denominator else None
        )
        evidence["current_ratio"] = _evidence(
            (assets, liabilities),
            status=(
                DataValueStatus.PRESENT if denominator else DataValueStatus.INVALID
            ),
            detail="current_assets / current_liabilities",
        )
    else:
        values["current_ratio"] = None
        evidence["current_ratio"] = _evidence((), detail="no common fiscal period")

    fcf_period = _common_period(
        indexed,
        ("operating_cash_flow", "capital_expenditures"),
        source_contains="(10-K",
    )
    if fcf_period is not None:
        operating = indexed["operating_cash_flow"][fcf_period]
        capex = indexed["capital_expenditures"][fcf_period]
        values["free_cashflow"] = float(operating.value) - abs(float(capex.value))
        evidence["free_cashflow"] = _evidence(
            (operating, capex),
            detail="annual operating_cash_flow - abs(capital_expenditures)",
        )
    else:
        values["free_cashflow"] = None
        evidence["free_cashflow"] = _evidence((), detail="no common fiscal period")

    ebitda_period = _common_period(
        indexed,
        ("operating_income", "depreciation_and_amortization"),
        source_contains="(10-K",
    )
    if ebitda_period is not None:
        operating_income = indexed["operating_income"][ebitda_period]
        depreciation = indexed["depreciation_and_amortization"][ebitda_period]
        values["ebitda"] = float(operating_income.value) + abs(
            float(depreciation.value)
        )
        evidence["ebitda"] = _evidence(
            (operating_income, depreciation),
            detail="annual operating_income + abs(depreciation_and_amortization)",
        )
    else:
        values["ebitda"] = None
        evidence["ebitda"] = _evidence((), detail="no common fiscal period")

    for field_name in ("market_cap", "enterprise_value", "short_float"):
        values[field_name] = None
        evidence[field_name] = _evidence(
            (), detail="not reported in SEC Company Facts"
        )
    values["field_evidence"] = evidence
    return values


@dataclass
class SecCompanyFactsProvider:
    provider_name = "SEC EDGAR Company Facts"
    supported_fields = frozenset(
        {
            "total_debt",
            "total_cash",
            "ebitda",
            "free_cashflow",
            "current_ratio",
            "entity_public_float_value",
        }
    )

    user_agent: str
    ticker_map_fetcher: Callable[..., dict[str, str]] = fetch_ticker_cik_map
    facts_fetcher: Callable[..., dict[str, Any]] = fetch_company_facts
    _cik_by_ticker: dict[str, str] | None = field(default=None, init=False)
    _records_by_ticker: dict[str, dict[str, Any]] = field(
        default_factory=dict, init=False
    )

    def __post_init__(self) -> None:
        identity = str(self.user_agent).strip()
        if not identity or "@" not in identity:
            raise ValueError("SEC user_agent exige nome e e-mail de contato.")
        self.user_agent = identity

    def __call__(
        self,
        symbol: str,
        _name_hint: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if self._cik_by_ticker is None:
            self._cik_by_ticker = self.ticker_map_fetcher(
                user_agent=self.user_agent
            )
        normalized = str(symbol).strip().upper()
        if normalized in self._records_by_ticker:
            return deepcopy(self._records_by_ticker[normalized])
        cik = self._cik_by_ticker.get(normalized)
        if cik is None:
            raise RuntimeError(f"404 CIK not found for {normalized}")
        facts = self.facts_fetcher(cik, user_agent=self.user_agent)
        record = record_from_company_facts(normalized, facts, cik=cik)
        self._records_by_ticker[normalized] = record
        return deepcopy(record)


def build_sec_secondary_provider(
    root: str | Path,
    settings: Mapping[str, Any],
) -> SecCompanyFactsProvider | None:
    user_agent = load_sec_user_agent(root, settings)
    return SecCompanyFactsProvider(user_agent) if user_agent else None

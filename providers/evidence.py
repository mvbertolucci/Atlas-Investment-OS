from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


class DataValueStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    STALE = "stale"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class FieldEvidence:
    status: DataValueStatus
    source: str
    category: str
    retrieved_at: str
    observed_at: str | None = None
    available_at: str | None = None
    confirmation_status: str = "not_requested"
    confirmed_by: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "source": self.source,
            "category": self.category,
            "retrieved_at": self.retrieved_at,
            "observed_at": self.observed_at,
            "available_at": self.available_at,
            "confirmation_status": self.confirmation_status,
            "confirmed_by": self.confirmed_by,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FieldEvidence":
        return cls(
            status=DataValueStatus(str(data.get("status", "missing"))),
            source=str(data.get("source") or "unknown"),
            category=str(data.get("category") or "other"),
            retrieved_at=str(data.get("retrieved_at") or ""),
            observed_at=data.get("observed_at"),
            available_at=data.get("available_at"),
            confirmation_status=str(
                data.get("confirmation_status") or "not_requested"
            ),
            confirmed_by=data.get("confirmed_by"),
            detail=data.get("detail"),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return not (isinstance(value, str) and not value.strip())


def _category(field_name: str) -> str:
    if field_name in {
        "price", "previous_close", "change_pct", "volume", "average_volume",
        "year_high", "year_low", "beta",
    }:
        return "market"
    if field_name in {
        "symbol", "name", "quote_type", "exchange", "country", "currency",
        "sector", "industry",
    }:
        return "identity"
    if field_name in {
        "target_price", "target_high_price", "target_low_price",
        "analyst_count", "rating", "earnings_date",
    }:
        return "analyst"
    if field_name in {"short_float", "insider_own", "inst_own"}:
        return "ownership"
    return "fundamentals"


def ensure_field_evidence(
    record: dict[str, Any],
    *,
    source: str | None = None,
    retrieved_at: str | None = None,
    raw_presence: Mapping[str, bool] | None = None,
    raw_values: Mapping[str, Any] | None = None,
    observed_at_by_category: Mapping[str, str] | None = None,
    not_applicable_fields: Iterable[str] = (),
) -> dict[str, Any]:
    evidence = dict(record.get("field_evidence") or {})
    provider = source or str(record.get("source") or "unknown")
    retrieved = retrieved_at or str(record.get("as_of") or utc_now())
    not_applicable = set(not_applicable_fields)
    excluded = {"field_evidence", "history", "source", "as_of"}
    for field_name, value in record.items():
        if field_name in excluded or field_name.startswith("_"):
            continue
        if field_name in evidence:
            continue
        category = _category(field_name)
        present_in_payload = (
            raw_presence.get(field_name, field_name in record)
            if raw_presence is not None
            else field_name in record
        )
        raw_value = (
            raw_values.get(field_name, value)
            if raw_values is not None
            else value
        )
        if field_name in not_applicable:
            status = DataValueStatus.NOT_APPLICABLE
        elif not present_in_payload:
            status = DataValueStatus.MISSING
        elif raw_value is None or raw_value == "":
            status = DataValueStatus.UNAVAILABLE
        elif not _valid(value):
            status = DataValueStatus.INVALID
        else:
            status = DataValueStatus.PRESENT
        observed_at = (observed_at_by_category or {}).get(category)
        evidence[field_name] = FieldEvidence(
            status=status,
            source=provider,
            category=category,
            retrieved_at=retrieved,
            observed_at=observed_at,
            available_at=retrieved,
        ).to_dict()
    record["field_evidence"] = evidence
    return record


def field_status(record: Mapping[str, Any], field_name: str) -> DataValueStatus:
    data = (record.get("field_evidence") or {}).get(field_name)
    if isinstance(data, Mapping):
        return FieldEvidence.from_dict(data).status
    return DataValueStatus.PRESENT if _valid(record.get(field_name)) else DataValueStatus.MISSING


def apply_sector_applicability(
    record: dict[str, Any],
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    ensure_field_evidence(record)
    sector = str(record.get("sector") or "").strip().casefold()
    configured = (policy or {}).get("not_applicable_by_sector") or {}
    fields: set[str] = set()
    for sector_name, sector_fields in configured.items():
        if str(sector_name).strip().casefold() == sector:
            fields.update(str(item) for item in (sector_fields or ()))
    evidence = dict(record.get("field_evidence") or {})
    for field_name in fields:
        current = FieldEvidence.from_dict(
            evidence.get(field_name, {
                "status": DataValueStatus.MISSING.value,
                "source": record.get("source", "unknown"),
                "category": _category(field_name),
                "retrieved_at": record.get("as_of", ""),
            })
        )
        evidence[field_name] = replace(
            current,
            status=DataValueStatus.NOT_APPLICABLE,
            detail=f"not applicable to sector {record.get('sector', '')}",
        ).to_dict()
        record[field_name] = None
    record["field_evidence"] = evidence
    freshness = (policy or {}).get("freshness") or {}
    stale_after_days = float(freshness.get("acceptable_days", 35.0))
    evaluated_at = datetime.now(timezone.utc)
    for field_name, payload in list(evidence.items()):
        current = FieldEvidence.from_dict(payload)
        if current.status != DataValueStatus.PRESENT:
            continue
        raw_timestamp = current.observed_at or current.available_at or current.retrieved_at
        try:
            timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        age_days = (evaluated_at - timestamp.astimezone(timezone.utc)).total_seconds() / 86400
        if age_days > stale_after_days:
            evidence[field_name] = replace(
                current,
                status=DataValueStatus.STALE,
                detail=f"older than {stale_after_days:g} days",
            ).to_dict()
    record["field_evidence"] = evidence
    return record


def _values_agree(primary: Any, secondary: Any, tolerance: float) -> bool:
    try:
        left, right = float(primary), float(secondary)
        scale = max(abs(left), abs(right), 1.0)
        return abs(left - right) / scale <= tolerance
    except (TypeError, ValueError):
        return str(primary).strip().casefold() == str(secondary).strip().casefold()


def reconcile_critical_fields(
    primary: dict[str, Any],
    secondary: Mapping[str, Any] | None,
    critical_fields: Iterable[str],
    *,
    tolerance: float = 0.05,
) -> dict[str, Any]:
    result = dict(primary)
    result["field_evidence"] = dict(primary.get("field_evidence") or {})
    secondary_source = str((secondary or {}).get("source") or "secondary")
    unusable = {
        DataValueStatus.MISSING,
        DataValueStatus.UNAVAILABLE,
        DataValueStatus.INVALID,
        DataValueStatus.STALE,
    }
    for field_name in critical_fields:
        primary_status = field_status(result, field_name)
        if secondary is None:
            current = FieldEvidence.from_dict(
                result["field_evidence"].get(field_name, {
                    "status": primary_status.value,
                    "source": result.get("source", "unknown"),
                    "category": _category(field_name),
                    "retrieved_at": result.get("as_of", ""),
                })
            )
            result["field_evidence"][field_name] = replace(
                current, confirmation_status="secondary_unavailable"
            ).to_dict()
            continue
        secondary_status = field_status(secondary, field_name)
        secondary_evidence = FieldEvidence.from_dict(
            (secondary.get("field_evidence") or {}).get(field_name, {
                "status": secondary_status.value,
                "source": secondary_source,
                "category": _category(field_name),
                "retrieved_at": secondary.get("as_of", ""),
            })
        )
        if primary_status in unusable and secondary_status == DataValueStatus.PRESENT:
            result[field_name] = secondary.get(field_name)
            result["field_evidence"][field_name] = replace(
                secondary_evidence,
                confirmation_status="fallback",
                detail=f"primary_status={primary_status.value}",
            ).to_dict()
            continue
        current = FieldEvidence.from_dict(
            result["field_evidence"].get(field_name, {
                "status": primary_status.value,
                "source": result.get("source", "unknown"),
                "category": _category(field_name),
                "retrieved_at": result.get("as_of", ""),
            })
        )
        if primary_status == secondary_status == DataValueStatus.PRESENT:
            if _values_agree(result.get(field_name), secondary.get(field_name), tolerance):
                updated = replace(
                    current,
                    confirmation_status="confirmed",
                    confirmed_by=secondary_source,
                )
            else:
                result[field_name] = None
                updated = replace(
                    current,
                    status=DataValueStatus.INVALID,
                    confirmation_status="conflict",
                    confirmed_by=secondary_source,
                    detail="critical sources disagree",
                )
            result["field_evidence"][field_name] = updated.to_dict()
    return result

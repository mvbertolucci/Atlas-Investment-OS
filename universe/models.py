from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "n/a"}:
        return ""
    return text


def _positive_number(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser numérico.") from exc
    if result < 0:
        raise ValueError(f"{field_name} não pode ser negativo.")
    return result


def _text_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)


@dataclass(frozen=True)
class UniversePolicy:
    name: str
    benchmark: str
    rebalance_frequency: str
    allowed_quote_types: tuple[str, ...] = ("EQUITY",)
    allowed_currencies: tuple[str, ...] = ("USD",)
    allowed_countries: tuple[str, ...] = ("United States",)
    min_market_cap: float = 1_000_000_000.0
    min_price: float = 5.0
    min_volume: float = 100_000.0
    required_fields: tuple[str, ...] = (
        "symbol",
        "quote_type",
        "currency",
        "country",
        "sector",
        "price",
        "market_cap",
        "volume",
    )

    def __post_init__(self) -> None:
        for field_name in (
            "name",
            "benchmark",
            "rebalance_frequency",
        ):
            value = _clean_text(getattr(self, field_name))
            if not value:
                raise ValueError(f"UniversePolicy exige {field_name}.")
            object.__setattr__(self, field_name, value)

        for field_name in (
            "allowed_quote_types",
            "allowed_currencies",
            "allowed_countries",
            "required_fields",
        ):
            values = _text_tuple(getattr(self, field_name))
            if not values:
                raise ValueError(f"UniversePolicy exige {field_name}.")
            object.__setattr__(self, field_name, values)

        for field_name in (
            "min_market_cap",
            "min_price",
            "min_volume",
        ):
            object.__setattr__(
                self,
                field_name,
                _positive_number(getattr(self, field_name), field_name),
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UniversePolicy":
        if not isinstance(data, dict):
            raise TypeError("A configuração do universo deve ser um objeto.")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "benchmark": self.benchmark,
            "rebalance_frequency": self.rebalance_frequency,
            "allowed_quote_types": list(self.allowed_quote_types),
            "allowed_currencies": list(self.allowed_currencies),
            "allowed_countries": list(self.allowed_countries),
            "min_market_cap": self.min_market_cap,
            "min_price": self.min_price,
            "min_volume": self.min_volume,
            "required_fields": list(self.required_fields),
        }


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    data_coverage_pct: float
    quote_type: str = ""
    currency: str = ""
    country: str = ""
    sector: str = ""
    industry: str = ""
    price: float | None = None
    market_cap: float | None = None
    volume: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "eligible": self.eligible,
            "exclusion_reasons": list(self.exclusion_reasons),
            "data_coverage_pct": self.data_coverage_pct,
            "quote_type": self.quote_type,
            "currency": self.currency,
            "country": self.country,
            "sector": self.sector,
            "industry": self.industry,
            "price": self.price,
            "market_cap": self.market_cap,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class UniverseReport:
    policy: UniversePolicy
    members: tuple[UniverseMember, ...]
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def total_count(self) -> int:
        return len(self.members)

    @property
    def eligible_count(self) -> int:
        return sum(member.eligible for member in self.members)

    @property
    def excluded_count(self) -> int:
        return self.total_count - self.eligible_count

    @property
    def average_data_coverage_pct(self) -> float:
        if not self.members:
            return 0.0
        return round(
            sum(member.data_coverage_pct for member in self.members)
            / self.total_count,
            1,
        )

    @property
    def exclusions_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for member in self.members:
            for reason in member.exclusion_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def eligible_by_sector(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for member in self.members:
            if member.eligible:
                sector = member.sector or "UNKNOWN"
                counts[sector] = counts.get(sector, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "policy": self.policy.to_dict(),
            "summary": {
                "total_count": self.total_count,
                "eligible_count": self.eligible_count,
                "excluded_count": self.excluded_count,
                "average_data_coverage_pct": self.average_data_coverage_pct,
                "exclusions_by_reason": self.exclusions_by_reason,
                "eligible_by_sector": self.eligible_by_sector,
            },
            "members": [member.to_dict() for member in self.members],
        }

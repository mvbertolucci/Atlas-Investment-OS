from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RankingPolicy:
    name: str
    primary_score: str = "Investment Score"
    tie_breakers: tuple[str, ...] = (
        "Opportunity Score",
        "Conviction Score",
    )
    min_confidence_score: float = 70.0
    require_no_deal_breakers: bool = True

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("RankingPolicy exige name.")
        if not str(self.primary_score).strip():
            raise ValueError("RankingPolicy exige primary_score.")
        if not self.tie_breakers:
            raise ValueError("RankingPolicy exige tie_breakers.")
        confidence = float(self.min_confidence_score)
        if not 0 <= confidence <= 100:
            raise ValueError("min_confidence_score deve estar entre 0 e 100.")
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "primary_score", str(self.primary_score).strip())
        object.__setattr__(
            self,
            "tie_breakers",
            tuple(str(value).strip() for value in self.tie_breakers),
        )
        object.__setattr__(self, "min_confidence_score", confidence)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RankingPolicy":
        if not isinstance(data, dict):
            raise TypeError("A configuração de ranking deve ser um objeto.")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "primary_score": self.primary_score,
            "tie_breakers": list(self.tie_breakers),
            "min_confidence_score": self.min_confidence_score,
            "require_no_deal_breakers": self.require_no_deal_breakers,
        }


@dataclass(frozen=True)
class RankedCompany:
    symbol: str
    sector: str
    universe_eligible: bool
    safeguard_passed: bool
    safeguard_reasons: tuple[str, ...]
    market_rank: int | None
    sector_rank: int | None
    candidate_rank: int | None
    investment_score: float | None
    opportunity_score: float | None
    conviction_score: float | None
    confidence_score: float | None
    deal_breakers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "universe_eligible": self.universe_eligible,
            "safeguard_passed": self.safeguard_passed,
            "safeguard_reasons": list(self.safeguard_reasons),
            "market_rank": self.market_rank,
            "sector_rank": self.sector_rank,
            "candidate_rank": self.candidate_rank,
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "confidence_score": self.confidence_score,
            "deal_breakers": list(self.deal_breakers),
        }


@dataclass(frozen=True)
class RankingReport:
    policy: RankingPolicy
    companies: tuple[RankedCompany, ...]
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def total_count(self) -> int:
        return len(self.companies)

    @property
    def universe_eligible_count(self) -> int:
        return sum(company.universe_eligible for company in self.companies)

    @property
    def candidate_count(self) -> int:
        return sum(company.safeguard_passed for company in self.companies)

    @property
    def blocked_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for company in self.companies:
            for reason in company.safeguard_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "policy": self.policy.to_dict(),
            "summary": {
                "total_count": self.total_count,
                "universe_eligible_count": self.universe_eligible_count,
                "candidate_count": self.candidate_count,
                "blocked_by_reason": self.blocked_by_reason,
            },
            "companies": [company.to_dict() for company in self.companies],
        }

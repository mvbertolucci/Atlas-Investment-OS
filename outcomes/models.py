from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reports.report_models import CompanyReport


VALID_DECISIONS = frozenset(
    {
        "STRONG_BUY",
        "BUY",
        "ACCUMULATE",
        "HOLD",
        "WATCH",
        "AVOID",
    }
)


def _normalize_score(value: Any) -> float | None:
    if value is None:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if numeric != numeric:
        return None

    return round(max(0.0, min(100.0, numeric)), 1)


def _normalize_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "decision_date deve ser datetime ou ISO-8601 válido."
        ) from exc


@dataclass(frozen=True)
class OutcomeSnapshot:
    """Fotografia imutável de uma decisão para avaliação futura."""

    decision_date: datetime | str
    symbol: str
    decision_price: float
    decision: str

    company_name: str = ""
    decision_rating: str = ""
    investment_score: float | None = None
    opportunity_score: float | None = None
    conviction_score: float | None = None
    decision_confidence: float | None = None
    risk_penalty: float | None = None
    has_deal_breaker: bool = False

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        decision = str(self.decision).strip().upper()

        if not symbol:
            raise ValueError(
                "OutcomeSnapshot exige um símbolo válido."
            )

        if decision not in VALID_DECISIONS:
            raise ValueError(
                "decision deve ser uma decisão válida do Atlas."
            )

        try:
            decision_price = float(self.decision_price)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "decision_price deve ser numérico e positivo."
            ) from exc

        if (
            decision_price != decision_price
            or decision_price <= 0
        ):
            raise ValueError(
                "decision_price deve ser numérico e positivo."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(
            self,
            "decision_date",
            _normalize_datetime(self.decision_date),
        )
        object.__setattr__(
            self,
            "decision_price",
            round(decision_price, 6),
        )
        object.__setattr__(
            self,
            "company_name",
            str(self.company_name).strip(),
        )
        object.__setattr__(
            self,
            "decision_rating",
            str(self.decision_rating).strip(),
        )

        for field_name in (
            "investment_score",
            "opportunity_score",
            "conviction_score",
            "decision_confidence",
            "risk_penalty",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalize_score(getattr(self, field_name)),
            )

        object.__setattr__(
            self,
            "has_deal_breaker",
            bool(self.has_deal_breaker),
        )

    @classmethod
    def from_company_report(
        cls,
        report: CompanyReport,
        *,
        decision_price: float,
        decision_date: datetime | str | None = None,
    ) -> "OutcomeSnapshot":
        if not isinstance(report, CompanyReport):
            raise TypeError(
                "report deve ser CompanyReport."
            )

        return cls(
            decision_date=decision_date or report.generated_at,
            symbol=report.symbol,
            company_name=report.company_name,
            decision_price=decision_price,
            decision=report.decision,
            decision_rating=report.decision_rating,
            investment_score=report.investment_score,
            opportunity_score=report.opportunity_score,
            conviction_score=report.conviction_score,
            decision_confidence=report.decision_confidence,
            risk_penalty=report.risk_penalty,
            has_deal_breaker=bool(report.deal_breakers),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_date": self.decision_date.isoformat(
                timespec="seconds"
            ),
            "symbol": self.symbol,
            "company_name": self.company_name,
            "decision_price": self.decision_price,
            "decision": self.decision,
            "decision_rating": self.decision_rating,
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "decision_confidence": self.decision_confidence,
            "risk_penalty": self.risk_penalty,
            "has_deal_breaker": self.has_deal_breaker,
        }

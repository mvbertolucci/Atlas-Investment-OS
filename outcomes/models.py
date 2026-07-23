from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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


def _normalize_items(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    source = values.split(";") if isinstance(values, str) else values
    items: list[str] = []
    for value in source:
        text = str(value).strip()
        if text and text not in items:
            items.append(text)
    return tuple(items)


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
    business_score: float | None = None
    valuation_score: float | None = None
    financial_score: float | None = None
    timing_score: float | None = None
    risk_penalty: float | None = None
    has_deal_breaker: bool = False
    deal_breakers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        symbol = str(self.symbol).strip().upper()
        decision = str(self.decision).strip().upper()

        if not symbol:
            raise ValueError(
                "OutcomeSnapshot exige um símbolo válido."
            )

        company_name = str(self.company_name).strip()
        if not company_name:
            raise ValueError(
                "OutcomeSnapshot exige o nome da empresa."
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
            company_name,
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
            "business_score",
            "valuation_score",
            "financial_score",
            "timing_score",
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
        object.__setattr__(
            self,
            "deal_breakers",
            _normalize_items(self.deal_breakers),
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
            business_score=report.business_score,
            valuation_score=report.valuation_score,
            financial_score=report.financial_score,
            timing_score=report.timing_score,
            risk_penalty=report.risk_penalty,
            has_deal_breaker=bool(report.deal_breakers),
            deal_breakers=report.deal_breakers,
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
            "business_score": self.business_score,
            "valuation_score": self.valuation_score,
            "financial_score": self.financial_score,
            "timing_score": self.timing_score,
            "risk_penalty": self.risk_penalty,
            "has_deal_breaker": self.has_deal_breaker,
            "deal_breakers": list(self.deal_breakers),
        }


@dataclass(frozen=True)
class OutcomeResult:
    """Retorno observado para uma decisão e horizonte específicos."""

    decision_date: datetime | str
    symbol: str
    company_name: str
    horizon_days: int
    evaluation_date: datetime | str
    decision_price: float
    outcome_price: float

    def __post_init__(self) -> None:
        decision_date = _normalize_datetime(self.decision_date)
        evaluation_date = _normalize_datetime(self.evaluation_date)
        symbol = str(self.symbol).strip().upper()

        if not symbol:
            raise ValueError(
                "OutcomeResult exige um símbolo válido."
            )

        company_name = str(self.company_name).strip()
        if not company_name:
            raise ValueError(
                "OutcomeResult exige o nome da empresa."
            )

        if isinstance(self.horizon_days, bool):
            raise ValueError(
                "horizon_days deve ser inteiro positivo."
            )

        try:
            horizon_days = int(self.horizon_days)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "horizon_days deve ser inteiro positivo."
            ) from exc

        if horizon_days <= 0 or float(self.horizon_days) != horizon_days:
            raise ValueError(
                "horizon_days deve ser inteiro positivo."
            )

        prices: dict[str, float] = {}
        for field_name in ("decision_price", "outcome_price"):
            try:
                price = float(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{field_name} deve ser numérico e positivo."
                ) from exc

            if price != price or price <= 0:
                raise ValueError(
                    f"{field_name} deve ser numérico e positivo."
                )
            prices[field_name] = round(price, 6)

        due_date = decision_date + timedelta(days=horizon_days)
        if evaluation_date < due_date:
            raise ValueError(
                "evaluation_date não pode anteceder o horizonte."
            )

        object.__setattr__(self, "decision_date", decision_date)
        object.__setattr__(self, "evaluation_date", evaluation_date)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "company_name", company_name)
        object.__setattr__(self, "horizon_days", horizon_days)
        object.__setattr__(
            self,
            "decision_price",
            prices["decision_price"],
        )
        object.__setattr__(
            self,
            "outcome_price",
            prices["outcome_price"],
        )

    @property
    def due_date(self) -> datetime:
        return self.decision_date + timedelta(
            days=self.horizon_days
        )

    @property
    def evaluation_lag_days(self) -> int:
        return (
            self.evaluation_date.date()
            - self.due_date.date()
        ).days

    @property
    def return_pct(self) -> float:
        return round(
            (self.outcome_price / self.decision_price - 1) * 100,
            6,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_date": self.decision_date.isoformat(
                timespec="seconds"
            ),
            "symbol": self.symbol,
            "company_name": self.company_name,
            "horizon_days": self.horizon_days,
            "due_date": self.due_date.isoformat(
                timespec="seconds"
            ),
            "evaluation_date": self.evaluation_date.isoformat(
                timespec="seconds"
            ),
            "evaluation_lag_days": self.evaluation_lag_days,
            "decision_price": self.decision_price,
            "outcome_price": self.outcome_price,
            "return_pct": self.return_pct,
        }

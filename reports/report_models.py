from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    text = str(value).strip()

    if text.lower() in {"", "nan", "none", "n/a"}:
        return default

    return text


def _normalize_score(
    value: Any,
    default: float | None = None,
) -> float | None:
    if value is None:
        return default

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default

    if numeric != numeric:
        return default

    return round(max(0.0, min(100.0, numeric)), 1)


def _normalize_items(
    values: Iterable[Any] | str | None,
) -> tuple[str, ...]:
    if values is None:
        return ()

    if isinstance(values, str):
        source = values.split(";")
    else:
        source = values

    items: list[str] = []

    for value in source:
        text = _normalize_text(value)

        if text and text not in items:
            items.append(text)

    return tuple(items)


@dataclass(frozen=True)
class CompanyReport:
    """
    Representação de domínio de uma análise individual do Atlas.

    Este objeto não depende de pandas e pode ser reutilizado por
    Excel, Markdown, Morning Brief, API, Dashboard e SDK.
    """

    symbol: str
    company_name: str = ""

    decision: str = ""
    decision_rating: str = ""
    suggested_action: str = ""
    decision_confidence: float | None = None
    decision_drivers: tuple[str, ...] = field(default_factory=tuple)

    investment_score: float | None = None
    opportunity_score: float | None = None
    conviction_score: float | None = None
    business_score: float | None = None
    valuation_score: float | None = None
    financial_score: float | None = None
    timing_score: float | None = None
    confidence_score: float | None = None
    data_coverage: float | None = None
    source_quality: float | None = None
    data_freshness: float | None = None
    risk_penalty: float | None = None
    observed_risk_penalty: float | None = None
    risk_uncertainty_penalty: float | None = None
    missing_required_features: tuple[str, ...] = field(default_factory=tuple)
    risk_evidence_missing: tuple[str, ...] = field(default_factory=tuple)

    reference_universe: str = ""
    reference_date: str = ""
    reference_count: int | None = None
    reference_version: str = ""

    investment_thesis: str = ""
    strengths: tuple[str, ...] = field(default_factory=tuple)
    risks: tuple[str, ...] = field(default_factory=tuple)
    catalysts: tuple[str, ...] = field(default_factory=tuple)
    deal_breakers: tuple[str, ...] = field(default_factory=tuple)

    generated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "symbol",
            _normalize_text(self.symbol).upper(),
        )
        object.__setattr__(
            self,
            "company_name",
            _normalize_text(self.company_name),
        )

        if not self.symbol:
            raise ValueError("CompanyReport exige um símbolo válido.")

        text_fields = [
            "decision",
            "decision_rating",
            "suggested_action",
            "investment_thesis",
            "reference_universe",
            "reference_date",
            "reference_version",
        ]

        for field_name in text_fields:
            object.__setattr__(
                self,
                field_name,
                _normalize_text(getattr(self, field_name)),
            )

        score_fields = [
            "decision_confidence",
            "investment_score",
            "opportunity_score",
            "conviction_score",
            "business_score",
            "valuation_score",
            "financial_score",
            "timing_score",
            "confidence_score",
            "data_coverage",
            "source_quality",
            "data_freshness",
            "risk_penalty",
            "observed_risk_penalty",
            "risk_uncertainty_penalty",
        ]

        for field_name in score_fields:
            object.__setattr__(
                self,
                field_name,
                _normalize_score(getattr(self, field_name)),
            )

        collection_fields = [
            "decision_drivers",
            "strengths",
            "risks",
            "catalysts",
            "deal_breakers",
            "missing_required_features",
            "risk_evidence_missing",
        ]

        for field_name in collection_fields:
            object.__setattr__(
                self,
                field_name,
                _normalize_items(getattr(self, field_name)),
            )

        if self.reference_count is not None:
            try:
                count = int(self.reference_count)
            except (TypeError, ValueError):
                count = None
            object.__setattr__(
                self,
                "reference_count",
                count if count is not None and count >= 0 else None,
            )

    @property
    def display_name(self) -> str:
        if self.company_name:
            return f"{self.company_name} ({self.symbol})"

        return self.symbol

    @property
    def has_risks(self) -> bool:
        return bool(self.risks or self.deal_breakers)

    @property
    def is_actionable(self) -> bool:
        return self.decision in {
            "STRONG_BUY",
            "BUY",
            "ACCUMULATE",
        }

    def scorecard(self) -> dict[str, float | None]:
        return {
            "Investment Score": self.investment_score,
            "Opportunity Score": self.opportunity_score,
            "Conviction Score": self.conviction_score,
            "Business Score": self.business_score,
            "Valuation Score": self.valuation_score,
            "Financial Score": self.financial_score,
            "Timing Score": self.timing_score,
            "Confidence Score": self.confidence_score,
            "Decision Confidence": self.decision_confidence,
            "Risk Penalty": self.risk_penalty,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "display_name": self.display_name,
            "decision": self.decision,
            "decision_rating": self.decision_rating,
            "suggested_action": self.suggested_action,
            "decision_confidence": self.decision_confidence,
            "decision_drivers": list(self.decision_drivers),
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "business_score": self.business_score,
            "valuation_score": self.valuation_score,
            "financial_score": self.financial_score,
            "timing_score": self.timing_score,
            "confidence_score": self.confidence_score,
            "data_coverage": self.data_coverage,
            "source_quality": self.source_quality,
            "data_freshness": self.data_freshness,
            "risk_penalty": self.risk_penalty,
            "observed_risk_penalty": self.observed_risk_penalty,
            "risk_uncertainty_penalty": self.risk_uncertainty_penalty,
            "missing_required_features": list(self.missing_required_features),
            "risk_evidence_missing": list(self.risk_evidence_missing),
            "reference_universe": self.reference_universe,
            "reference_date": self.reference_date,
            "reference_count": self.reference_count,
            "reference_version": self.reference_version,
            "investment_thesis": self.investment_thesis,
            "strengths": list(self.strengths),
            "risks": list(self.risks),
            "catalysts": list(self.catalysts),
            "deal_breakers": list(self.deal_breakers),
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
        }


@dataclass(frozen=True)
class MarketSummary:
    """
    Resumo agregado de uma execução do Atlas.
    """

    companies_analyzed: int = 0
    total_alerts: int = 0
    high_alerts: int = 0
    medium_alerts: int = 0
    new_opportunities: int = 0
    strong_opportunities: int = 0
    average_opportunity: float | None = None
    maximum_opportunity: float | None = None
    generated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        integer_fields = [
            "companies_analyzed",
            "total_alerts",
            "high_alerts",
            "medium_alerts",
            "new_opportunities",
            "strong_opportunities",
        ]

        for field_name in integer_fields:
            value = max(0, int(getattr(self, field_name)))
            object.__setattr__(self, field_name, value)

        object.__setattr__(
            self,
            "average_opportunity",
            _normalize_score(self.average_opportunity),
        )
        object.__setattr__(
            self,
            "maximum_opportunity",
            _normalize_score(self.maximum_opportunity),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "companies_analyzed": self.companies_analyzed,
            "total_alerts": self.total_alerts,
            "high_alerts": self.high_alerts,
            "medium_alerts": self.medium_alerts,
            "new_opportunities": self.new_opportunities,
            "strong_opportunities": self.strong_opportunities,
            "average_opportunity": self.average_opportunity,
            "maximum_opportunity": self.maximum_opportunity,
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
        }


@dataclass(frozen=True)
class PortfolioReport:
    """
    Modelo inicial para relatórios agregados de carteira.

    Nesta release ele serve apenas como contrato de domínio.
    O Portfolio Intelligence será implementado na versão 1.0.
    """

    portfolio_name: str
    holdings_count: int = 0
    total_value: float | None = None
    average_investment_score: float | None = None
    average_opportunity_score: float | None = None
    average_conviction_score: float | None = None
    concentration_risk: str = ""
    observations: tuple[str, ...] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        name = _normalize_text(self.portfolio_name)

        if not name:
            raise ValueError(
                "PortfolioReport exige um nome de carteira."
            )

        object.__setattr__(self, "portfolio_name", name)
        object.__setattr__(
            self,
            "holdings_count",
            max(0, int(self.holdings_count)),
        )

        if self.total_value is not None:
            try:
                total_value = max(0.0, float(self.total_value))
            except (TypeError, ValueError):
                total_value = None

            object.__setattr__(
                self,
                "total_value",
                total_value,
            )

        for field_name in [
            "average_investment_score",
            "average_opportunity_score",
            "average_conviction_score",
        ]:
            object.__setattr__(
                self,
                field_name,
                _normalize_score(getattr(self, field_name)),
            )

        object.__setattr__(
            self,
            "concentration_risk",
            _normalize_text(self.concentration_risk),
        )
        object.__setattr__(
            self,
            "observations",
            _normalize_items(self.observations),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_name": self.portfolio_name,
            "holdings_count": self.holdings_count,
            "total_value": self.total_value,
            "average_investment_score": (
                self.average_investment_score
            ),
            "average_opportunity_score": (
                self.average_opportunity_score
            ),
            "average_conviction_score": (
                self.average_conviction_score
            ),
            "concentration_risk": self.concentration_risk,
            "observations": list(self.observations),
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
        }

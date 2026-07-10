from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from portfolio.allocation import AllocationResult
from portfolio.concentration import ConcentrationResult
from portfolio.models import Holding, Portfolio


@dataclass(frozen=True)
class QualityPolicy:
    """
    Pesos usados para calcular o Portfolio Quality Score.

    A soma dos pesos deve ser igual a 1.
    """

    investment_weight: float = 0.35
    opportunity_weight: float = 0.25
    conviction_weight: float = 0.25
    decision_confidence_weight: float = 0.15

    concentration_penalty_weight: float = 0.20
    missing_report_penalty: float = 5.0


DEFAULT_QUALITY_POLICY = QualityPolicy()


class PortfolioQualityError(ValueError):
    """Erro de cálculo do Portfolio Quality Engine."""


@dataclass(frozen=True)
class PortfolioQualityResult:
    """
    Resultado consolidado da qualidade da carteira.
    """

    investment_score: float | None
    opportunity_score: float | None
    conviction_score: float | None
    decision_confidence: float | None

    base_quality_score: float | None
    concentration_penalty: float
    missing_report_penalty: float
    portfolio_quality_score: float | None

    rating: str
    covered_weight: float
    missing_report_symbols: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def has_full_coverage(self) -> bool:
        return (
            not self.missing_report_symbols
            and self.covered_weight >= 0.9999
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "decision_confidence": self.decision_confidence,
            "base_quality_score": self.base_quality_score,
            "concentration_penalty": self.concentration_penalty,
            "missing_report_penalty": self.missing_report_penalty,
            "portfolio_quality_score": self.portfolio_quality_score,
            "rating": self.rating,
            "covered_weight": self.covered_weight,
            "has_full_coverage": self.has_full_coverage,
            "missing_report_symbols": list(
                self.missing_report_symbols
            ),
            "warnings": list(self.warnings),
        }


def classify_portfolio_quality(
    score: float | None,
) -> str:
    if score is None:
        return "UNAVAILABLE"

    if score >= 85:
        return "EXCELLENT"

    if score >= 75:
        return "GOOD"

    if score >= 60:
        return "FAIR"

    if score >= 45:
        return "WEAK"

    return "POOR"


def _validate_policy(
    policy: QualityPolicy,
) -> None:
    score_weights = {
        "investment_weight": policy.investment_weight,
        "opportunity_weight": policy.opportunity_weight,
        "conviction_weight": policy.conviction_weight,
        "decision_confidence_weight": (
            policy.decision_confidence_weight
        ),
    }

    for name, value in score_weights.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise PortfolioQualityError(
                f"{name} deve ser numérico."
            ) from exc

        if numeric < 0:
            raise PortfolioQualityError(
                f"{name} não pode ser negativo."
            )

    total = sum(score_weights.values())

    if abs(total - 1.0) > 0.0001:
        raise PortfolioQualityError(
            "A soma dos pesos de qualidade deve ser igual a 1. "
            f"Valor encontrado: {total:.6f}."
        )

    if not 0.0 <= policy.concentration_penalty_weight <= 1.0:
        raise PortfolioQualityError(
            "concentration_penalty_weight deve estar "
            "entre 0 e 1."
        )

    if policy.missing_report_penalty < 0:
        raise PortfolioQualityError(
            "missing_report_penalty não pode ser negativo."
        )


def _holding_weight(
    holding: Holding,
    portfolio: Portfolio,
) -> float:
    if holding.portfolio_weight is not None:
        return holding.portfolio_weight

    if portfolio.total_value <= 0:
        return 0.0

    return (holding.market_value or 0.0) / portfolio.total_value


def _weighted_score(
    portfolio: Portfolio,
    attribute: str,
) -> tuple[float | None, float]:
    weighted_sum = 0.0
    covered_weight = 0.0

    for holding in portfolio.holdings:
        report = holding.company_report

        if report is None:
            continue

        value = getattr(report, attribute)

        if value is None:
            continue

        weight = _holding_weight(
            holding,
            portfolio,
        )

        if weight <= 0:
            continue

        weighted_sum += float(value) * weight
        covered_weight += weight

    if covered_weight <= 0:
        return None, 0.0

    return (
        round(weighted_sum / covered_weight, 1),
        round(covered_weight, 6),
    )


def _average_coverage(
    coverages: tuple[float, ...],
) -> float:
    valid = [
        value
        for value in coverages
        if value > 0
    ]

    if not valid:
        return 0.0

    return round(
        sum(valid) / len(valid),
        6,
    )


def _build_base_quality(
    *,
    investment_score: float | None,
    opportunity_score: float | None,
    conviction_score: float | None,
    decision_confidence: float | None,
    policy: QualityPolicy,
) -> float | None:
    values = {
        "investment": (
            investment_score,
            policy.investment_weight,
        ),
        "opportunity": (
            opportunity_score,
            policy.opportunity_weight,
        ),
        "conviction": (
            conviction_score,
            policy.conviction_weight,
        ),
        "decision_confidence": (
            decision_confidence,
            policy.decision_confidence_weight,
        ),
    }

    available = [
        (value, weight)
        for value, weight in values.values()
        if value is not None
    ]

    if not available:
        return None

    available_weight = sum(
        weight
        for _, weight in available
    )

    if available_weight <= 0:
        return None

    score = sum(
        float(value) * weight
        for value, weight in available
    ) / available_weight

    return round(score, 1)


def calculate_portfolio_quality(
    portfolio: Portfolio,
    *,
    concentration: ConcentrationResult | None = None,
    policy: QualityPolicy = DEFAULT_QUALITY_POLICY,
    inherited_warnings: tuple[str, ...] = (),
) -> PortfolioQualityResult:
    """
    Calcula a qualidade agregada da carteira.

    As médias são ponderadas pelo valor atual de cada holding.
    Caixa não recebe score e, portanto, não participa das médias.
    """

    if not isinstance(portfolio, Portfolio):
        raise TypeError(
            "calculate_portfolio_quality exige "
            "um objeto Portfolio."
        )

    _validate_policy(policy)

    weighted_portfolio = portfolio.with_calculated_weights()

    investment_score, investment_coverage = _weighted_score(
        weighted_portfolio,
        "investment_score",
    )
    opportunity_score, opportunity_coverage = _weighted_score(
        weighted_portfolio,
        "opportunity_score",
    )
    conviction_score, conviction_coverage = _weighted_score(
        weighted_portfolio,
        "conviction_score",
    )
    decision_confidence, decision_coverage = _weighted_score(
        weighted_portfolio,
        "decision_confidence",
    )

    covered_weight = _average_coverage(
        (
            investment_coverage,
            opportunity_coverage,
            conviction_coverage,
            decision_coverage,
        )
    )

    base_quality_score = _build_base_quality(
        investment_score=investment_score,
        opportunity_score=opportunity_score,
        conviction_score=conviction_score,
        decision_confidence=decision_confidence,
        policy=policy,
    )

    concentration_penalty = 0.0

    if concentration is not None:
        if not isinstance(
            concentration,
            ConcentrationResult,
        ):
            raise TypeError(
                "concentration deve ser "
                "um ConcentrationResult."
            )

        concentration_score = (
            concentration.risk.concentration_score
            or 0.0
        )

        concentration_penalty = round(
            concentration_score
            * policy.concentration_penalty_weight,
            1,
        )

    missing_symbols = tuple(
        holding.symbol
        for holding in weighted_portfolio.holdings
        if holding.company_report is None
    )

    missing_report_penalty = round(
        len(missing_symbols)
        * policy.missing_report_penalty,
        1,
    )

    if base_quality_score is None:
        final_score = None
    else:
        final_score = round(
            max(
                0.0,
                min(
                    100.0,
                    base_quality_score
                    - concentration_penalty
                    - missing_report_penalty,
                ),
            ),
            1,
        )

    warnings: list[str] = list(inherited_warnings)

    if missing_symbols:
        warnings.append(
            "Holdings sem CompanyReport: "
            + ", ".join(missing_symbols)
        )

    if covered_weight < 0.9999:
        warnings.append(
            "Cobertura parcial dos scores da carteira: "
            f"{covered_weight:.1%}"
        )

    if concentration is not None:
        warnings.extend(
            concentration.risk.warnings
        )

    if base_quality_score is None:
        warnings.append(
            "Não há scores suficientes para calcular "
            "a qualidade da carteira."
        )

    return PortfolioQualityResult(
        investment_score=investment_score,
        opportunity_score=opportunity_score,
        conviction_score=conviction_score,
        decision_confidence=decision_confidence,
        base_quality_score=base_quality_score,
        concentration_penalty=concentration_penalty,
        missing_report_penalty=missing_report_penalty,
        portfolio_quality_score=final_score,
        rating=classify_portfolio_quality(
            final_score
        ),
        covered_weight=covered_weight,
        missing_report_symbols=missing_symbols,
        warnings=tuple(
            dict.fromkeys(warnings)
        ),
    )


def calculate_allocation_quality(
    allocation: AllocationResult,
    *,
    concentration: ConcentrationResult | None = None,
    policy: QualityPolicy = DEFAULT_QUALITY_POLICY,
) -> PortfolioQualityResult:
    """
    Calcula qualidade a partir do AllocationResult.
    """

    if not isinstance(
        allocation,
        AllocationResult,
    ):
        raise TypeError(
            "calculate_allocation_quality exige "
            "um AllocationResult."
        )

    return calculate_portfolio_quality(
        allocation.portfolio,
        concentration=concentration,
        policy=policy,
        inherited_warnings=allocation.warnings,
    )

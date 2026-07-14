from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from portfolio.allocation import AllocationResult
from portfolio.concentration import ConcentrationResult
from portfolio.quality import PortfolioQualityResult
from portfolio.rebalance import RebalancePlan


@dataclass(frozen=True)
class PortfolioReport:
    """
    Relatório consolidado da camada Portfolio Intelligence.

    O objeto é independente de pandas e pode ser serializado para
    Excel, Markdown, JSON, API ou Dashboard.
    """

    portfolio_name: str
    generated_at: datetime

    summary: dict[str, Any]
    allocation: dict[str, Any]
    concentration: dict[str, Any]
    quality: dict[str, Any]
    rebalance: dict[str, Any]
    warnings: tuple[str, ...] = ()

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat(
            timespec="seconds"
        )
        data["warnings"] = list(self.warnings)
        return data


def _collect_warnings(
    allocation_result: AllocationResult,
    concentration_result: ConcentrationResult,
    quality_result: PortfolioQualityResult,
    rebalance_plan: RebalancePlan,
) -> tuple[str, ...]:
    values = [
        *allocation_result.warnings,
        *concentration_result.risk.warnings,
        *quality_result.warnings,
        *rebalance_plan.warnings,
    ]

    return tuple(
        dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    )


def build_portfolio_report(
    allocation_result: AllocationResult,
    concentration_result: ConcentrationResult,
    quality_result: PortfolioQualityResult,
    rebalance_plan: RebalancePlan,
) -> PortfolioReport:
    """
    Consolida os resultados dos quatro motores de portfólio.
    """

    if not isinstance(
        allocation_result,
        AllocationResult,
    ):
        raise TypeError(
            "allocation_result deve ser AllocationResult."
        )

    if not isinstance(
        concentration_result,
        ConcentrationResult,
    ):
        raise TypeError(
            "concentration_result deve ser ConcentrationResult."
        )

    if not isinstance(
        quality_result,
        PortfolioQualityResult,
    ):
        raise TypeError(
            "quality_result deve ser PortfolioQualityResult."
        )

    if not isinstance(
        rebalance_plan,
        RebalancePlan,
    ):
        raise TypeError(
            "rebalance_plan deve ser RebalancePlan."
        )

    portfolio = allocation_result.portfolio
    snapshot = allocation_result.snapshot
    risk = concentration_result.risk

    summary = {
        "portfolio_name": portfolio.name,
        "currency": portfolio.currency,
        "holdings_count": portfolio.holdings_count,
        "total_market_value": portfolio.total_market_value,
        "cash": portfolio.cash,
        "cash_weight": snapshot.cash_weight,
        "total_value": portfolio.total_value,
        "quality_rating": quality_result.rating,
        "quality_score": (
            quality_result.portfolio_quality_score
        ),
        "covered_weight": quality_result.covered_weight,
        "concentration_score": risk.concentration_score,
        "diversification_score": risk.diversification_score,
        "largest_position_weight": (
            risk.largest_position_weight
        ),
        "top_5_weight": risk.top_5_weight,
        "rebalance_actions": len(
            rebalance_plan.actions
        ),
        "buy_actions": len(
            rebalance_plan.buy_actions
        ),
        "sell_actions": len(
            rebalance_plan.sell_actions
        ),
        "hold_actions": len(
            rebalance_plan.hold_actions
        ),
        "trim_actions": len(
            rebalance_plan.trim_actions
        ),
        "review_actions": len(
            rebalance_plan.review_actions
        ),
        "required_cash": rebalance_plan.required_cash,
        "released_cash": rebalance_plan.released_cash,
        "net_cash_requirement": (
            rebalance_plan.net_cash_requirement
        ),
        "estimated_turnover": (
            rebalance_plan.estimated_turnover
        ),
    }

    return PortfolioReport(
        portfolio_name=portfolio.name,
        generated_at=datetime.now(),
        summary=summary,
        allocation=snapshot.to_dict(),
        concentration=risk.to_dict(),
        quality=quality_result.to_dict(),
        rebalance=rebalance_plan.to_dict(),
        warnings=_collect_warnings(
            allocation_result,
            concentration_result,
            quality_result,
            rebalance_plan,
        ),
    )

"""
Portfolio Report Engine (PR-016.7)

Este módulo consolida Allocation, Concentration, Quality e
Rebalance em um único relatório serializável.
"""

from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class PortfolioReport:
    summary: dict[str, Any]
    allocation: dict[str, Any]
    concentration: dict[str, Any]
    quality: dict[str, Any]
    rebalance: dict[str, Any]

    def to_dict(self)->dict[str,Any]:
        return asdict(self)

def build_portfolio_report(
    allocation_result,
    concentration_result,
    quality_result,
    rebalance_plan,
)->PortfolioReport:
    return PortfolioReport(
        summary={
            "quality_rating": getattr(quality_result,"rating",None),
            "quality_score": getattr(quality_result,"portfolio_quality_score",None),
            "turnover": getattr(rebalance_plan,"estimated_turnover",None),
        },
        allocation=getattr(allocation_result,"snapshot",allocation_result).to_dict(),
        concentration=getattr(concentration_result,"risk",concentration_result).to_dict(),
        quality=quality_result.to_dict(),
        rebalance=rebalance_plan.to_dict(),
    )

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SellPriorityItem:
    """
    Classificação individual de um holding da carteira atual.

    `action` é SELL quando o holding tem ao menos um Deal Breaker ativo,
    HOLD caso contrário. Não é uma sugestão de peso -- apenas prioridade.
    `current_weight` é informativo (peso atual real), nunca um alvo.
    """

    symbol: str
    investment_score: float | None
    action: str
    deal_breakers: tuple[str, ...] = ()
    current_weight: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "investment_score": self.investment_score,
            "action": self.action,
            "deal_breakers": list(self.deal_breakers),
            "current_weight": self.current_weight,
        }


@dataclass(frozen=True)
class SellPriorityReport:
    items: tuple[SellPriorityItem, ...] = ()
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class BuyPriorityItem:
    """
    Classificação individual de um candidato do screener (universo amplo).

    Ordenado por `candidate_rank` (qualidade decrescente); só inclui quem
    passou o safeguard governado (sem Deal Breaker, confiança mínima). Não
    carrega peso nem restrição setorial -- é uma classificação, não uma
    construção de carteira.
    """

    symbol: str
    sector: str
    candidate_rank: int
    investment_score: float | None
    opportunity_score: float | None
    conviction_score: float | None
    confidence_score: float | None
    already_held: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "candidate_rank": self.candidate_rank,
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "confidence_score": self.confidence_score,
            "already_held": self.already_held,
        }


@dataclass(frozen=True)
class BuyPriorityReport:
    items: tuple[BuyPriorityItem, ...] = ()
    total_candidate_count: int = 0
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "total_candidate_count": self.total_candidate_count,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class PriorityReport:
    """Feixe read-only: prioridade de venda (sempre) + de compra (opcional)."""

    sell: SellPriorityReport
    buy: BuyPriorityReport | None = None
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "sell": self.sell.to_dict(),
            "buy": self.buy.to_dict() if self.buy is not None else None,
        }

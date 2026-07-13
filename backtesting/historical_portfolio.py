from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from backtesting.point_in_time import AsOfSnapshot, PointInTimeDataset
from backtesting.portfolio_validation import PortfolioRebalance
from backtesting.walk_forward import (
    IncompleteDecision,
    compute_governed_config_hashes,
    score_snapshot_batch,
)
from portfolio.model_portfolio import (
    PortfolioConstructionError,
    build_model_portfolio,
    load_model_portfolio_policy,
)
from ranking import load_ranking_policy, rank_companies
from universe import evaluate_universe, load_universe_policy


class HistoricalPortfolioConstructionError(ValueError):
    """Raised when an incomplete historical target cannot become a trade."""


def _date(value: date | datetime | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser uma data ISO-8601.") from exc


@dataclass(frozen=True)
class HistoricalTargetPortfolio:
    decision_at: datetime
    target_weights: Mapping[str, float]
    sectors: Mapping[str, str]
    incomplete_decisions: tuple[IncompleteDecision, ...]
    universe_member_count: int
    universe_eligible_count: int
    candidate_count: int
    governed_config_hashes: Mapping[str, str]
    construction_error: str | None = None

    def __post_init__(self) -> None:
        if self.decision_at.tzinfo is None or self.decision_at.utcoffset() is None:
            raise ValueError("decision_at exige fuso horário explícito.")
        weights = dict(sorted(self.target_weights.items()))
        sectors = dict(sorted(self.sectors.items()))
        if set(weights) != set(sectors):
            raise ValueError("Todo target histórico exige setor explícito.")
        if self.construction_error is None and not weights:
            raise ValueError("Target sem erro exige ao menos uma posição.")
        if self.construction_error is not None and weights:
            raise ValueError("Target com erro não pode conter posições.")
        hashes = dict(sorted(self.governed_config_hashes.items()))
        if not hashes or any(not value for value in hashes.values()):
            raise ValueError("governed_config_hashes não pode ser vazio.")
        object.__setattr__(self, "target_weights", weights)
        object.__setattr__(self, "sectors", sectors)
        object.__setattr__(self, "governed_config_hashes", hashes)
        object.__setattr__(
            self, "incomplete_decisions", tuple(self.incomplete_decisions)
        )

    @property
    def constructed(self) -> bool:
        return self.construction_error is None

    def to_rebalance(
        self,
        effective_on: date | datetime | str,
    ) -> PortfolioRebalance:
        """
        Converte uma decisão em rebalanceamento somente quando o chamador
        fornece a data efetiva de execução. A decisão nunca presume execução
        no mesmo fechamento que gerou seus dados.
        """
        if not self.constructed:
            raise HistoricalPortfolioConstructionError(
                self.construction_error or "TARGET_NOT_CONSTRUCTED"
            )
        effective_date = _date(effective_on, "effective_on")
        if effective_date < self.decision_at.date():
            raise ValueError("effective_on não pode anteceder decision_at.")
        return PortfolioRebalance(
            effective_on=effective_date,
            target_weights=self.target_weights,
            sectors=self.sectors,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_at": self.decision_at.isoformat(),
            "constructed": self.constructed,
            "construction_error": self.construction_error,
            "governed_config_hashes": dict(self.governed_config_hashes),
            "coverage": {
                "universe_member_count": self.universe_member_count,
                "universe_eligible_count": self.universe_eligible_count,
                "candidate_count": self.candidate_count,
                "incomplete_decision_count": len(self.incomplete_decisions),
            },
            "target_weights": dict(self.target_weights),
            "sectors": dict(self.sectors),
            "incomplete_decisions": [
                item.to_dict() for item in self.incomplete_decisions
            ],
        }


def build_historical_target_portfolio(
    snapshot: AsOfSnapshot,
    *,
    model_path: str | Path,
    deal_breakers_path: str | Path,
    universe_policy_path: str | Path,
    ranking_policy_path: str | Path,
    model_portfolio_policy_path: str | Path,
) -> HistoricalTargetPortfolio:
    """
    Constrói o alvo consultivo de um cutoff usando somente o snapshot as-of e
    as mesmas políticas executáveis do pipeline atual. Cobertura incompleta
    permanece no resultado; falha de construção não vira carteira parcial.
    """
    if not isinstance(snapshot, AsOfSnapshot):
        raise TypeError("snapshot exige AsOfSnapshot.")
    governed_config_hashes = compute_governed_config_hashes(
        {
            "model": model_path,
            "deal_breakers": deal_breakers_path,
            "universe_policy": universe_policy_path,
            "ranking_policy": ranking_policy_path,
            "model_portfolio_policy": model_portfolio_policy_path,
        }
    )
    scored, incomplete = score_snapshot_batch(
        snapshot,
        model_path=model_path,
        deal_breakers_path=deal_breakers_path,
    )
    if scored.empty:
        return HistoricalTargetPortfolio(
            decision_at=snapshot.decision_at,
            target_weights={},
            sectors={},
            incomplete_decisions=incomplete,
            universe_member_count=len(snapshot.members),
            universe_eligible_count=0,
            candidate_count=0,
            governed_config_hashes=governed_config_hashes,
            construction_error="NO_SCORABLE_MEMBERS",
        )

    universe_report = evaluate_universe(
        scored,
        load_universe_policy(universe_policy_path),
    )
    ranking_report = rank_companies(
        scored,
        universe_report,
        load_ranking_policy(ranking_policy_path),
    )
    metadata = {
        str(row["symbol"]): row.to_dict()
        for _, row in scored.iterrows()
    }
    try:
        model_report = build_model_portfolio(
            ranking_report,
            load_model_portfolio_policy(model_portfolio_policy_path),
            metadata=metadata,
            universe_snapshot_date=snapshot.decision_at.date().isoformat(),
            collection_updated_at=snapshot.decision_at.isoformat(),
        )
    except PortfolioConstructionError as exc:
        return HistoricalTargetPortfolio(
            decision_at=snapshot.decision_at,
            target_weights={},
            sectors={},
            incomplete_decisions=incomplete,
            universe_member_count=len(snapshot.members),
            universe_eligible_count=universe_report.eligible_count,
            candidate_count=ranking_report.candidate_count,
            governed_config_hashes=governed_config_hashes,
            construction_error=str(exc),
        )

    return HistoricalTargetPortfolio(
        decision_at=snapshot.decision_at,
        target_weights={
            position.symbol: position.target_weight
            for position in model_report.positions
        },
        sectors={
            position.symbol: position.sector
            for position in model_report.positions
        },
        incomplete_decisions=incomplete,
        universe_member_count=len(snapshot.members),
        universe_eligible_count=universe_report.eligible_count,
        candidate_count=ranking_report.candidate_count,
        governed_config_hashes=governed_config_hashes,
    )


def build_historical_target_portfolios(
    dataset: PointInTimeDataset,
    decision_dates: Iterable[datetime | str],
    *,
    model_path: str | Path,
    deal_breakers_path: str | Path,
    universe_policy_path: str | Path,
    ranking_policy_path: str | Path,
    model_portfolio_policy_path: str | Path,
) -> tuple[HistoricalTargetPortfolio, ...]:
    """Constrói alvos ordenados e deduplicados para cutoffs explícitos."""
    if not isinstance(dataset, PointInTimeDataset):
        raise TypeError("dataset exige PointInTimeDataset.")
    snapshots = {
        snapshot.decision_at: snapshot
        for snapshot in (dataset.as_of(item) for item in decision_dates)
    }
    if not snapshots:
        raise ValueError("decision_dates não pode ser vazio.")
    paths = {
        "model_path": model_path,
        "deal_breakers_path": deal_breakers_path,
        "universe_policy_path": universe_policy_path,
        "ranking_policy_path": ranking_policy_path,
        "model_portfolio_policy_path": model_portfolio_policy_path,
    }
    return tuple(
        build_historical_target_portfolio(snapshots[decision_at], **paths)
        for decision_at in sorted(snapshots)
    )

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from analytics.mapper import normalize_columns
from ranking import load_ranking_policy, rank_companies, write_ranking_report
from ranking.models import RankingReport
from scoring.investment import score_dataframe
from universe import evaluate_universe, load_universe_policy, write_universe_report
from universe.collector import load_collection_state
from universe.sources import load_constituent_snapshot


ROOT = Path(__file__).resolve().parents[1]


class PortfolioConstructionError(ValueError):
    """Raised when explicit construction constraints cannot be satisfied."""


@dataclass(frozen=True)
class ModelPortfolioPolicy:
    name: str
    target_positions: int = 20
    weighting_method: str = "equal"
    max_position_weight: float = 0.05
    max_sector_weight: float = 0.20
    cash_weight: float = 0.0
    max_initial_turnover: float = 1.0

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("ModelPortfolioPolicy exige name.")
        if int(self.target_positions) <= 0:
            raise ValueError("target_positions deve ser positivo.")
        if self.weighting_method != "equal":
            raise ValueError("Somente weighting_method=equal é suportado.")
        for field_name in (
            "max_position_weight",
            "max_sector_weight",
            "cash_weight",
            "max_initial_turnover",
        ):
            value = float(getattr(self, field_name))
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} deve estar entre 0 e 1.")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "name", str(self.name).strip())
        object.__setattr__(self, "target_positions", int(self.target_positions))

        investable_weight = 1.0 - self.cash_weight
        equal_weight = investable_weight / self.target_positions
        if equal_weight > self.max_position_weight + 1e-12:
            raise ValueError(
                "max_position_weight é incompatível com target_positions."
            )
        if equal_weight > self.max_sector_weight + 1e-12:
            raise ValueError(
                "max_sector_weight é menor que uma posição de peso igual."
            )
        if investable_weight > self.max_initial_turnover + 1e-12:
            raise ValueError(
                "max_initial_turnover não comporta a formação a partir de caixa."
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelPortfolioPolicy":
        if not isinstance(data, dict):
            raise TypeError("A política de carteira-modelo deve ser um objeto.")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_positions": self.target_positions,
            "weighting_method": self.weighting_method,
            "max_position_weight": self.max_position_weight,
            "max_sector_weight": self.max_sector_weight,
            "cash_weight": self.cash_weight,
            "max_initial_turnover": self.max_initial_turnover,
        }


@dataclass(frozen=True)
class ModelPosition:
    symbol: str
    name: str
    sector: str
    industry: str
    target_weight: float
    candidate_rank: int
    market_rank: int | None
    sector_rank: int | None
    investment_score: float
    opportunity_score: float | None
    conviction_score: float | None
    confidence_score: float | None
    reference_price: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "target_weight": self.target_weight,
            "candidate_rank": self.candidate_rank,
            "market_rank": self.market_rank,
            "sector_rank": self.sector_rank,
            "investment_score": self.investment_score,
            "opportunity_score": self.opportunity_score,
            "conviction_score": self.conviction_score,
            "confidence_score": self.confidence_score,
            "reference_price": self.reference_price,
        }


@dataclass(frozen=True)
class ModelPortfolioReport:
    policy: ModelPortfolioPolicy
    universe_snapshot_date: str
    collection_updated_at: str
    total_observations: int
    universe_eligible_count: int
    candidate_count: int
    positions: tuple[ModelPosition, ...]
    warnings: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def invested_weight(self) -> float:
        return round(sum(item.target_weight for item in self.positions), 6)

    @property
    def sector_weights(self) -> dict[str, float]:
        weights: dict[str, float] = {}
        for item in self.positions:
            weights[item.sector] = weights.get(item.sector, 0.0) + item.target_weight
        return {
            sector: round(weight, 6)
            for sector, weight in sorted(weights.items())
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "advisory_only": True,
            "policy": self.policy.to_dict(),
            "source": {
                "universe_snapshot_date": self.universe_snapshot_date,
                "collection_updated_at": self.collection_updated_at,
                "total_observations": self.total_observations,
                "universe_eligible_count": self.universe_eligible_count,
                "candidate_count": self.candidate_count,
            },
            "summary": {
                "position_count": len(self.positions),
                "invested_weight": self.invested_weight,
                "cash_weight": self.policy.cash_weight,
                "sector_weights": self.sector_weights,
                "expected_initial_turnover": self.invested_weight,
                "warnings": list(self.warnings),
            },
            "positions": [item.to_dict() for item in self.positions],
        }


def load_model_portfolio_policy(path: str | Path) -> ModelPortfolioPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ModelPortfolioPolicy.from_dict(data)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def build_model_portfolio(
    ranking_report: RankingReport,
    policy: ModelPortfolioPolicy,
    *,
    metadata: Mapping[str, Mapping[str, Any]] | None = None,
    universe_snapshot_date: str = "",
    collection_updated_at: str = "",
) -> ModelPortfolioReport:
    if not isinstance(ranking_report, RankingReport):
        raise TypeError("build_model_portfolio exige RankingReport.")
    if not isinstance(policy, ModelPortfolioPolicy):
        raise TypeError("build_model_portfolio exige ModelPortfolioPolicy.")

    company_metadata = metadata or {}
    candidates = sorted(
        (
            company
            for company in ranking_report.companies
            if company.safeguard_passed and company.candidate_rank is not None
        ),
        key=lambda company: (company.candidate_rank or 10**9, company.symbol),
    )
    equal_weight = round(
        (1.0 - policy.cash_weight) / policy.target_positions,
        6,
    )
    selected = []
    sector_weights: dict[str, float] = {}
    sector_cap_skips = 0
    for company in candidates:
        sector = company.sector or "UNKNOWN"
        if (
            sector_weights.get(sector, 0.0) + equal_weight
            > policy.max_sector_weight + 1e-12
        ):
            sector_cap_skips += 1
            continue
        selected.append(company)
        sector_weights[sector] = sector_weights.get(sector, 0.0) + equal_weight
        if len(selected) == policy.target_positions:
            break

    if len(selected) < policy.target_positions:
        raise PortfolioConstructionError(
            "Candidatos insuficientes para cumprir simultaneamente os limites "
            "de posição e setor."
        )

    target_total = round(1.0 - policy.cash_weight, 6)
    weights = [equal_weight] * len(selected)
    weights[-1] = round(target_total - sum(weights[:-1]), 6)
    if weights[-1] > policy.max_position_weight + 1e-12:
        raise PortfolioConstructionError("Arredondamento excedeu o limite por posição.")

    positions: list[ModelPosition] = []
    for company, weight in zip(selected, weights):
        details = company_metadata.get(company.symbol, {})
        positions.append(
            ModelPosition(
                symbol=company.symbol,
                name=str(details.get("name", "")).strip(),
                sector=company.sector,
                industry=str(details.get("industry", "")).strip(),
                target_weight=weight,
                candidate_rank=int(company.candidate_rank),
                market_rank=company.market_rank,
                sector_rank=company.sector_rank,
                investment_score=float(company.investment_score),
                opportunity_score=company.opportunity_score,
                conviction_score=company.conviction_score,
                confidence_score=company.confidence_score,
                reference_price=_number(details.get("price")),
            )
        )

    warnings = (
        (f"{sector_cap_skips} candidato(s) superior(es) ignorado(s) pelo limite setorial.",)
        if sector_cap_skips
        else ()
    )
    return ModelPortfolioReport(
        policy=policy,
        universe_snapshot_date=universe_snapshot_date,
        collection_updated_at=collection_updated_at,
        total_observations=ranking_report.total_count,
        universe_eligible_count=ranking_report.universe_eligible_count,
        candidate_count=ranking_report.candidate_count,
        positions=tuple(positions),
        warnings=warnings,
    )


def write_model_portfolio_report(
    report: ModelPortfolioReport,
    path: str | Path,
) -> Path:
    if not isinstance(report, ModelPortfolioReport):
        raise TypeError("report deve ser ModelPortfolioReport.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def build_from_collection(
    *,
    state_path: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
) -> ModelPortfolioReport:
    snapshot = load_constituent_snapshot(snapshot_path)
    snapshot_dates = {row["snapshot_date"] for row in snapshot}
    if len(snapshot_dates) != 1:
        raise ValueError("Snapshot do universo possui datas inconsistentes.")
    snapshot_date = next(iter(snapshot_dates))
    state = load_collection_state(
        state_path,
        snapshot_date=snapshot_date,
        total_constituents=len(snapshot),
    )
    if len(state.observations) != len(snapshot) or state.failures:
        raise PortfolioConstructionError(
            "A coleta deve estar completa e sem falhas antes da construção."
        )

    frame = normalize_columns(pd.DataFrame(state.observations.values()))
    scored = score_dataframe(
        frame,
        ROOT / "config" / "model.yaml",
        ROOT / "config" / "deal_breakers.json",
    )
    universe_report = evaluate_universe(
        scored,
        load_universe_policy(ROOT / "config" / "universe.yaml"),
    )
    ranking_report = rank_companies(
        scored,
        universe_report,
        load_ranking_policy(ROOT / "config" / "ranking.yaml"),
    )
    metadata = {
        str(row["symbol"]): row
        for row in state.observations.values()
    }
    report = build_model_portfolio(
        ranking_report,
        load_model_portfolio_policy(ROOT / "config" / "model_portfolio.yaml"),
        metadata=metadata,
        universe_snapshot_date=snapshot_date,
        collection_updated_at=state.updated_at,
    )
    outputs = Path(output_dir)
    write_universe_report(universe_report, outputs / "research_universe_report.json")
    write_ranking_report(ranking_report, outputs / "research_ranking_report.json")
    write_model_portfolio_report(report, outputs / "model_portfolio_report.json")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Constrói a carteira-modelo consultiva do universo coletado."
    )
    parser.add_argument(
        "--state",
        default=str(ROOT / "data" / "research_universe_collection.json"),
    )
    parser.add_argument(
        "--snapshot",
        default=str(ROOT / "config" / "research_universe.csv"),
    )
    parser.add_argument("--output-dir", default=str(ROOT / "output"))
    args = parser.parse_args()
    report = build_from_collection(
        state_path=args.state,
        snapshot_path=args.snapshot,
        output_dir=args.output_dir,
    )
    print(
        f"Carteira-modelo: {len(report.positions)} posições; "
        f"{report.universe_eligible_count} elegíveis; "
        f"{report.candidate_count} candidatos."
    )


if __name__ == "__main__":
    main()

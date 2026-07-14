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
from ranking import (
    load_ranking_policy,
    rank_companies,
    write_candidate_ranking_csv,
    write_ranking_report,
)
from ranking.models import RankingReport
from reports.research_html import render_research_report, write_research_report
from scoring.investment import score_dataframe
from universe import evaluate_universe, load_universe_policy, write_universe_report
from universe.collector import CollectionState, load_collection_state
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
    excluded_failures: tuple[tuple[str, str], ...] = ()
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
                "excluded_failure_count": len(self.excluded_failures),
                "excluded_failures": [
                    {"symbol": symbol, "reason": reason}
                    for symbol, reason in self.excluded_failures
                ],
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
    excluded_failures: Mapping[str, str] | None = None,
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

    excluded = tuple(sorted((excluded_failures or {}).items()))
    warnings_list: list[str] = []
    if sector_cap_skips:
        warnings_list.append(
            f"{sector_cap_skips} candidato(s) superior(es) ignorado(s) "
            "pelo limite setorial."
        )
    if excluded:
        warnings_list.append(
            f"{len(excluded)} constituinte(s) excluído(s) por falha "
            "permanente do provider (sem série de preço)."
        )
    return ModelPortfolioReport(
        policy=policy,
        universe_snapshot_date=universe_snapshot_date,
        collection_updated_at=collection_updated_at,
        total_observations=ranking_report.total_count,
        universe_eligible_count=ranking_report.universe_eligible_count,
        candidate_count=ranking_report.candidate_count,
        positions=tuple(positions),
        warnings=tuple(warnings_list),
        excluded_failures=excluded,
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


def _labeled_filename(base_name: str, label: str) -> str:
    """
    Sem label (padrão, screener S&P 500): nome de arquivo idêntico ao de
    sempre. Com label (ex.: "market", "adr"): sufixo distinto, para não
    sobrescrever a saída de outro screener no mesmo output_dir.
    """
    if not label:
        return base_name
    stem, _, suffix = base_name.rpartition(".")
    return f"{stem}_{label}.{suffix}"


def _resolve_residual_failures(
    state: CollectionState,
    *,
    expected: int,
    allow_exhausted_failures: bool,
    failure_attempt_budget: int | None,
) -> dict[str, str]:
    """
    Decide se uma coleta pode alimentar a construção da carteira e devolve as
    falhas permanentes a registrar no relatório.

    Contrato estrito (padrão, ``allow_exhausted_failures=False``): a coleta
    precisa estar completa e sem falha alguma — comportamento idêntico ao
    histórico do screener S&P 500.

    Contrato permissivo (``allow_exhausted_failures=True``): aceita falhas cujo
    orçamento de tentativas se esgotou (``attempts >= failure_attempt_budget``),
    pois são terminais — instrumentos sem série de preço (warrants, units,
    rights, preferenciais, papéis suspensos) que nunca produzirão observação.
    Ainda BARRA quando há falha transitória (retentável) ou quando algum
    símbolo do snapshot não foi sequer tentado (coleta incompleta poderia
    esconder uma large cap ausente por erro transitório).
    """
    observed = len(state.observations)
    if not allow_exhausted_failures:
        if observed != expected or state.failures:
            raise PortfolioConstructionError(
                "A coleta deve estar completa e sem falhas antes da construção."
            )
        return {}

    if failure_attempt_budget is None or failure_attempt_budget <= 0:
        raise ValueError(
            "failure_attempt_budget deve ser positivo quando "
            "allow_exhausted_failures está ativo."
        )

    transient = sorted(
        symbol
        for symbol, details in state.failures.items()
        if int(details.get("attempts", 0)) < failure_attempt_budget
    )
    if transient:
        raise PortfolioConstructionError(
            "A coleta ainda tem falhas retentáveis (transitórias): "
            f"{', '.join(transient[:10])}"
            f"{'…' if len(transient) > 10 else ''}. "
            "Conclua a coleta antes da construção."
        )

    if observed + len(state.failures) != expected:
        raise PortfolioConstructionError(
            "A coleta não cobre todo o snapshot: "
            f"{expected - observed - len(state.failures)} símbolo(s) sem "
            "tentativa registrada. Conclua a coleta antes da construção."
        )

    return {
        symbol: str(details.get("last_error", "")).strip()
        for symbol, details in state.failures.items()
    }


def build_from_collection(
    *,
    state_path: str | Path,
    snapshot_path: str | Path,
    output_dir: str | Path,
    universe_policy_path: str | Path = ROOT / "config" / "universe.yaml",
    ranking_policy_path: str | Path = ROOT / "config" / "ranking.yaml",
    model_portfolio_policy_path: str
    | Path = ROOT / "config" / "model_portfolio.yaml",
    output_label: str = "",
    allow_exhausted_failures: bool = False,
    failure_attempt_budget: int | None = None,
) -> ModelPortfolioReport:
    """
    Constrói a carteira-modelo a partir de uma coleta completa.

    Por padrão, usa exatamente as três políticas do screener S&P 500 e os
    nomes de arquivo históricos (comportamento idêntico ao de antes desta
    parametrização). Para rodar sobre outro screener (mercado amplo, ADR),
    passe `universe_policy_path` apontando para a política correspondente
    e `output_label` (ex.: "market", "adr") para gerar arquivos de saída
    com nome distinto, sem sobrescrever a saída do S&P 500.
    """
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
    excluded_failures = _resolve_residual_failures(
        state,
        expected=len(snapshot),
        allow_exhausted_failures=allow_exhausted_failures,
        failure_attempt_budget=failure_attempt_budget,
    )

    frame = normalize_columns(pd.DataFrame(state.observations.values()))
    scored = score_dataframe(
        frame,
        ROOT / "config" / "model.yaml",
        ROOT / "config" / "deal_breakers.json",
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
        str(row["symbol"]): row
        for row in state.observations.values()
    }
    report = build_model_portfolio(
        ranking_report,
        load_model_portfolio_policy(model_portfolio_policy_path),
        metadata=metadata,
        universe_snapshot_date=snapshot_date,
        collection_updated_at=state.updated_at,
        excluded_failures=excluded_failures,
    )
    outputs = Path(output_dir)
    write_universe_report(
        universe_report,
        outputs / _labeled_filename("research_universe_report.json", output_label),
    )
    write_ranking_report(
        ranking_report,
        outputs / _labeled_filename("research_ranking_report.json", output_label),
    )
    write_candidate_ranking_csv(
        ranking_report,
        outputs / _labeled_filename("research_candidates.csv", output_label),
        metadata=metadata,
    )
    write_model_portfolio_report(
        report,
        outputs / _labeled_filename("model_portfolio_report.json", output_label),
    )

    screener_display_name = {
        "": "S&P 500",
        "market": "Mercado Amplo",
        "adr": "ADR",
    }.get(output_label, output_label or "S&P 500")
    write_research_report(
        render_research_report(
            ranking_report.to_dict(),
            report.to_dict(),
            label=screener_display_name,
        ),
        outputs / _labeled_filename("research_report.html", output_label),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Constrói a carteira-modelo consultiva do universo coletado. "
            "Por padrão, o screener S&P 500; use --universe-policy (e "
            "--label, para nomear a saída) para rodar sobre outro screener "
            "(mercado amplo, ADR) sem sobrescrever a saída do S&P 500."
        )
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
    parser.add_argument(
        "--universe-policy",
        default=str(ROOT / "config" / "universe.yaml"),
    )
    parser.add_argument(
        "--ranking-policy",
        default=str(ROOT / "config" / "ranking.yaml"),
    )
    parser.add_argument(
        "--model-portfolio-policy",
        default=str(ROOT / "config" / "model_portfolio.yaml"),
    )
    parser.add_argument(
        "--label",
        default="",
        help=(
            "Sufixo dos arquivos de saída (ex.: market, adr). Vazio "
            "(padrão) mantém os nomes históricos do screener S&P 500."
        ),
    )
    parser.add_argument(
        "--allow-exhausted-failures",
        action="store_true",
        help=(
            "Aceita falhas permanentes (orçamento de tentativas esgotado — "
            "instrumentos sem série de preço) e as registra no relatório, em "
            "vez de barrar a construção. Ainda barra falhas transitórias e "
            "coleta incompleta. Necessário no screener de mercado amplo, onde "
            "warrants/units/rights nunca produzem observação."
        ),
    )
    args = parser.parse_args()

    settings = json.loads(
        (ROOT / "config" / "settings.json").read_text(encoding="utf-8")
    )
    failure_attempt_budget = int(settings.get("research_collection_retries", 2)) + 1

    report = build_from_collection(
        state_path=args.state,
        snapshot_path=args.snapshot,
        output_dir=args.output_dir,
        universe_policy_path=args.universe_policy,
        ranking_policy_path=args.ranking_policy,
        model_portfolio_policy_path=args.model_portfolio_policy,
        output_label=args.label,
        allow_exhausted_failures=args.allow_exhausted_failures,
        failure_attempt_budget=failure_attempt_budget,
    )
    excluded = len(report.excluded_failures)
    print(
        f"Carteira-modelo: {len(report.positions)} posições; "
        f"{report.universe_eligible_count} elegíveis; "
        f"{report.candidate_count} candidatos"
        + (f"; {excluded} falha(s) permanente(s) excluída(s)." if excluded else ".")
    )


if __name__ == "__main__":
    main()

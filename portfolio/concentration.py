from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from portfolio.allocation import AllocationResult
from portfolio.models import AllocationSnapshot, PortfolioRisk


@dataclass(frozen=True)
class ConcentrationPolicy:
    """
    Limites usados para avaliar concentração da carteira.

    Todos os pesos usam escala decimal:
    0.20 representa 20%.
    """

    max_position_weight: float = 0.20
    max_top_5_weight: float = 0.70
    max_sector_weight: float = 0.35
    max_country_weight: float = 0.60
    max_currency_weight: float = 0.70
    minimum_cash_weight: float = 0.05


DEFAULT_CONCENTRATION_POLICY = ConcentrationPolicy()


class ConcentrationError(ValueError):
    """Erro de cálculo do Concentration Engine."""


@dataclass(frozen=True)
class ConcentrationResult:
    """
    Resultado completo da análise de concentração.
    """

    risk: PortfolioRisk
    policy: ConcentrationPolicy
    breaches: tuple[str, ...] = ()

    @property
    def has_breaches(self) -> bool:
        return bool(self.breaches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk.to_dict(),
            "policy": {
                "max_position_weight": (
                    self.policy.max_position_weight
                ),
                "max_top_5_weight": (
                    self.policy.max_top_5_weight
                ),
                "max_sector_weight": (
                    self.policy.max_sector_weight
                ),
                "max_country_weight": (
                    self.policy.max_country_weight
                ),
                "max_currency_weight": (
                    self.policy.max_currency_weight
                ),
                "minimum_cash_weight": (
                    self.policy.minimum_cash_weight
                ),
            },
            "breaches": list(self.breaches),
        }


def _validate_policy(
    policy: ConcentrationPolicy,
) -> None:
    values = {
        "max_position_weight": policy.max_position_weight,
        "max_top_5_weight": policy.max_top_5_weight,
        "max_sector_weight": policy.max_sector_weight,
        "max_country_weight": policy.max_country_weight,
        "max_currency_weight": policy.max_currency_weight,
        "minimum_cash_weight": policy.minimum_cash_weight,
    }

    for name, value in values.items():
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ConcentrationError(
                f"{name} deve ser numérico."
            ) from exc

        if not 0.0 <= numeric <= 1.0:
            raise ConcentrationError(
                f"{name} deve estar entre 0 e 1."
            )


def _largest_weight(
    weights: dict[str, float],
) -> float:
    if not weights:
        return 0.0

    return max(weights.values())


def _top_n_weight(
    weights: dict[str, float],
    count: int,
) -> float:
    if count <= 0 or not weights:
        return 0.0

    ordered = sorted(
        weights.values(),
        reverse=True,
    )

    return round(
        sum(ordered[:count]),
        6,
    )


def _herfindahl_index(
    weights: dict[str, float],
) -> float:
    """
    Índice HHI em escala 0..1.

    Caixa não é incluído aqui porque o objetivo é medir a
    concentração entre os ativos investidos.
    """

    invested_total = sum(weights.values())

    if invested_total <= 0:
        return 0.0

    normalized = [
        weight / invested_total
        for weight in weights.values()
    ]

    return sum(
        weight ** 2
        for weight in normalized
    )


def _score_concentration(
    weights: dict[str, float],
) -> tuple[float, float]:
    """
    Converte HHI em scores de concentração e diversificação.

    - concentração alta => score próximo de 100
    - diversificação alta => score próximo de 100
    """

    hhi = _herfindahl_index(weights)

    concentration_score = round(
        min(100.0, max(0.0, hhi * 100.0)),
        1,
    )

    diversification_score = round(
        100.0 - concentration_score,
        1,
    )

    return (
        concentration_score,
        diversification_score,
    )


def _dimension_breaches(
    values: dict[str, float],
    *,
    limit: float,
    label: str,
) -> list[str]:
    breaches: list[str] = []

    for name, weight in sorted(
        values.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        if weight > limit:
            breaches.append(
                f"{label} acima do limite: "
                f"{name} = {weight:.1%} "
                f"(limite {limit:.1%})"
            )

    return breaches


def analyze_concentration(
    snapshot: AllocationSnapshot,
    *,
    policy: ConcentrationPolicy = (
        DEFAULT_CONCENTRATION_POLICY
    ),
    inherited_warnings: tuple[str, ...] = (),
) -> ConcentrationResult:
    """
    Analisa concentração a partir de um AllocationSnapshot.
    """

    if not isinstance(
        snapshot,
        AllocationSnapshot,
    ):
        raise TypeError(
            "analyze_concentration exige "
            "um AllocationSnapshot."
        )

    _validate_policy(policy)

    largest_position = _largest_weight(
        snapshot.by_symbol
    )
    top_5_weight = _top_n_weight(
        snapshot.by_symbol,
        5,
    )

    concentration_score, diversification_score = (
        _score_concentration(
            snapshot.by_symbol
        )
    )

    breaches: list[str] = []

    if (
        largest_position
        > policy.max_position_weight
    ):
        breaches.append(
            "Maior posição acima do limite: "
            f"{largest_position:.1%} "
            f"(limite {policy.max_position_weight:.1%})"
        )

    if top_5_weight > policy.max_top_5_weight:
        breaches.append(
            "Top 5 posições acima do limite: "
            f"{top_5_weight:.1%} "
            f"(limite {policy.max_top_5_weight:.1%})"
        )

    breaches.extend(
        _dimension_breaches(
            snapshot.by_sector,
            limit=policy.max_sector_weight,
            label="Setor",
        )
    )
    breaches.extend(
        _dimension_breaches(
            snapshot.by_country,
            limit=policy.max_country_weight,
            label="País",
        )
    )
    breaches.extend(
        _dimension_breaches(
            snapshot.by_currency,
            limit=policy.max_currency_weight,
            label="Moeda",
        )
    )

    if (
        snapshot.cash_weight
        < policy.minimum_cash_weight
    ):
        breaches.append(
            "Caixa abaixo do mínimo: "
            f"{snapshot.cash_weight:.1%} "
            f"(mínimo {policy.minimum_cash_weight:.1%})"
        )

    warnings = tuple(
        dict.fromkeys(
            [
                *inherited_warnings,
                *breaches,
            ]
        )
    )

    risk = PortfolioRisk(
        concentration_score=concentration_score,
        diversification_score=diversification_score,
        largest_position_weight=largest_position,
        top_5_weight=top_5_weight,
        sector_concentration=snapshot.by_sector,
        country_concentration=snapshot.by_country,
        currency_concentration=snapshot.by_currency,
        warnings=warnings,
    )

    return ConcentrationResult(
        risk=risk,
        policy=policy,
        breaches=tuple(breaches),
    )


def analyze_allocation_concentration(
    allocation: AllocationResult,
    *,
    policy: ConcentrationPolicy = (
        DEFAULT_CONCENTRATION_POLICY
    ),
) -> ConcentrationResult:
    """
    Analisa um AllocationResult e reaproveita seus warnings.
    """

    if not isinstance(
        allocation,
        AllocationResult,
    ):
        raise TypeError(
            "analyze_allocation_concentration exige "
            "um AllocationResult."
        )

    return analyze_concentration(
        allocation.snapshot,
        policy=policy,
        inherited_warnings=allocation.warnings,
    )

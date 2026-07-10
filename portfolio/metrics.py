from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from portfolio.models import Holding


K = TypeVar("K", bound=str)


UNKNOWN_SECTOR = "Unknown Sector"
UNKNOWN_COUNTRY = "Unknown Country"
UNKNOWN_CURRENCY = "UNKNOWN"


def holding_market_value(holding: Holding) -> float:
    """
    Retorna o valor de mercado usado na alocação.

    Holdings sem preço atual contribuem com zero e permanecem
    disponíveis para alertas de qualidade de dados.
    """

    return holding.market_value or 0.0


def normalize_dimension(
    value: str,
    *,
    fallback: str,
    uppercase: bool = False,
) -> str:
    normalized = str(value or "").strip()

    if not normalized:
        normalized = fallback

    if uppercase:
        normalized = normalized.upper()

    return normalized


def aggregate_weights(
    holdings: Iterable[Holding],
    *,
    total_value: float,
    dimension: str,
    fallback: str,
    uppercase: bool = False,
) -> dict[str, float]:
    """
    Agrega pesos por uma dimensão textual da Holding.

    Exemplos de dimensão:
    - sector
    - country
    - currency
    """

    if total_value <= 0:
        return {}

    result: dict[str, float] = {}

    for holding in holdings:
        market_value = holding_market_value(holding)

        if market_value <= 0:
            continue

        key = normalize_dimension(
            getattr(holding, dimension, ""),
            fallback=fallback,
            uppercase=uppercase,
        )

        result[key] = (
            result.get(key, 0.0)
            + market_value / total_value
        )

    return {
        key: round(value, 6)
        for key, value in sorted(
            result.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )
    }


def rounded_weights_with_residual(
    raw_weights: dict[str, float],
    *,
    target_total: float,
) -> dict[str, float]:
    """
    Arredonda pesos e corrige o resíduo no maior componente.

    Isso mantém a soma compatível com AllocationSnapshot mesmo
    depois do arredondamento decimal.
    """

    if not raw_weights:
        return {}

    result = {
        key: round(value, 6)
        for key, value in raw_weights.items()
    }

    residual = round(
        target_total - sum(result.values()),
        6,
    )

    if residual:
        largest_key = max(
            result,
            key=result.get,
        )
        result[largest_key] = round(
            result[largest_key] + residual,
            6,
        )

    return result

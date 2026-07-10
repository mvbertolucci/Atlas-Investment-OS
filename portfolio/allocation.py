from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from portfolio.metrics import (
    UNKNOWN_COUNTRY,
    UNKNOWN_CURRENCY,
    UNKNOWN_SECTOR,
    aggregate_weights,
    holding_market_value,
    rounded_weights_with_residual,
)
from portfolio.models import (
    AllocationSnapshot,
    Portfolio,
)


class AllocationError(ValueError):
    """Erro de cálculo da alocação da carteira."""


@dataclass(frozen=True)
class AllocationResult:
    """
    Resultado completo do Allocation Engine.

    `snapshot` contém a visão consolidada.
    `portfolio` contém as holdings com pesos calculados.
    `warnings` registra limitações de dados.
    """

    portfolio: Portfolio
    snapshot: AllocationSnapshot
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio": self.portfolio.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "warnings": list(self.warnings),
        }


def _symbol_weights(
    portfolio: Portfolio,
) -> dict[str, float]:
    total_value = portfolio.total_value

    if total_value <= 0:
        return {}

    raw = {
        holding.symbol: (
            holding_market_value(holding)
            / total_value
        )
        for holding in portfolio.holdings
        if holding_market_value(holding) > 0
    }

    cash_weight = portfolio.cash / total_value

    return rounded_weights_with_residual(
        raw,
        target_total=1.0 - cash_weight,
    )


def _build_warnings(
    portfolio: Portfolio,
) -> tuple[str, ...]:
    warnings: list[str] = []

    if portfolio.missing_price_symbols:
        warnings.append(
            "Holdings sem preço atual: "
            + ", ".join(portfolio.missing_price_symbols)
        )

    if portfolio.missing_report_symbols:
        warnings.append(
            "Holdings sem CompanyReport: "
            + ", ".join(portfolio.missing_report_symbols)
        )

    if not portfolio.holdings:
        warnings.append(
            "A carteira não possui holdings."
        )

    if portfolio.total_market_value <= 0:
        warnings.append(
            "Nenhuma holding possui valor de mercado positivo."
        )

    return tuple(warnings)


def calculate_allocation(
    portfolio: Portfolio,
) -> AllocationResult:
    """
    Calcula a alocação completa de um Portfolio.

    Os pesos incluem o caixa no denominador, portanto:
    soma(by_symbol) + cash_weight == 1.
    """

    if not isinstance(portfolio, Portfolio):
        raise TypeError(
            "calculate_allocation exige um objeto Portfolio."
        )

    total_value = portfolio.total_value

    if total_value <= 0:
        raise AllocationError(
            "Não é possível calcular a alocação de uma "
            "carteira com valor total igual a zero."
        )

    cash_weight = round(
        portfolio.cash / total_value,
        6,
    )

    by_symbol = _symbol_weights(portfolio)

    by_sector = aggregate_weights(
        portfolio.holdings,
        total_value=total_value,
        dimension="sector",
        fallback=UNKNOWN_SECTOR,
    )

    by_country = aggregate_weights(
        portfolio.holdings,
        total_value=total_value,
        dimension="country",
        fallback=UNKNOWN_COUNTRY,
    )

    by_currency = aggregate_weights(
        portfolio.holdings,
        total_value=total_value,
        dimension="currency",
        fallback=UNKNOWN_CURRENCY,
        uppercase=True,
    )

    snapshot = AllocationSnapshot(
        by_symbol=by_symbol,
        by_sector=by_sector,
        by_country=by_country,
        by_currency=by_currency,
        cash_weight=cash_weight,
    )

    weighted_portfolio = portfolio.with_calculated_weights()

    return AllocationResult(
        portfolio=weighted_portfolio,
        snapshot=snapshot,
        warnings=_build_warnings(portfolio),
    )


def build_allocation_snapshot(
    portfolio: Portfolio,
) -> AllocationSnapshot:
    """
    Atalho público para consumidores que precisam apenas do snapshot.
    """

    return calculate_allocation(portfolio).snapshot

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from storage.atomic_write import atomic_write_json


SCENARIO_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class PortfolioScenario:
    generated_at: str
    currency: str
    total_value: float
    cash_before: float
    cash_after: float
    released_cash: float
    estimated_cost: float
    turnover: float
    weights_after: dict[str, float]
    sector_weights_after: dict[str, float]
    executed_actions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(self.weights_after.values(), reverse=True)
        return {
            "contract_version": SCENARIO_CONTRACT_VERSION,
            "generated_at": self.generated_at,
            "advisory_only": True,
            "assumption": "Execute only official SELL/TRIM trade values; no replacement buys.",
            "currency": self.currency,
            "summary": {
                "total_value": self.total_value,
                "cash_before": self.cash_before,
                "cash_after": self.cash_after,
                "cash_weight_before": round(self.cash_before / self.total_value, 6),
                "cash_weight_after": round(self.cash_after / self.total_value, 6),
                "released_cash": self.released_cash,
                "estimated_cost": self.estimated_cost,
                "turnover": self.turnover,
                "largest_position_weight_after": round(ordered[0], 6) if ordered else 0.0,
                "top_5_weight_after": round(sum(ordered[:5]), 6),
            },
            "weights_after": dict(self.weights_after),
            "sector_weights_after": dict(self.sector_weights_after),
            "executed_actions": list(self.executed_actions),
        }


def build_sell_scenario(
    portfolio: Mapping[str, Any],
    *,
    transaction_cost_rate: float = 0.0,
    generated_at: str | None = None,
) -> PortfolioScenario:
    if not 0 <= transaction_cost_rate <= 1:
        raise ValueError("transaction_cost_rate deve estar entre 0 e 1.")
    summary = portfolio.get("summary") or {}
    total_value = float(summary.get("total_value") or 0.0)
    if total_value <= 0:
        raise ValueError("portfolio exige total_value positivo.")
    cash_before = float(summary.get("cash") or 0.0)
    holdings = portfolio.get("holdings") or []
    values = {
        str(item.get("symbol", "")).upper(): float(item.get("market_value") or 0.0)
        for item in holdings
        if str(item.get("symbol", "")).strip()
    }
    sectors = {
        str(item.get("symbol", "")).upper(): str(item.get("sector") or "Unknown")
        for item in holdings
    }
    executed: list[dict[str, Any]] = []
    released = 0.0
    for action in (portfolio.get("rebalance") or {}).get("actions", []):
        kind = str(action.get("action", "")).upper()
        if kind not in {"SELL", "TRIM"}:
            continue
        symbol = str(action.get("symbol", "")).upper()
        trade_value = float(action.get("trade_value") or 0.0)
        if trade_value >= 0 or symbol not in values:
            continue
        sale_value = min(-trade_value, values[symbol])
        values[symbol] = round(values[symbol] - sale_value, 2)
        released += sale_value
        executed.append(
            {"symbol": symbol, "action": kind, "sale_value": round(sale_value, 2)}
        )
    cost = round(released * transaction_cost_rate, 2)
    cash_after = round(cash_before + released - cost, 2)
    weights = {
        symbol: round(value / total_value, 6)
        for symbol, value in values.items()
        if value > 0
    }
    sector_weights: dict[str, float] = {}
    for symbol, weight in weights.items():
        sector = sectors.get(symbol, "Unknown")
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
    sector_weights = {key: round(value, 6) for key, value in sector_weights.items()}
    return PortfolioScenario(
        generated_at=generated_at or datetime.now().isoformat(timespec="seconds"),
        currency=str(summary.get("currency") or "USD"),
        total_value=round(total_value, 2),
        cash_before=round(cash_before, 2),
        cash_after=cash_after,
        released_cash=round(released, 2),
        estimated_cost=cost,
        turnover=round(released / total_value, 6),
        weights_after=weights,
        sector_weights_after=sector_weights,
        executed_actions=tuple(executed),
    )


def write_portfolio_scenario(scenario: PortfolioScenario, path: str | Path) -> Path:
    if not isinstance(scenario, PortfolioScenario):
        raise TypeError("scenario deve ser PortfolioScenario.")
    return atomic_write_json(path, scenario.to_dict(), ensure_ascii=False, indent=2)

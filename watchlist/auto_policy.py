from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} deve ser um objeto YAML.")
    return value


@dataclass(frozen=True)
class WatchlistAutoPolicy:
    """Política governada do fluxo de curadoria automática da watchlist.

    Espelha `portfolio.sell_rules.SellRulesPolicy`: seções cruas guardadas
    como dict, expostas por `@property` tipada com default em código --
    `config/watchlist_auto.yaml` sempre especifica as chaves explicitamente
    hoje, então os defaults nunca são de fato lidos em produção, mas existem
    para não quebrar caso uma chave seja omitida no futuro.
    """

    selection: Mapping[str, Any]
    exit: Mapping[str, Any]
    safeguards: Mapping[str, Any]
    enabled: bool = False

    def __post_init__(self) -> None:
        for field_name in ("selection", "exit", "safeguards"):
            object.__setattr__(
                self,
                field_name,
                dict(_mapping(getattr(self, field_name), field_name)),
            )
        object.__setattr__(self, "enabled", bool(self.enabled))

        if self.top_n <= 0:
            raise ValueError("selection.top_n deve ser positivo.")
        if not 0 <= self.exit_investment_score_threshold <= 100:
            raise ValueError(
                "exit.investment_score_threshold deve estar entre 0 e 100."
            )
        if not 0 <= self.min_confidence_score <= 100:
            raise ValueError(
                "selection.min_confidence_score deve estar entre 0 e 100."
            )
        if not self.qualifying_decisions:
            raise ValueError("selection.qualifying_decisions não pode ser vazio.")

    @property
    def top_n(self) -> int:
        return int(self.selection.get("top_n", 30))

    @property
    def qualifying_decisions(self) -> tuple[str, ...]:
        raw = self.selection.get(
            "qualifying_decisions", ["STRONG_BUY", "BUY", "ACCUMULATE"]
        )
        return tuple(str(item).strip().upper() for item in raw)

    @property
    def min_confidence_score(self) -> float:
        return float(self.selection.get("min_confidence_score", 60.0))

    @property
    def exit_investment_score_threshold(self) -> float:
        return float(self.exit.get("investment_score_threshold", 40.0))

    @property
    def protect_portfolio_holdings(self) -> bool:
        return bool(self.safeguards.get("protect_portfolio_holdings", True))

    @property
    def protect_manual_entries(self) -> bool:
        return bool(self.safeguards.get("protect_manual_entries", True))


def load_watchlist_auto_policy(path: str | Path) -> WatchlistAutoPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise TypeError("watchlist_auto.yaml deve conter um objeto.")
    return WatchlistAutoPolicy(
        selection=_mapping(data.get("selection", {}), "selection"),
        exit=_mapping(data.get("exit", {}), "exit"),
        safeguards=_mapping(data.get("safeguards", {}), "safeguards"),
        enabled=bool(data.get("enabled", False)),
    )

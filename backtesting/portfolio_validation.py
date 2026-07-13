from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from backtesting.point_in_time import DELISTING_TREATMENTS


CASH_SYMBOL = "CASH"
INPUT_SCHEMA_VERSION = 1
PERFORMANCE_DISCLAIMER = (
    "Historical validation is research evidence, not a performance promise. "
    "Results depend on the stated return, benchmark, cost and terminal-event "
    "assumptions and do not represent live execution."
)


def _text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} não pode ser vazio.")
    return text


def _date(value: date | datetime | str, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser uma data ISO-8601.") from exc


def _finite(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser numérico e finito.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} deve ser numérico e finito.")
    return number


def _rounded(value: float) -> float:
    return round(value, 10)


@dataclass(frozen=True)
class PortfolioValidationPolicy:
    name: str
    benchmark_symbol: str
    periods_per_year: int = 12
    transaction_cost_bps: float = 10.0
    base_currency: str = "USD"
    dividends_included: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        object.__setattr__(
            self,
            "benchmark_symbol",
            _text(self.benchmark_symbol, "benchmark_symbol").upper(),
        )
        periods = int(self.periods_per_year)
        if periods <= 0:
            raise ValueError("periods_per_year deve ser positivo.")
        object.__setattr__(self, "periods_per_year", periods)
        cost = _finite(self.transaction_cost_bps, "transaction_cost_bps")
        if cost < 0 or cost > 10_000:
            raise ValueError(
                "transaction_cost_bps deve estar entre 0 e 10000."
            )
        object.__setattr__(self, "transaction_cost_bps", cost)
        object.__setattr__(
            self,
            "base_currency",
            _text(self.base_currency, "base_currency").upper(),
        )
        if not isinstance(self.dividends_included, bool):
            raise TypeError("dividends_included deve ser booleano.")

    @property
    def transaction_cost_rate(self) -> float:
        return self.transaction_cost_bps / 10_000.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PortfolioValidationPolicy":
        if not isinstance(data, Mapping):
            raise TypeError("A política de validação deve ser um objeto.")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "benchmark_symbol": self.benchmark_symbol,
            "periods_per_year": self.periods_per_year,
            "transaction_cost_bps": self.transaction_cost_bps,
            "base_currency": self.base_currency,
            "dividends_included": self.dividends_included,
        }


@dataclass(frozen=True)
class PortfolioValidationManifest:
    dataset_name: str
    dataset_version: str
    portfolio_source: str
    return_source: str
    benchmark_source: str
    period_convention: str
    terminal_event_source: str
    atlas_code_revision: str

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any]
    ) -> "PortfolioValidationManifest":
        if not isinstance(data, Mapping):
            raise TypeError("manifest deve ser um objeto.")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, str]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class PortfolioRebalance:
    effective_on: date | datetime | str
    target_weights: Mapping[str, float]
    sectors: Mapping[str, str] = field(default_factory=dict)
    factor_exposures: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        effective_on = _date(self.effective_on, "effective_on")
        weights: dict[str, float] = {}
        for raw_symbol, raw_weight in self.target_weights.items():
            symbol = _text(raw_symbol, "symbol").upper()
            if symbol == CASH_SYMBOL:
                raise ValueError("CASH é implícito e não deve estar em target_weights.")
            if symbol in weights:
                raise ValueError("Símbolo duplicado em target_weights.")
            weight = _finite(raw_weight, f"target_weights[{symbol}]")
            if weight <= 0 or weight > 1:
                raise ValueError("Cada target weight deve ser maior que 0 e até 1.")
            weights[symbol] = weight
        if not weights:
            raise ValueError("target_weights não pode ser vazio.")
        if sum(weights.values()) > 1 + 1e-12:
            raise ValueError("A soma de target_weights não pode exceder 1.")
        sectors: dict[str, str] = {}
        for raw_symbol, raw_sector in self.sectors.items():
            symbol = _text(raw_symbol, "sector symbol").upper()
            if symbol not in weights:
                raise ValueError("sectors só pode conter símbolos da carteira.")
            if symbol in sectors:
                raise ValueError("Símbolo duplicado em sectors.")
            sectors[symbol] = _text(raw_sector, f"sectors[{symbol}]")
        factor_exposures: dict[str, dict[str, float]] = {}
        factor_names: set[str] | None = None
        for raw_symbol, raw_exposures in self.factor_exposures.items():
            symbol = _text(raw_symbol, "factor exposure symbol").upper()
            if symbol not in weights:
                raise ValueError("factor_exposures só pode conter símbolos da carteira.")
            if symbol in factor_exposures:
                raise ValueError("Símbolo duplicado em factor_exposures.")
            if not isinstance(raw_exposures, Mapping) or not raw_exposures:
                raise ValueError(f"factor_exposures[{symbol}] deve ser um objeto não vazio.")
            exposures = {
                _text(raw_factor, "factor name"): _finite(
                    raw_value, f"factor_exposures[{symbol}][{raw_factor}]"
                )
                for raw_factor, raw_value in raw_exposures.items()
            }
            names = frozenset(exposures)
            if factor_names is None:
                factor_names = names
            elif names != factor_names:
                raise ValueError(
                    "factor_exposures deve usar o mesmo conjunto de fatores para "
                    "todos os símbolos."
                )
            factor_exposures[symbol] = dict(sorted(exposures.items()))
        object.__setattr__(self, "effective_on", effective_on)
        object.__setattr__(self, "target_weights", dict(sorted(weights.items())))
        object.__setattr__(self, "sectors", dict(sorted(sectors.items())))
        object.__setattr__(
            self, "factor_exposures", dict(sorted(factor_exposures.items()))
        )

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - sum(self.target_weights.values()))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PortfolioRebalance":
        if not isinstance(data, Mapping):
            raise TypeError("rebalance deve ser um objeto.")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_on": self.effective_on.isoformat(),
            "target_weights": dict(self.target_weights),
            "sectors": dict(self.sectors),
            "factor_exposures": {
                symbol: dict(values)
                for symbol, values in self.factor_exposures.items()
            },
        }


@dataclass(frozen=True)
class AssetPeriodReturn:
    symbol: str
    period_start: date | datetime | str
    period_end: date | datetime | str
    total_return: float | None
    source: str
    currency: str = "USD"
    dividends_included: bool = True
    terminal_treatment: str | None = None

    def __post_init__(self) -> None:
        symbol = _text(self.symbol, "symbol").upper()
        period_start = _date(self.period_start, "period_start")
        period_end = _date(self.period_end, "period_end")
        if period_end <= period_start:
            raise ValueError("period_end deve ser posterior a period_start.")
        treatment = (
            _text(self.terminal_treatment, "terminal_treatment").lower()
            if self.terminal_treatment is not None
            else None
        )
        if treatment is not None and treatment not in DELISTING_TREATMENTS:
            raise ValueError("terminal_treatment não suportado.")
        if treatment == "unresolved":
            if self.total_return is not None:
                raise ValueError("Delistagem unresolved não pode inventar retorno.")
            total_return = None
        else:
            if self.total_return is None:
                raise ValueError("total_return é obrigatório para retorno resolvido.")
            total_return = _finite(self.total_return, "total_return")
            if total_return < -1:
                raise ValueError("total_return não pode ser menor que -1.")
            if treatment == "zero" and total_return != -1:
                raise ValueError("Delistagem zero exige total_return igual a -1.")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "period_start", period_start)
        object.__setattr__(self, "period_end", period_end)
        object.__setattr__(self, "total_return", total_return)
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(
            self, "currency", _text(self.currency, "currency").upper()
        )
        if not isinstance(self.dividends_included, bool):
            raise TypeError("dividends_included deve ser booleano.")
        object.__setattr__(self, "terminal_treatment", treatment)

    @property
    def identity(self) -> tuple[str, date, date]:
        return (self.symbol, self.period_start, self.period_end)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssetPeriodReturn":
        if not isinstance(data, Mapping):
            raise TypeError("return deve ser um objeto.")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_return": self.total_return,
            "source": self.source,
            "currency": self.currency,
            "dividends_included": self.dividends_included,
            "terminal_treatment": self.terminal_treatment,
        }


@dataclass(frozen=True)
class ValidationPeriod:
    period_start: date
    period_end: date
    gross_return: float
    net_return: float
    benchmark_return: float
    turnover: float
    estimated_cost: float
    position_hhi: float
    maximum_position_weight: float
    sector_hhi: float | None = None
    maximum_sector_weight: float | None = None
    sector_contributions: Mapping[str, float] | None = None
    factor_exposures: Mapping[str, float] | None = None
    terminal_events: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "benchmark_return": self.benchmark_return,
            "excess_return": _rounded(self.net_return - self.benchmark_return),
            "turnover": self.turnover,
            "estimated_cost": self.estimated_cost,
            "position_hhi": self.position_hhi,
            "maximum_position_weight": self.maximum_position_weight,
            "sector_hhi": self.sector_hhi,
            "maximum_sector_weight": self.maximum_sector_weight,
            "sector_contributions": (
                dict(self.sector_contributions)
                if self.sector_contributions is not None
                else None
            ),
            "factor_exposures": (
                dict(self.factor_exposures)
                if self.factor_exposures is not None
                else None
            ),
            "terminal_events": list(self.terminal_events),
        }


@dataclass(frozen=True)
class IncompleteValidationPeriod:
    period_start: date
    period_end: date
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ValidationSummary:
    total_return: float
    benchmark_total_return: float
    relative_return: float | None
    annualized_return: float
    annualized_volatility: float
    maximum_drawdown: float
    average_turnover: float
    total_estimated_cost: float
    average_position_hhi: float
    maximum_position_weight: float
    average_sector_hhi: float | None
    maximum_sector_weight: float | None

    def to_dict(self) -> dict[str, float | None]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PortfolioValidationReport:
    manifest: PortfolioValidationManifest
    policy: PortfolioValidationPolicy
    periods: tuple[ValidationPeriod, ...]
    incomplete_periods: tuple[IncompleteValidationPeriod, ...]
    summary: ValidationSummary | None
    return_sources: tuple[str, ...] = ()
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, PortfolioValidationManifest):
            raise TypeError("manifest exige PortfolioValidationManifest.")
        if not isinstance(self.policy, PortfolioValidationPolicy):
            raise TypeError("policy exige PortfolioValidationPolicy.")
        if (
            not isinstance(self.generated_at, datetime)
            or self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() is None
        ):
            raise ValueError("generated_at exige timestamp com fuso horário.")
        object.__setattr__(
            self, "generated_at", self.generated_at.astimezone(timezone.utc)
        )
        object.__setattr__(
            self, "return_sources", tuple(sorted(set(self.return_sources)))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "advisory_only": True,
            "performance_disclaimer": PERFORMANCE_DISCLAIMER,
            "status": "complete" if self.summary is not None else "incomplete",
            "input_schema_version": INPUT_SCHEMA_VERSION,
            "manifest": self.manifest.to_dict(),
            "policy": self.policy.to_dict(),
            "return_sources": list(self.return_sources),
            "summary": self.summary.to_dict() if self.summary else None,
            "periods": [item.to_dict() for item in self.periods],
            "incomplete_periods": [
                item.to_dict() for item in self.incomplete_periods
            ],
        }


@dataclass(frozen=True)
class PortfolioValidationInput:
    manifest: PortfolioValidationManifest
    rebalances: tuple[PortfolioRebalance, ...]
    returns: tuple[AssetPeriodReturn, ...]
    schema_version: int = INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != INPUT_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version deve ser {INPUT_SCHEMA_VERSION}."
            )
        if not isinstance(self.manifest, PortfolioValidationManifest):
            raise TypeError("manifest exige PortfolioValidationManifest.")
        if not self.rebalances:
            raise ValueError("rebalances não pode ser vazio.")
        if not all(isinstance(item, PortfolioRebalance) for item in self.rebalances):
            raise TypeError("rebalances exige PortfolioRebalance.")
        if not all(isinstance(item, AssetPeriodReturn) for item in self.returns):
            raise TypeError("returns exige AssetPeriodReturn.")
        object.__setattr__(self, "schema_version", INPUT_SCHEMA_VERSION)
        object.__setattr__(self, "rebalances", tuple(self.rebalances))
        object.__setattr__(self, "returns", tuple(self.returns))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PortfolioValidationInput":
        if not isinstance(data, Mapping):
            raise TypeError("O input de validação deve ser um objeto.")
        schema_version = data.get("schema_version", 0)
        raw_rebalances = data.get("rebalances")
        raw_returns = data.get("returns")
        if not isinstance(raw_rebalances, list):
            raise TypeError("rebalances deve ser uma lista.")
        if not isinstance(raw_returns, list):
            raise TypeError("returns deve ser uma lista.")
        return cls(
            schema_version=schema_version,
            manifest=PortfolioValidationManifest.from_dict(data.get("manifest")),
            rebalances=tuple(
                PortfolioRebalance.from_dict(item) for item in raw_rebalances
            ),
            returns=tuple(
                AssetPeriodReturn.from_dict(item) for item in raw_returns
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest": self.manifest.to_dict(),
            "rebalances": [item.to_dict() for item in self.rebalances],
            "returns": [item.to_dict() for item in self.returns],
        }


def load_portfolio_validation_policy(
    path: str | Path,
) -> PortfolioValidationPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return PortfolioValidationPolicy.from_dict(data)


def load_portfolio_validation_input(
    path: str | Path,
) -> PortfolioValidationInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioValidationInput.from_dict(data)


def _turnover(
    previous_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
) -> float:
    symbols = set(previous_weights) | set(target_weights)
    return 0.5 * sum(
        abs(target_weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
        for symbol in symbols
    )


def _cumulative(returns: Iterable[float]) -> float:
    nav = 1.0
    for period_return in returns:
        nav *= 1.0 + period_return
    return nav - 1.0


def _maximum_drawdown(returns: Iterable[float]) -> float:
    nav = peak = 1.0
    maximum = 0.0
    for period_return in returns:
        nav *= 1.0 + period_return
        peak = max(peak, nav)
        maximum = min(maximum, nav / peak - 1.0)
    return maximum


def _summary(
    periods: tuple[ValidationPeriod, ...],
    policy: PortfolioValidationPolicy,
) -> ValidationSummary:
    net_returns = [item.net_return for item in periods]
    benchmark_returns = [item.benchmark_return for item in periods]
    total_return = _cumulative(net_returns)
    benchmark_total = _cumulative(benchmark_returns)
    annualized = (
        -1.0
        if total_return <= -1
        else (1.0 + total_return) ** (policy.periods_per_year / len(periods)) - 1.0
    )
    volatility = (
        statistics.stdev(net_returns) * math.sqrt(policy.periods_per_year)
        if len(net_returns) > 1
        else 0.0
    )
    relative = (
        None
        if benchmark_total <= -1
        else (1.0 + total_return) / (1.0 + benchmark_total) - 1.0
    )
    sector_hhi_values = [
        item.sector_hhi for item in periods if item.sector_hhi is not None
    ]
    maximum_sector_values = [
        item.maximum_sector_weight
        for item in periods
        if item.maximum_sector_weight is not None
    ]
    complete_sector_coverage = len(sector_hhi_values) == len(periods)
    return ValidationSummary(
        total_return=_rounded(total_return),
        benchmark_total_return=_rounded(benchmark_total),
        relative_return=_rounded(relative) if relative is not None else None,
        annualized_return=_rounded(annualized),
        annualized_volatility=_rounded(volatility),
        maximum_drawdown=_rounded(_maximum_drawdown(net_returns)),
        average_turnover=_rounded(statistics.mean(item.turnover for item in periods)),
        total_estimated_cost=_rounded(sum(item.estimated_cost for item in periods)),
        average_position_hhi=_rounded(
            statistics.mean(item.position_hhi for item in periods)
        ),
        maximum_position_weight=_rounded(
            max(item.maximum_position_weight for item in periods)
        ),
        average_sector_hhi=(
            _rounded(statistics.mean(sector_hhi_values))
            if complete_sector_coverage
            else None
        ),
        maximum_sector_weight=(
            _rounded(max(maximum_sector_values))
            if complete_sector_coverage
            else None
        ),
    )


def validate_portfolio(
    rebalances: Iterable[PortfolioRebalance],
    returns: Iterable[AssetPeriodReturn],
    policy: PortfolioValidationPolicy,
    manifest: PortfolioValidationManifest,
    *,
    generated_at: datetime | None = None,
) -> PortfolioValidationReport:
    if not isinstance(policy, PortfolioValidationPolicy):
        raise TypeError("validate_portfolio exige PortfolioValidationPolicy.")
    if not isinstance(manifest, PortfolioValidationManifest):
        raise TypeError("validate_portfolio exige PortfolioValidationManifest.")
    rebalance_rows = tuple(rebalances)
    if not rebalance_rows:
        raise ValueError("rebalances não pode ser vazio.")
    if not all(isinstance(item, PortfolioRebalance) for item in rebalance_rows):
        raise TypeError("rebalances exige PortfolioRebalance.")
    ordered_rebalances = tuple(
        sorted(rebalance_rows, key=lambda item: item.effective_on)
    )
    dates = [item.effective_on for item in ordered_rebalances]
    if len(dates) != len(set(dates)):
        raise ValueError("Só pode existir um rebalanceamento por data.")

    return_rows = tuple(returns)
    if not all(isinstance(item, AssetPeriodReturn) for item in return_rows):
        raise TypeError("returns exige AssetPeriodReturn.")
    identities = [item.identity for item in return_rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Retorno duplicado para símbolo e período.")
    by_period: dict[tuple[date, date], dict[str, AssetPeriodReturn]] = {}
    for item in return_rows:
        by_period.setdefault((item.period_start, item.period_end), {})[item.symbol] = item

    starts = {item.effective_on for item in ordered_rebalances}
    if any(period_start not in starts for period_start, _ in by_period):
        raise ValueError("Todo período de retorno deve começar num rebalanceamento.")

    periods: list[ValidationPeriod] = []
    incomplete: list[IncompleteValidationPeriod] = []
    previous_weights: dict[str, float] | None = {CASH_SYMBOL: 1.0}
    previous_end: date | None = None

    for rebalance in ordered_rebalances:
        matching = [key for key in by_period if key[0] == rebalance.effective_on]
        if len(matching) != 1:
            raise ValueError("Cada rebalanceamento exige exatamente um período.")
        period_start, period_end = matching[0]
        if previous_end is not None and period_start != previous_end:
            raise ValueError("Períodos de validação devem ser consecutivos.")
        previous_end = period_end
        rows = by_period[(period_start, period_end)]
        reasons: list[str] = []
        if previous_weights is None:
            reasons.append("PRIOR_PERIOD_INCOMPLETE")

        expected = set(rebalance.target_weights)
        for symbol in sorted(expected):
            item = rows.get(symbol)
            if item is None:
                reasons.append(f"MISSING_RETURN:{symbol}")
                continue
            if item.terminal_treatment == "unresolved":
                reasons.append(f"UNRESOLVED_DELISTING:{symbol}")
            if item.currency != policy.base_currency:
                reasons.append(f"RETURN_CURRENCY_MISMATCH:{symbol}")
            if item.dividends_included != policy.dividends_included:
                reasons.append(f"DIVIDEND_TREATMENT_MISMATCH:{symbol}")

        benchmark = rows.get(policy.benchmark_symbol)
        if benchmark is None:
            reasons.append(f"MISSING_BENCHMARK_RETURN:{policy.benchmark_symbol}")
        else:
            if benchmark.total_return is None:
                reasons.append(f"UNRESOLVED_BENCHMARK:{policy.benchmark_symbol}")
            if benchmark.currency != policy.base_currency:
                reasons.append("BENCHMARK_CURRENCY_MISMATCH")
            if benchmark.dividends_included != policy.dividends_included:
                reasons.append("BENCHMARK_DIVIDEND_TREATMENT_MISMATCH")

        if reasons:
            incomplete.append(
                IncompleteValidationPeriod(
                    period_start, period_end, tuple(sorted(set(reasons)))
                )
            )
            previous_weights = None
            continue

        assert previous_weights is not None
        target = dict(rebalance.target_weights)
        target[CASH_SYMBOL] = rebalance.cash_weight
        turnover = _turnover(previous_weights, target)
        asset_returns = {
            symbol: float(rows[symbol].total_return)
            for symbol in rebalance.target_weights
        }
        gross_return = sum(
            rebalance.target_weights[symbol] * asset_returns[symbol]
            for symbol in rebalance.target_weights
        )
        estimated_cost = turnover * policy.transaction_cost_rate
        # O custo é retirado proporcionalmente do capital no rebalanceamento,
        # antes do retorno do período. Isso preserva o piso econômico de -100%
        # mesmo quando uma posição termina sem valor.
        net_return = (1.0 - estimated_cost) * (1.0 + gross_return) - 1.0
        benchmark_return = float(benchmark.total_return)
        position_weights = tuple(rebalance.target_weights.values())
        sector_weights: dict[str, float] = {}
        sector_contributions: dict[str, float] = {}
        if len(rebalance.sectors) == len(rebalance.target_weights):
            for symbol, weight in rebalance.target_weights.items():
                sector = rebalance.sectors[symbol]
                sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
                sector_contributions[sector] = sector_contributions.get(
                    sector, 0.0
                ) + weight * asset_returns[symbol]
        factor_exposures: dict[str, float] = {}
        if len(rebalance.factor_exposures) == len(rebalance.target_weights):
            for symbol, weight in rebalance.target_weights.items():
                for factor, exposure in rebalance.factor_exposures[symbol].items():
                    factor_exposures[factor] = (
                        factor_exposures.get(factor, 0.0) + weight * exposure
                    )
        periods.append(
            ValidationPeriod(
                period_start=period_start,
                period_end=period_end,
                gross_return=_rounded(gross_return),
                net_return=_rounded(net_return),
                benchmark_return=_rounded(benchmark_return),
                turnover=_rounded(turnover),
                estimated_cost=_rounded(estimated_cost),
                position_hhi=_rounded(sum(weight * weight for weight in position_weights)),
                maximum_position_weight=_rounded(max(position_weights)),
                sector_hhi=(
                    _rounded(sum(weight * weight for weight in sector_weights.values()))
                    if sector_weights
                    else None
                ),
                maximum_sector_weight=(
                    _rounded(max(sector_weights.values()))
                    if sector_weights
                    else None
                ),
                sector_contributions=(
                    {
                        sector: _rounded(value)
                        for sector, value in sorted(sector_contributions.items())
                    }
                    if sector_contributions
                    else None
                ),
                factor_exposures=(
                    {
                        factor: _rounded(value)
                        for factor, value in sorted(factor_exposures.items())
                    }
                    if factor_exposures
                    else None
                ),
                terminal_events=tuple(
                    f"{symbol}:{rows[symbol].terminal_treatment}"
                    for symbol in sorted(rebalance.target_weights)
                    if rows[symbol].terminal_treatment is not None
                ),
            )
        )

        gross_value = 1.0 + gross_return
        if gross_value <= 0:
            previous_weights = None
        else:
            previous_weights = {
                symbol: target[symbol]
                * (1.0 + (asset_returns[symbol] if symbol != CASH_SYMBOL else 0.0))
                / gross_value
                for symbol in target
            }

    period_tuple = tuple(periods)
    incomplete_tuple = tuple(incomplete)
    summary = (
        _summary(period_tuple, policy)
        if period_tuple and not incomplete_tuple
        else None
    )
    return PortfolioValidationReport(
        manifest=manifest,
        policy=policy,
        periods=period_tuple,
        incomplete_periods=incomplete_tuple,
        summary=summary,
        return_sources=tuple(sorted({item.source for item in return_rows})),
        generated_at=generated_at or datetime.now(timezone.utc),
    )


def write_portfolio_validation_report(
    report: PortfolioValidationReport,
    path: str | Path,
) -> Path:
    if not isinstance(report, PortfolioValidationReport):
        raise TypeError("report deve ser PortfolioValidationReport.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def run_portfolio_validation(
    *,
    input_path: str | Path,
    policy_path: str | Path,
    output_path: str | Path,
    generated_at: datetime | None = None,
) -> PortfolioValidationReport:
    validation_input = load_portfolio_validation_input(input_path)
    report = validate_portfolio(
        validation_input.rebalances,
        validation_input.returns,
        load_portfolio_validation_policy(policy_path),
        validation_input.manifest,
        generated_at=generated_at,
    )
    write_portfolio_validation_report(report, output_path)
    return report


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Valida uma sequência explícita de carteiras e retornos, sem "
            "buscar dados de mercado."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--policy",
        default=str(
            Path(__file__).resolve().parents[1]
            / "config"
            / "portfolio_validation.yaml"
        ),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_portfolio_validation(
        input_path=args.input,
        policy_path=args.policy,
        output_path=args.output,
    )
    print(
        f"Validação de portfólio: {report.to_dict()['status']}; "
        f"{len(report.periods)} período(s) completo(s); "
        f"{len(report.incomplete_periods)} incompleto(s)."
    )


if __name__ == "__main__":
    main()

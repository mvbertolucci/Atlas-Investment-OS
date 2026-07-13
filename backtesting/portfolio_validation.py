from __future__ import annotations

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
class PortfolioRebalance:
    effective_on: date | datetime | str
    target_weights: Mapping[str, float]

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
        object.__setattr__(self, "effective_on", effective_on)
        object.__setattr__(self, "target_weights", dict(sorted(weights.items())))

    @property
    def cash_weight(self) -> float:
        return max(0.0, 1.0 - sum(self.target_weights.values()))


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

    def to_dict(self) -> dict[str, float | None]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PortfolioValidationReport:
    policy: PortfolioValidationPolicy
    periods: tuple[ValidationPeriod, ...]
    incomplete_periods: tuple[IncompleteValidationPeriod, ...]
    summary: ValidationSummary | None
    return_sources: tuple[str, ...] = ()
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "advisory_only": True,
            "performance_disclaimer": PERFORMANCE_DISCLAIMER,
            "status": "complete" if self.summary is not None else "incomplete",
            "policy": self.policy.to_dict(),
            "return_sources": list(self.return_sources),
            "summary": self.summary.to_dict() if self.summary else None,
            "periods": [item.to_dict() for item in self.periods],
            "incomplete_periods": [
                item.to_dict() for item in self.incomplete_periods
            ],
        }


def load_portfolio_validation_policy(
    path: str | Path,
) -> PortfolioValidationPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return PortfolioValidationPolicy.from_dict(data)


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
    )


def validate_portfolio(
    rebalances: Iterable[PortfolioRebalance],
    returns: Iterable[AssetPeriodReturn],
    policy: PortfolioValidationPolicy,
    *,
    generated_at: datetime | None = None,
) -> PortfolioValidationReport:
    if not isinstance(policy, PortfolioValidationPolicy):
        raise TypeError("validate_portfolio exige PortfolioValidationPolicy.")
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

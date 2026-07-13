from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from backtesting.historical_portfolio import HistoricalTargetPortfolio
from backtesting.portfolio_validation import PortfolioRebalance


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


def _utc_timestamp(value: datetime | str, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name} deve ser timestamp ISO-8601 com fuso."
            ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} exige fuso horário explícito.")
    return value.astimezone(timezone.utc)


def _positive_number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser numérico e positivo.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field_name} deve ser numérico e positivo.")
    return number


@dataclass(frozen=True)
class HistoricalExecutionPolicy:
    name: str
    execution_timing: str = "next_session_open"
    max_wait_calendar_days: int = 7
    base_currency: str = "USD"
    require_all_prices: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name"))
        if self.execution_timing != "next_session_open":
            raise ValueError("Somente execution_timing=next_session_open é suportado.")
        wait = int(self.max_wait_calendar_days)
        if wait <= 0:
            raise ValueError("max_wait_calendar_days deve ser positivo.")
        object.__setattr__(self, "max_wait_calendar_days", wait)
        object.__setattr__(
            self,
            "base_currency",
            _text(self.base_currency, "base_currency").upper(),
        )
        if self.require_all_prices is not True:
            raise ValueError("require_all_prices deve permanecer true.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HistoricalExecutionPolicy":
        if not isinstance(data, Mapping):
            raise TypeError("A política de execução deve ser um objeto.")
        return cls(**dict(data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "execution_timing": self.execution_timing,
            "max_wait_calendar_days": self.max_wait_calendar_days,
            "base_currency": self.base_currency,
            "require_all_prices": self.require_all_prices,
        }


@dataclass(frozen=True)
class TradingSession:
    session_date: date | datetime | str
    opens_at: datetime | str
    venue: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_date", _date(self.session_date, "session_date")
        )
        object.__setattr__(self, "opens_at", _utc_timestamp(self.opens_at, "opens_at"))
        object.__setattr__(self, "venue", _text(self.venue, "venue"))
        object.__setattr__(self, "source", _text(self.source, "source"))

    def to_dict(self) -> dict[str, str]:
        return {
            "session_date": self.session_date.isoformat(),
            "opens_at": self.opens_at.isoformat(),
            "venue": self.venue,
            "source": self.source,
        }


@dataclass(frozen=True)
class ExecutionPriceObservation:
    symbol: str
    observed_at: datetime | str
    price: float
    currency: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol").upper())
        object.__setattr__(
            self,
            "observed_at",
            _utc_timestamp(self.observed_at, "observed_at"),
        )
        object.__setattr__(self, "price", _positive_number(self.price, "price"))
        object.__setattr__(
            self, "currency", _text(self.currency, "currency").upper()
        )
        object.__setattr__(self, "source", _text(self.source, "source"))

    @property
    def identity(self) -> tuple[str, datetime]:
        return (self.symbol, self.observed_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "observed_at": self.observed_at.isoformat(),
            "price": self.price,
            "currency": self.currency,
            "source": self.source,
        }


@dataclass(frozen=True)
class HistoricalExecutionResult:
    target: HistoricalTargetPortfolio
    policy: HistoricalExecutionPolicy
    session: TradingSession | None
    rebalance: PortfolioRebalance | None
    execution_prices: Mapping[str, ExecutionPriceObservation]
    failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        prices = dict(sorted(self.execution_prices.items()))
        if self.failure_reasons and self.rebalance is not None:
            raise ValueError("Execução com falha não pode conter rebalanceamento.")
        if not self.failure_reasons and self.rebalance is None:
            raise ValueError("Execução sem falha exige rebalanceamento.")
        object.__setattr__(self, "execution_prices", prices)
        object.__setattr__(self, "failure_reasons", tuple(self.failure_reasons))

    @property
    def executed(self) -> bool:
        return self.rebalance is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_at": self.target.decision_at.isoformat(),
            "executed": self.executed,
            "failure_reasons": list(self.failure_reasons),
            "policy": self.policy.to_dict(),
            "session": self.session.to_dict() if self.session else None,
            "rebalance": self.rebalance.to_dict() if self.rebalance else None,
            "execution_prices": {
                symbol: observation.to_dict()
                for symbol, observation in self.execution_prices.items()
            },
        }


def load_historical_execution_policy(
    path: str | Path,
) -> HistoricalExecutionPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return HistoricalExecutionPolicy.from_dict(data)


def execute_historical_target(
    target: HistoricalTargetPortfolio,
    sessions: Iterable[TradingSession],
    prices: Iterable[ExecutionPriceObservation],
    policy: HistoricalExecutionPolicy,
) -> HistoricalExecutionResult:
    if not isinstance(target, HistoricalTargetPortfolio):
        raise TypeError("target exige HistoricalTargetPortfolio.")
    if not isinstance(policy, HistoricalExecutionPolicy):
        raise TypeError("policy exige HistoricalExecutionPolicy.")
    if not target.constructed:
        return HistoricalExecutionResult(
            target=target,
            policy=policy,
            session=None,
            rebalance=None,
            execution_prices={},
            failure_reasons=(
                f"TARGET_NOT_CONSTRUCTED:{target.construction_error}",
            ),
        )

    session_rows = tuple(sessions)
    if not all(isinstance(item, TradingSession) for item in session_rows):
        raise TypeError("sessions exige TradingSession.")
    opens = [item.opens_at for item in session_rows]
    if len(opens) != len(set(opens)):
        raise ValueError("Sessão duplicada para opens_at.")
    future_sessions = sorted(
        (item for item in session_rows if item.opens_at > target.decision_at),
        key=lambda item: item.opens_at,
    )
    if not future_sessions:
        return HistoricalExecutionResult(
            target, policy, None, None, {}, ("NO_SESSION_AFTER_DECISION",)
        )
    session = future_sessions[0]
    if session.opens_at - target.decision_at > timedelta(
        days=policy.max_wait_calendar_days
    ):
        return HistoricalExecutionResult(
            target,
            policy,
            session,
            None,
            {},
            ("SESSION_OUTSIDE_MAX_WAIT",),
        )

    price_rows = tuple(prices)
    if not all(isinstance(item, ExecutionPriceObservation) for item in price_rows):
        raise TypeError("prices exige ExecutionPriceObservation.")
    identities = [item.identity for item in price_rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Preço de execução duplicado para símbolo e timestamp.")
    at_open = {
        item.symbol: item
        for item in price_rows
        if item.observed_at == session.opens_at
    }
    selected: dict[str, ExecutionPriceObservation] = {}
    reasons: list[str] = []
    for symbol in target.target_weights:
        observation = at_open.get(symbol)
        if observation is None:
            reasons.append(f"MISSING_EXECUTION_PRICE:{symbol}")
            continue
        if observation.currency != policy.base_currency:
            reasons.append(f"EXECUTION_CURRENCY_MISMATCH:{symbol}")
            continue
        selected[symbol] = observation
    if reasons:
        return HistoricalExecutionResult(
            target,
            policy,
            session,
            None,
            selected,
            tuple(sorted(reasons)),
        )

    return HistoricalExecutionResult(
        target=target,
        policy=policy,
        session=session,
        rebalance=target.to_rebalance(session.session_date),
        execution_prices=selected,
        failure_reasons=(),
    )


def execute_historical_targets(
    targets: Iterable[HistoricalTargetPortfolio],
    sessions: Iterable[TradingSession],
    prices: Iterable[ExecutionPriceObservation],
    policy: HistoricalExecutionPolicy,
) -> tuple[HistoricalExecutionResult, ...]:
    target_rows = tuple(targets)
    if not target_rows:
        raise ValueError("targets não pode ser vazio.")
    session_rows = tuple(sessions)
    price_rows = tuple(prices)
    return tuple(
        execute_historical_target(target, session_rows, price_rows, policy)
        for target in target_rows
    )

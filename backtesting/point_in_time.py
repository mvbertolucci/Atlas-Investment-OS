from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable


DELISTING_TREATMENTS = frozenset(
    {"cash", "zero", "successor", "unresolved"}
)


def _text(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} não pode ser vazio.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} não pode ser vazio.")
    return text


def _symbol(value: Any) -> str:
    return _text(value, "symbol").upper()


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
                f"{field_name} deve ser um timestamp ISO-8601 com fuso horário."
            ) from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} exige fuso horário explícito.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class HistoricalObservation:
    """One immutable, source-versioned value known at a precise time."""

    symbol: str
    field_name: str
    value: Any
    observed_on: date | datetime | str
    available_at: datetime | str
    source: str
    revision_id: str

    def __post_init__(self) -> None:
        observed_on = _date(self.observed_on, "observed_on")
        available_at = _utc_timestamp(self.available_at, "available_at")
        if available_at.date() < observed_on:
            raise ValueError("available_at não pode anteceder observed_on.")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        object.__setattr__(self, "field_name", _text(self.field_name, "field_name"))
        object.__setattr__(self, "observed_on", observed_on)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "revision_id", _text(self.revision_id, "revision_id"))

    @property
    def identity(self) -> tuple[str, str, date, str]:
        return (self.symbol, self.field_name, self.observed_on, self.revision_id)

    def is_available(self, decision_at: datetime | str) -> bool:
        cutoff = _utc_timestamp(decision_at, "decision_at")
        return self.observed_on <= cutoff.date() and self.available_at <= cutoff


@dataclass(frozen=True)
class UniverseMembership:
    """Half-open constituent interval, retained for additions and removals."""

    symbol: str
    effective_from: date | datetime | str
    known_at: datetime | str
    source: str
    effective_to: date | datetime | str | None = None

    def __post_init__(self) -> None:
        effective_from = _date(self.effective_from, "effective_from")
        effective_to = (
            _date(self.effective_to, "effective_to")
            if self.effective_to is not None
            else None
        )
        if effective_to is not None and effective_to <= effective_from:
            raise ValueError("effective_to deve ser posterior a effective_from.")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        object.__setattr__(self, "effective_from", effective_from)
        object.__setattr__(self, "effective_to", effective_to)
        object.__setattr__(self, "known_at", _utc_timestamp(self.known_at, "known_at"))
        object.__setattr__(self, "source", _text(self.source, "source"))

    def is_active(self, decision_at: datetime | str) -> bool:
        cutoff = _utc_timestamp(decision_at, "decision_at")
        return (
            self.known_at <= cutoff
            and self.effective_from <= cutoff.date()
            and (self.effective_to is None or cutoff.date() < self.effective_to)
        )


@dataclass(frozen=True)
class StockSplitRecord:
    """Effective split event used only to keep price/share units consistent."""

    symbol: str
    effective_on: date | datetime | str
    ratio: float
    known_at: datetime | str
    source: str

    def __post_init__(self) -> None:
        effective_on = _date(self.effective_on, "effective_on")
        try:
            ratio = float(self.ratio)
        except (TypeError, ValueError) as exc:
            raise ValueError("ratio de split deve ser numérico e positivo.") from exc
        if ratio <= 0 or ratio != ratio:
            raise ValueError("ratio de split deve ser numérico e positivo.")
        if ratio == 1:
            raise ValueError("ratio de split não pode ser 1.")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        object.__setattr__(self, "effective_on", effective_on)
        object.__setattr__(self, "ratio", ratio)
        object.__setattr__(self, "known_at", _utc_timestamp(self.known_at, "known_at"))
        object.__setattr__(self, "source", _text(self.source, "source"))

    @property
    def identity(self) -> tuple[str, date]:
        return (self.symbol, self.effective_on)

    def is_known_and_effective(self, decision_at: datetime | str) -> bool:
        cutoff = _utc_timestamp(decision_at, "decision_at")
        return self.known_at <= cutoff and self.effective_on <= cutoff.date()


@dataclass(frozen=True)
class DelistingRecord:
    """Explicit terminal event and required return treatment."""

    symbol: str
    effective_on: date | datetime | str
    known_at: datetime | str
    last_trade_on: date | datetime | str
    return_treatment: str
    source: str
    cash_proceeds: float | None = None
    successor_symbol: str | None = None

    def __post_init__(self) -> None:
        effective_on = _date(self.effective_on, "effective_on")
        last_trade_on = _date(self.last_trade_on, "last_trade_on")
        if last_trade_on > effective_on:
            raise ValueError("last_trade_on não pode suceder effective_on.")
        treatment = _text(self.return_treatment, "return_treatment").lower()
        if treatment not in DELISTING_TREATMENTS:
            raise ValueError("return_treatment de delistagem não suportado.")
        successor = (
            _symbol(self.successor_symbol) if self.successor_symbol is not None else None
        )
        if treatment == "successor" and not successor:
            raise ValueError("Delistagem successor exige successor_symbol.")
        if treatment != "successor" and successor:
            raise ValueError("successor_symbol só é válido para treatment successor.")
        proceeds = self.cash_proceeds
        if proceeds is not None:
            try:
                proceeds = float(proceeds)
            except (TypeError, ValueError) as exc:
                raise ValueError("cash_proceeds deve ser numérico e não negativo.") from exc
            if proceeds < 0 or proceeds != proceeds:
                raise ValueError("cash_proceeds deve ser numérico e não negativo.")
        if treatment == "cash" and proceeds is None:
            raise ValueError("Delistagem cash exige cash_proceeds.")
        if treatment != "cash" and proceeds is not None:
            raise ValueError("cash_proceeds só é válido para treatment cash.")
        object.__setattr__(self, "symbol", _symbol(self.symbol))
        object.__setattr__(self, "effective_on", effective_on)
        object.__setattr__(self, "known_at", _utc_timestamp(self.known_at, "known_at"))
        object.__setattr__(self, "last_trade_on", last_trade_on)
        object.__setattr__(self, "return_treatment", treatment)
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "cash_proceeds", proceeds)
        object.__setattr__(self, "successor_symbol", successor)

    def is_known_and_effective(self, decision_at: datetime | str) -> bool:
        cutoff = _utc_timestamp(decision_at, "decision_at")
        return self.known_at <= cutoff and self.effective_on <= cutoff.date()


@dataclass(frozen=True)
class AsOfSnapshot:
    decision_at: datetime
    members: tuple[str, ...]
    observations: tuple[HistoricalObservation, ...]
    delistings: tuple[DelistingRecord, ...]
    splits: tuple[StockSplitRecord, ...] = ()

    def observation(
        self, symbol: str, field_name: str
    ) -> HistoricalObservation:
        key = (_symbol(symbol), _text(field_name, "field_name"))
        for observation in self.observations:
            if (observation.symbol, observation.field_name) == key:
                return observation
        raise KeyError(key)

    def value(self, symbol: str, field_name: str) -> Any:
        return self.observation(symbol, field_name).value


@dataclass(frozen=True)
class PointInTimeDataset:
    observations: tuple[HistoricalObservation, ...] = ()
    memberships: tuple[UniverseMembership, ...] = ()
    delistings: tuple[DelistingRecord, ...] = ()
    splits: tuple[StockSplitRecord, ...] = ()

    def __post_init__(self) -> None:
        observations = tuple(self.observations)
        memberships = tuple(self.memberships)
        delistings = tuple(self.delistings)
        splits = tuple(self.splits)
        identities: set[tuple[str, str, date, str]] = set()
        for observation in observations:
            if not isinstance(observation, HistoricalObservation):
                raise TypeError("observations exige HistoricalObservation.")
            if observation.identity in identities:
                raise ValueError("Observação point-in-time duplicada.")
            identities.add(observation.identity)
        self._validate_memberships(memberships)
        delisting_symbols: set[str] = set()
        for record in delistings:
            if not isinstance(record, DelistingRecord):
                raise TypeError("delistings exige DelistingRecord.")
            if record.symbol in delisting_symbols:
                raise ValueError("Delistagem duplicada para o símbolo.")
            delisting_symbols.add(record.symbol)
        split_identities: set[tuple[str, date]] = set()
        for record in splits:
            if not isinstance(record, StockSplitRecord):
                raise TypeError("splits exige StockSplitRecord.")
            if record.identity in split_identities:
                raise ValueError("Split duplicado para símbolo e data.")
            split_identities.add(record.identity)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "memberships", memberships)
        object.__setattr__(self, "delistings", delistings)
        object.__setattr__(self, "splits", splits)

    @staticmethod
    def _validate_memberships(memberships: tuple[UniverseMembership, ...]) -> None:
        by_symbol: dict[str, list[UniverseMembership]] = {}
        for membership in memberships:
            if not isinstance(membership, UniverseMembership):
                raise TypeError("memberships exige UniverseMembership.")
            by_symbol.setdefault(membership.symbol, []).append(membership)
        for intervals in by_symbol.values():
            ordered = sorted(intervals, key=lambda item: item.effective_from)
            for previous, current in zip(ordered, ordered[1:]):
                if previous.effective_to is None or current.effective_from < previous.effective_to:
                    raise ValueError("Intervalos de constituição não podem se sobrepor.")

    def as_of(self, decision_at: datetime | str) -> AsOfSnapshot:
        cutoff = _utc_timestamp(decision_at, "decision_at")
        members = tuple(
            sorted(
                {
                    membership.symbol
                    for membership in self.memberships
                    if membership.is_active(cutoff)
                }
            )
        )
        latest: dict[tuple[str, str], HistoricalObservation] = {}
        for observation in self.observations:
            if not observation.is_available(cutoff):
                continue
            key = (observation.symbol, observation.field_name)
            candidate_key = (
                observation.observed_on,
                observation.available_at,
                observation.revision_id,
            )
            current = latest.get(key)
            if current is None or candidate_key > (
                current.observed_on,
                current.available_at,
                current.revision_id,
            ):
                latest[key] = observation
        available = tuple(latest[key] for key in sorted(latest))
        delistings = tuple(
            sorted(
                (
                    record
                    for record in self.delistings
                    if record.is_known_and_effective(cutoff)
                ),
                key=lambda item: (item.effective_on, item.symbol),
            )
        )
        splits = tuple(
            sorted(
                (
                    record
                    for record in self.splits
                    if record.is_known_and_effective(cutoff)
                ),
                key=lambda item: (item.effective_on, item.symbol),
            )
        )
        return AsOfSnapshot(cutoff, members, available, delistings, splits)

    @classmethod
    def from_iterables(
        cls,
        *,
        observations: Iterable[HistoricalObservation] = (),
        memberships: Iterable[UniverseMembership] = (),
        delistings: Iterable[DelistingRecord] = (),
        splits: Iterable[StockSplitRecord] = (),
    ) -> "PointInTimeDataset":
        return cls(
            tuple(observations),
            tuple(memberships),
            tuple(delistings),
            tuple(splits),
        )

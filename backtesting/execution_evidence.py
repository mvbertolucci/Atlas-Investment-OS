from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from backtesting.historical_execution import (
    ExecutionPriceObservation,
    TradingSession,
)
from backtesting.price_history import extract_split_events


EXECUTION_EVIDENCE_SCHEMA_VERSION = 1
US_MARKET_TIMEZONE = ZoneInfo("America/New_York")
REGULAR_SESSION_OPEN = time(9, 30)


def _text(value: Any, field_name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field_name} não pode ser vazio.")
    return text


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


def _row_date(timestamp: Any) -> date:
    return (
        timestamp.date()
        if hasattr(timestamp, "date")
        else date.fromisoformat(str(timestamp))
    )


def regular_us_open_at(session_date: date | str) -> datetime:
    if isinstance(session_date, str):
        session_date = date.fromisoformat(session_date)
    return datetime.combine(
        session_date,
        REGULAR_SESSION_OPEN,
        tzinfo=US_MARKET_TIMEZONE,
    ).astimezone(timezone.utc)


def extract_observed_us_sessions(
    reference_history: pd.DataFrame,
    *,
    venue: str = "XNYS/XNAS",
    source: str = "yahoo_reference_daily_bars",
) -> tuple[TradingSession, ...]:
    """
    Uma sessão por barra diária válida do ativo-referência. Isto é evidência
    observada/proxy, não um calendário oficial de bolsa.
    """
    if not isinstance(reference_history, pd.DataFrame):
        raise TypeError("reference_history exige DataFrame.")
    if "Open" not in reference_history.columns:
        return ()
    session_dates = sorted(
        {
            _row_date(timestamp)
            for timestamp, value in reference_history["Open"].items()
            if not pd.isna(value)
        }
    )
    return tuple(
        TradingSession(
            session_date=session_date,
            opens_at=regular_us_open_at(session_date),
            venue=venue,
            source=source,
        )
        for session_date in session_dates
    )


def extract_opening_price_observations(
    symbol: str,
    price_history: pd.DataFrame,
    *,
    currency: str = "USD",
    source: str = "yahoo_daily_open",
) -> tuple[ExecutionPriceObservation, ...]:
    """
    Extrai `Open` em unidades as-traded. Assim como o `Close` já tratado pelo
    projeto, barras Yahoo antigas são normalizadas por splits futuros; cada
    abertura é multiplicada somente pelos eventos posteriores à sua sessão.
    """
    if not isinstance(price_history, pd.DataFrame):
        raise TypeError("price_history exige DataFrame.")
    if "Open" not in price_history.columns:
        return ()
    split_events = extract_split_events(price_history)
    observations: list[ExecutionPriceObservation] = []
    for timestamp, raw_open in price_history["Open"].items():
        if pd.isna(raw_open):
            continue
        session_date = _row_date(timestamp)
        future_split_factor = 1.0
        for effective_on, ratio in split_events:
            if effective_on > session_date:
                future_split_factor *= ratio
        observations.append(
            ExecutionPriceObservation(
                symbol=symbol,
                observed_at=regular_us_open_at(session_date),
                price=float(raw_open) * future_split_factor,
                currency=currency,
                source=source,
            )
        )
    return tuple(observations)


@dataclass(frozen=True)
class HistoricalExecutionEvidence:
    reference_symbol: str
    retrieved_at: datetime | str
    sessions: tuple[TradingSession, ...]
    prices: tuple[ExecutionPriceObservation, ...]
    schema_version: int = EXECUTION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != EXECUTION_EVIDENCE_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version deve ser {EXECUTION_EVIDENCE_SCHEMA_VERSION}."
            )
        session_rows = tuple(self.sessions)
        price_rows = tuple(self.prices)
        if not session_rows:
            raise ValueError("sessions não pode ser vazio.")
        if not price_rows:
            raise ValueError("prices não pode ser vazio.")
        if not all(isinstance(item, TradingSession) for item in session_rows):
            raise TypeError("sessions exige TradingSession.")
        if not all(isinstance(item, ExecutionPriceObservation) for item in price_rows):
            raise TypeError("prices exige ExecutionPriceObservation.")
        sessions = tuple(sorted(session_rows, key=lambda item: item.opens_at))
        prices = tuple(
            sorted(price_rows, key=lambda item: (item.observed_at, item.symbol))
        )
        opens = [item.opens_at for item in sessions]
        if len(opens) != len(set(opens)):
            raise ValueError("Sessão duplicada no artefato.")
        identities = [item.identity for item in prices]
        if len(identities) != len(set(identities)):
            raise ValueError("Preço duplicado no artefato.")
        open_set = set(opens)
        if any(item.observed_at not in open_set for item in prices):
            raise ValueError("Todo preço deve coincidir com uma sessão observada.")
        reference_symbol = _text(self.reference_symbol, "reference_symbol").upper()
        retrieved_at = _utc_timestamp(self.retrieved_at, "retrieved_at")
        if retrieved_at < max(
            *(item.opens_at for item in sessions),
            *(item.observed_at for item in prices),
        ):
            raise ValueError("retrieved_at não pode anteceder a evidência.")
        object.__setattr__(self, "reference_symbol", reference_symbol)
        object.__setattr__(self, "retrieved_at", retrieved_at)
        object.__setattr__(self, "sessions", sessions)
        object.__setattr__(self, "prices", prices)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest": {
                "reference_symbol": self.reference_symbol,
                "retrieved_at": self.retrieved_at.isoformat(),
                "calendar_method": "observed_reference_daily_bars",
                "session_timezone": "America/New_York",
                "regular_open_time": "09:30:00",
                "price_field": "Open",
                "split_policy": "restore_as_traded_from_future_split_events",
            },
            "sessions": [item.to_dict() for item in self.sessions],
            "prices": [item.to_dict() for item in self.prices],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HistoricalExecutionEvidence":
        if not isinstance(data, Mapping):
            raise TypeError("O artefato de execução deve ser um objeto.")
        manifest = data.get("manifest")
        if not isinstance(manifest, Mapping):
            raise TypeError("manifest deve ser um objeto.")
        expected = {
            "calendar_method": "observed_reference_daily_bars",
            "session_timezone": "America/New_York",
            "regular_open_time": "09:30:00",
            "price_field": "Open",
            "split_policy": "restore_as_traded_from_future_split_events",
        }
        for field_name, expected_value in expected.items():
            if manifest.get(field_name) != expected_value:
                raise ValueError(f"manifest.{field_name} incompatível.")
        raw_sessions = data.get("sessions")
        raw_prices = data.get("prices")
        if not isinstance(raw_sessions, list) or not isinstance(raw_prices, list):
            raise TypeError("sessions e prices devem ser listas.")
        return cls(
            schema_version=data.get("schema_version", 0),
            reference_symbol=manifest.get("reference_symbol"),
            retrieved_at=manifest.get("retrieved_at"),
            sessions=tuple(TradingSession(**item) for item in raw_sessions),
            prices=tuple(ExecutionPriceObservation(**item) for item in raw_prices),
        )


def build_execution_evidence(
    *,
    reference_symbol: str,
    reference_history: pd.DataFrame,
    symbol_histories: Mapping[str, pd.DataFrame],
    retrieved_at: datetime | str,
) -> HistoricalExecutionEvidence:
    sessions = extract_observed_us_sessions(
        reference_history,
        source=f"yahoo_reference_daily_bars:{reference_symbol.upper()}",
    )
    opens = {item.opens_at for item in sessions}
    prices = tuple(
        observation
        for symbol, history in sorted(symbol_histories.items())
        for observation in extract_opening_price_observations(symbol, history)
        if observation.observed_at in opens
    )
    return HistoricalExecutionEvidence(
        reference_symbol=reference_symbol,
        retrieved_at=retrieved_at,
        sessions=sessions,
        prices=prices,
    )


def write_execution_evidence(
    evidence: HistoricalExecutionEvidence,
    path: str | Path,
) -> Path:
    if not isinstance(evidence, HistoricalExecutionEvidence):
        raise TypeError("evidence exige HistoricalExecutionEvidence.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def load_execution_evidence(path: str | Path) -> HistoricalExecutionEvidence:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return HistoricalExecutionEvidence.from_dict(data)

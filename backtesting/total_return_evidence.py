from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from backtesting.point_in_time import DelistingRecord
from backtesting.portfolio_validation import AssetPeriodReturn

TOTAL_RETURN_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_SOURCE = "yahoo_daily_close_dividend_reinvested"


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


def _closes_by_date(price_history: pd.DataFrame) -> dict[date, float]:
    if "Close" not in price_history.columns:
        return {}
    closes: dict[date, float] = {}
    for timestamp, value in price_history["Close"].items():
        if pd.isna(value):
            continue
        closes[_row_date(timestamp)] = float(value)
    return closes


def _dividends_by_date(price_history: pd.DataFrame) -> dict[date, float]:
    if "Dividends" not in price_history.columns:
        return {}
    dividends: dict[date, float] = {}
    for timestamp, value in price_history["Dividends"].items():
        if pd.isna(value) or float(value) == 0.0:
            continue
        dividends[_row_date(timestamp)] = float(value)
    return dividends


def _delisting_for_period(
    symbol: str,
    period_start: date,
    period_end: date,
    delistings: Iterable[DelistingRecord],
) -> DelistingRecord | None:
    """
    A delisting only overrides the ONE period during which the symbol
    actually stopped trading (`last_trade_on` inside this period's window) --
    it never retroactively touches an earlier, already-resolved period.
    """
    for record in delistings:
        if record.symbol != symbol:
            continue
        if period_start <= record.last_trade_on < period_end:
            return record
    return None


def _dividend_reinvested_return(
    closes: Mapping[date, float],
    dividends: Mapping[date, float],
    period_start: date,
    period_end: date,
) -> tuple[float, date] | None:
    """
    Compounds day-over-day (Close[t] + Dividend[t]) / Close[t-1] across every
    bar strictly after `period_start` and up to (and including) `period_end`
    or the last bar actually observed in the window, whichever is earlier.

    Because both `Close` and `Dividends` come from the same Yahoo bars and
    neither is restored to as-traded units here (unlike
    `backtesting.price_history`, which needs actual per-share market_cap
    units), Yahoo's own retroactive split-continuity convention cancels out
    naturally in this day-over-day ratio -- no explicit split adjustment is
    needed for a return calculation, only for a per-share price level.

    Returns `(multiplier_minus_one, last_observed_date)` or `None` when
    `period_start` itself has no observed close (nothing to compound from --
    never invented).
    """
    if period_start not in closes:
        return None
    trading_dates = sorted(d for d in closes if period_start < d <= period_end)
    multiplier = 1.0
    previous_close = closes[period_start]
    last_observed = period_start
    for trading_date in trading_dates:
        close = closes[trading_date]
        dividend = dividends.get(trading_date, 0.0)
        multiplier *= (close + dividend) / previous_close
        previous_close = close
        last_observed = trading_date
    return multiplier - 1.0, last_observed


def extract_total_return_observations(
    symbol: str,
    price_history: pd.DataFrame,
    period_boundaries: Iterable[date | str],
    *,
    currency: str = "USD",
    source: str = DEFAULT_SOURCE,
    delistings: Iterable[DelistingRecord] = (),
) -> tuple[AssetPeriodReturn, ...]:
    """
    Pure, offline adapter: converts already-acquired Yahoo-shaped daily bars
    (`Close`, optionally `Dividends`) plus an explicit, caller-supplied
    sequence of period boundary dates into dividend-inclusive
    `AssetPeriodReturn` rows -- the exact type
    `backtesting.portfolio_validation.validate_portfolio` already consumes.
    Works identically for a portfolio holding or a benchmark symbol (e.g.
    SPY); there is no benchmark-specific code path.

    A period with no observed close on its start date is silently omitted
    (not invented as a zero or interpolated value) -- the validation runner
    already reports `MISSING_RETURN`/`MISSING_BENCHMARK_RETURN` for any
    period/symbol combination absent from `returns`.

    `delistings` (see `backtesting.point_in_time.DelistingRecord`) overrides
    the ordinary compounding result for the one period containing
    `last_trade_on`, following the PR-032 return-treatment vocabulary:

    - `zero`: `total_return` is forced to exactly -1.0, regardless of any
      compounding up to that point.
    - `cash`: the ordinary compounding multiplier up to the last observed
      trading day is combined with `cash_proceeds` (a per-share terminal
      settlement) in place of a next Close that will never arrive:
      `total_return = multiplier_to_last_trade * (cash_proceeds /
      close_at_last_trade) - 1`.
    - `successor`: this single-symbol adapter has no evidence of the
      successor security's own value, so it is deliberately reported as
      `unresolved` (`total_return=None`) rather than inventing one --
      resolving a successor's realized return needs that security's own
      price evidence, a separate, later input.
    - `unresolved`: passed through as `unresolved`/`None` unchanged.
    """
    symbol = _text(symbol, "symbol").upper()
    if not isinstance(price_history, pd.DataFrame):
        raise TypeError("price_history exige DataFrame.")
    boundaries = sorted({_row_date(item) for item in period_boundaries})
    if len(boundaries) < 2:
        return ()

    closes = _closes_by_date(price_history)
    dividends = _dividends_by_date(price_history)
    delisting_rows = tuple(delistings)

    observations: list[AssetPeriodReturn] = []
    for period_start, period_end in zip(boundaries, boundaries[1:]):
        delisting = _delisting_for_period(
            symbol, period_start, period_end, delisting_rows
        )
        if delisting is not None and delisting.return_treatment == "unresolved":
            observations.append(
                AssetPeriodReturn(
                    symbol=symbol,
                    period_start=period_start,
                    period_end=period_end,
                    total_return=None,
                    source=delisting.source,
                    currency=currency,
                    dividends_included=True,
                    terminal_treatment="unresolved",
                )
            )
            continue
        if delisting is not None and delisting.return_treatment == "successor":
            observations.append(
                AssetPeriodReturn(
                    symbol=symbol,
                    period_start=period_start,
                    period_end=period_end,
                    total_return=None,
                    source=delisting.source,
                    currency=currency,
                    dividends_included=True,
                    terminal_treatment="unresolved",
                )
            )
            continue

        result = _dividend_reinvested_return(
            closes,
            dividends,
            period_start,
            period_end if delisting is None else delisting.last_trade_on,
        )
        if result is None:
            continue
        multiplier_minus_one, last_observed = result

        if delisting is not None and delisting.return_treatment == "zero":
            observations.append(
                AssetPeriodReturn(
                    symbol=symbol,
                    period_start=period_start,
                    period_end=period_end,
                    total_return=-1.0,
                    source=delisting.source,
                    currency=currency,
                    dividends_included=True,
                    terminal_treatment="zero",
                )
            )
            continue

        if delisting is not None and delisting.return_treatment == "cash":
            close_at_last_trade = closes.get(last_observed)
            if close_at_last_trade is None or close_at_last_trade <= 0:
                observations.append(
                    AssetPeriodReturn(
                        symbol=symbol,
                        period_start=period_start,
                        period_end=period_end,
                        total_return=None,
                        source=delisting.source,
                        currency=currency,
                        dividends_included=True,
                        terminal_treatment="unresolved",
                    )
                )
                continue
            total_return = (1.0 + multiplier_minus_one) * (
                delisting.cash_proceeds / close_at_last_trade
            ) - 1.0
            observations.append(
                AssetPeriodReturn(
                    symbol=symbol,
                    period_start=period_start,
                    period_end=period_end,
                    total_return=max(total_return, -1.0),
                    source=delisting.source,
                    currency=currency,
                    dividends_included=True,
                    terminal_treatment="cash",
                )
            )
            continue

        observations.append(
            AssetPeriodReturn(
                symbol=symbol,
                period_start=period_start,
                period_end=period_end,
                total_return=multiplier_minus_one,
                source=source,
                currency=currency,
                dividends_included=True,
                terminal_treatment=None,
            )
        )

    return tuple(observations)


@dataclass(frozen=True)
class TotalReturnEvidence:
    """
    Versioned, source-attributed wrapper around a set of already-derived
    `AssetPeriodReturn` rows -- the same pattern
    `backtesting.execution_evidence.HistoricalExecutionEvidence` uses for
    session/open-price evidence, applied here so total-return evidence can be
    computed once, written to disk with explicit retrieval provenance, and
    reused across validation runs without recomputing from raw bars. `returns`
    plugs directly into `PortfolioValidationInput(returns=..., ...)`.
    """

    retrieved_at: datetime | str
    returns: tuple[AssetPeriodReturn, ...]
    schema_version: int = TOTAL_RETURN_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != TOTAL_RETURN_EVIDENCE_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version deve ser {TOTAL_RETURN_EVIDENCE_SCHEMA_VERSION}."
            )
        return_rows = tuple(self.returns)
        if not return_rows:
            raise ValueError("returns não pode ser vazio.")
        if not all(isinstance(item, AssetPeriodReturn) for item in return_rows):
            raise TypeError("returns exige AssetPeriodReturn.")
        identities = [item.identity for item in return_rows]
        if len(identities) != len(set(identities)):
            raise ValueError("Retorno duplicado para símbolo e período no artefato.")
        retrieved_at = _utc_timestamp(self.retrieved_at, "retrieved_at")
        latest_period_end = max(item.period_end for item in return_rows)
        if retrieved_at.date() < latest_period_end:
            raise ValueError("retrieved_at não pode anteceder a evidência.")
        object.__setattr__(self, "retrieved_at", retrieved_at)
        object.__setattr__(
            self,
            "returns",
            tuple(sorted(return_rows, key=lambda item: item.identity)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest": {
                "retrieved_at": self.retrieved_at.isoformat(),
                "calculation_method": "day_over_day_dividend_reinvested",
            },
            "returns": [item.to_dict() for item in self.returns],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TotalReturnEvidence":
        if not isinstance(data, Mapping):
            raise TypeError("O artefato de retorno total deve ser um objeto.")
        manifest = data.get("manifest")
        if not isinstance(manifest, Mapping):
            raise TypeError("manifest deve ser um objeto.")
        if manifest.get("calculation_method") != "day_over_day_dividend_reinvested":
            raise ValueError("manifest.calculation_method incompatível.")
        raw_returns = data.get("returns")
        if not isinstance(raw_returns, list):
            raise TypeError("returns deve ser uma lista.")
        return cls(
            schema_version=data.get("schema_version", 0),
            retrieved_at=manifest.get("retrieved_at"),
            returns=tuple(AssetPeriodReturn.from_dict(item) for item in raw_returns),
        )


def write_total_return_evidence(
    evidence: TotalReturnEvidence,
    path: str | Path,
) -> Path:
    if not isinstance(evidence, TotalReturnEvidence):
        raise TypeError("evidence exige TotalReturnEvidence.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def load_total_return_evidence(path: str | Path) -> TotalReturnEvidence:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TotalReturnEvidence.from_dict(data)

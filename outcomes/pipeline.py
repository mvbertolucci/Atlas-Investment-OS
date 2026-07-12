from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd

from outcomes.models import OutcomeResult, OutcomeSnapshot
from reports.report_engine import build_company_reports
from storage.history_db import HistoryDatabase


DEFAULT_OUTCOME_HORIZONS_DAYS = (30, 90, 180, 365)


@dataclass(frozen=True)
class OutcomeCaptureResult:
    snapshots: tuple[OutcomeSnapshot, ...]
    skipped_symbols: tuple[str, ...]
    horizons_days: tuple[int, ...]

    @property
    def saved_count(self) -> int:
        return len(self.snapshots)


@dataclass(frozen=True)
class OutcomeEvaluationResult:
    results: tuple[OutcomeResult, ...]
    pending_count: int
    missing_price_symbols: tuple[str, ...]

    @property
    def evaluated_count(self) -> int:
        return len(self.results)


def normalize_outcome_horizons(
    values: Iterable[Any] | None,
) -> tuple[int, ...]:
    if values is None:
        return DEFAULT_OUTCOME_HORIZONS_DAYS

    if isinstance(values, (str, bytes)):
        raise ValueError(
            "outcome_horizons_days deve ser uma lista de dias."
        )

    horizons: set[int] = set()

    for value in values:
        if isinstance(value, bool):
            raise ValueError(
                "Horizontes devem ser números inteiros positivos."
            )

        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Horizontes devem ser números inteiros positivos."
            ) from exc

        if numeric <= 0 or float(value) != numeric:
            raise ValueError(
                "Horizontes devem ser números inteiros positivos."
            )

        horizons.add(numeric)

    if not horizons:
        raise ValueError(
            "outcome_horizons_days não pode ficar vazio."
        )

    return tuple(sorted(horizons))


def build_outcome_snapshots(
    analysis_df: pd.DataFrame,
    *,
    decision_date: datetime | str,
    horizons_days: Iterable[Any] | None = None,
) -> OutcomeCaptureResult:
    horizons = normalize_outcome_horizons(horizons_days)
    reports = build_company_reports(analysis_df)
    rows = {
        str(row.get("symbol", "")).strip().upper(): row
        for _, row in analysis_df.iterrows()
    }

    snapshots: list[OutcomeSnapshot] = []
    skipped: list[str] = []

    for report in reports:
        row = rows.get(report.symbol)
        price = (
            pd.to_numeric(row.get("price"), errors="coerce")
            if row is not None
            else None
        )

        if price is None or pd.isna(price) or float(price) <= 0:
            skipped.append(report.symbol)
            continue

        try:
            snapshot = OutcomeSnapshot.from_company_report(
                report,
                decision_price=float(price),
                decision_date=decision_date,
            )
        except ValueError:
            skipped.append(report.symbol)
            continue

        snapshots.append(snapshot)

    return OutcomeCaptureResult(
        snapshots=tuple(snapshots),
        skipped_symbols=tuple(dict.fromkeys(skipped)),
        horizons_days=horizons,
    )


def capture_outcome_snapshots(
    database: HistoryDatabase,
    analysis_df: pd.DataFrame,
    *,
    decision_date: datetime | str,
    horizons_days: Iterable[Any] | None = None,
) -> OutcomeCaptureResult:
    if not isinstance(database, HistoryDatabase):
        raise TypeError(
            "database deve ser HistoryDatabase."
        )

    result = build_outcome_snapshots(
        analysis_df,
        decision_date=decision_date,
        horizons_days=horizons_days,
    )
    database.save_outcome_snapshots(
        list(result.snapshots)
    )
    return result


def evaluate_due_outcomes(
    database: HistoryDatabase,
    analysis_df: pd.DataFrame,
    *,
    evaluation_date: datetime | str,
    horizons_days: Iterable[Any] | None = None,
) -> OutcomeEvaluationResult:
    if not isinstance(database, HistoryDatabase):
        raise TypeError(
            "database deve ser HistoryDatabase."
        )

    evaluation_at = (
        evaluation_date
        if isinstance(evaluation_date, datetime)
        else datetime.fromisoformat(str(evaluation_date))
    )
    horizons = normalize_outcome_horizons(horizons_days)
    snapshots = database.load_outcome_snapshots()
    existing = database.load_outcome_results()
    existing_keys = {
        (
            str(row["decision_date"]),
            str(row["symbol"]),
            int(row["horizon_days"]),
        )
        for _, row in existing.iterrows()
    }

    prices: dict[str, float] = {}
    for _, row in analysis_df.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        price = pd.to_numeric(
            row.get("price"),
            errors="coerce",
        )
        if symbol and not pd.isna(price) and float(price) > 0:
            prices[symbol] = float(price)

    results: list[OutcomeResult] = []
    pending_count = 0
    missing_prices: list[str] = []

    for _, row in snapshots.iterrows():
        decision_date_text = str(row["decision_date"])
        decision_at = datetime.fromisoformat(
            decision_date_text
        )
        symbol = str(row["symbol"])

        for horizon_days in horizons:
            key = (
                decision_date_text,
                symbol,
                horizon_days,
            )
            if key in existing_keys:
                continue

            due_at = decision_at + timedelta(
                days=horizon_days
            )
            if evaluation_at < due_at:
                pending_count += 1
                continue

            outcome_price = prices.get(symbol)
            if outcome_price is None:
                missing_prices.append(symbol)
                continue

            results.append(
                OutcomeResult(
                    decision_date=decision_at,
                    symbol=symbol,
                    horizon_days=horizon_days,
                    evaluation_date=evaluation_at,
                    decision_price=float(
                        row["decision_price"]
                    ),
                    outcome_price=outcome_price,
                )
            )

    database.save_outcome_results(results)
    return OutcomeEvaluationResult(
        results=tuple(results),
        pending_count=pending_count,
        missing_price_symbols=tuple(
            dict.fromkeys(missing_prices)
        ),
    )

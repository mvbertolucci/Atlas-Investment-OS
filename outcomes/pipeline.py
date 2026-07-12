from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from outcomes.models import OutcomeSnapshot
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

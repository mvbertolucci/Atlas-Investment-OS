from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from storage.history_db import HistoryDatabase


SCORE_COLUMNS = [
    "business_score",
    "valuation_score",
    "financial_score",
    "timing_score",
    "investment_score",
    "opportunity_score",
    "confidence_score",
]


DISPLAY_NAMES = {
    "business_score": "Business Score",
    "valuation_score": "Valuation Score",
    "financial_score": "Financial Score",
    "timing_score": "Timing Score",
    "investment_score": "Investment Score",
    "opportunity_score": "Opportunity Score",
    "confidence_score": "Confidence Score",
}


def load_history(
    database_path: Path,
    symbol: str | None = None,
) -> pd.DataFrame:
    """
    Carrega o histórico salvo no SQLite.

    Quando symbol for informado, retorna apenas o histórico
    daquela empresa.
    """

    with HistoryDatabase(database_path) as database:
        history = database.load_history(symbol=symbol)

    if history.empty:
        return history

    history["snapshot_date"] = pd.to_datetime(
        history["snapshot_date"],
        errors="coerce",
    )

    history = history.dropna(subset=["snapshot_date"])

    sort_columns = ["snapshot_date"]

    if "symbol" in history.columns:
        sort_columns.append("symbol")

    return history.sort_values(sort_columns).reset_index(drop=True)


def latest_snapshot(history: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna o snapshot mais recente de cada empresa.
    """

    if history.empty:
        return history.copy()

    required = {"symbol", "snapshot_date"}

    if not required.issubset(history.columns):
        return pd.DataFrame()

    ordered = history.sort_values(
        ["symbol", "snapshot_date"],
    )

    return (
        ordered.groupby("symbol", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def previous_snapshot(history: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna o penúltimo snapshot disponível de cada empresa.
    """

    if history.empty:
        return history.copy()

    required = {"symbol", "snapshot_date"}

    if not required.issubset(history.columns):
        return pd.DataFrame()

    ordered = history.sort_values(
        ["symbol", "snapshot_date"],
    )

    previous_rows = []

    for _, group in ordered.groupby("symbol"):
        if len(group) >= 2:
            previous_rows.append(group.iloc[-2])

    if not previous_rows:
        return pd.DataFrame(columns=history.columns)

    return pd.DataFrame(previous_rows).reset_index(drop=True)


def previous_run_context(
    history: pd.DataFrame,
    *,
    current_snapshot_date: str | pd.Timestamp,
    current_model_version: str,
) -> tuple[dict[str, dict[str, object]], str, pd.Timestamp | None]:
    """
    Retorna o run global imediatamente anterior, nunca o último registro
    disponível por símbolo. Versões diferentes reiniciam a baseline.
    """
    if history.empty or "snapshot_date" not in history.columns:
        return {}, "first_run", None
    current_at = pd.Timestamp(current_snapshot_date)
    earlier = history.loc[history["snapshot_date"] < current_at].copy()
    if earlier.empty:
        return {}, "first_run", None
    previous_at = earlier["snapshot_date"].max()
    previous = earlier.loc[earlier["snapshot_date"] == previous_at].copy()
    versions = {
        str(value).strip()
        for value in previous.get(
            "model_version",
            pd.Series(["legacy"]),
        ).dropna()
        if str(value).strip()
    }
    if versions != {str(current_model_version).strip()}:
        return {}, "model_version_changed", previous_at
    rows = {
        str(row["symbol"]).strip().upper(): row.to_dict()
        for _, row in previous.iterrows()
        if str(row.get("symbol", "")).strip()
    }
    return rows, "comparable", previous_at


def earnings_between_runs(
    value: Any,
    previous_run_at: pd.Timestamp | None,
    current_run_at: str | datetime | pd.Timestamp,
) -> bool | None:
    """
    True quando a data de earnings cai estritamente entre o run anterior e o
    run atual (transição, não estado) -- None quando não há data de earnings
    ou não há run anterior para comparar. Compartilhada pelo motor de venda
    (portfolio/rebalance.py) e pelos triggers de watchlist (watchlist/
    triggers.py): "houve divulgação de resultado desde o último run" é a
    mesma pergunta nos dois lugares.
    """
    if value is None or pd.isna(value) or previous_run_at is None:
        return None
    earnings_at = pd.to_datetime(value, errors="coerce")
    current_at = pd.Timestamp(current_run_at)
    if pd.isna(earnings_at):
        return None
    return previous_run_at < earnings_at <= current_at


def classify_trend(delta: float | int | None) -> str:
    """
    Classifica a tendência com base na variação do score.
    """

    if delta is None or pd.isna(delta):
        return "Sem histórico"

    value = float(delta)

    if value >= 5:
        return "Melhora forte"

    if value >= 1:
        return "Melhorando"

    if value <= -5:
        return "Piora forte"

    if value <= -1:
        return "Piorando"

    return "Estável"


def build_score_changes(history: pd.DataFrame) -> pd.DataFrame:
    """
    Compara o snapshot mais recente com o anterior.

    Retorna uma linha por empresa contendo valor anterior,
    valor atual, delta e tendência para cada score.
    """

    if history.empty:
        return pd.DataFrame()

    current = latest_snapshot(history)
    previous = previous_snapshot(history)

    if current.empty:
        return pd.DataFrame()

    result = current[
        ["symbol", "snapshot_date"]
    ].copy()

    result = result.rename(
        columns={"snapshot_date": "Current Date"},
    )

    if previous.empty:
        for score_column in SCORE_COLUMNS:
            if score_column not in current.columns:
                continue

            display_name = DISPLAY_NAMES[score_column]

            result[f"{display_name} Previous"] = pd.NA
            result[f"{display_name} Current"] = current[
                score_column
            ].values
            result[f"{display_name} Delta"] = pd.NA
            result[f"{display_name} Trend"] = "Sem histórico"

        return result

    previous_lookup = previous.set_index("symbol")

    for score_column in SCORE_COLUMNS:
        if score_column not in current.columns:
            continue

        display_name = DISPLAY_NAMES[score_column]

        current_values = pd.to_numeric(
            current[score_column],
            errors="coerce",
        )

        previous_values = current["symbol"].map(
            previous_lookup[score_column]
            if score_column in previous_lookup.columns
            else pd.Series(dtype="float64")
        )

        previous_values = pd.to_numeric(
            previous_values,
            errors="coerce",
        )

        delta = current_values - previous_values

        result[f"{display_name} Previous"] = previous_values.values
        result[f"{display_name} Current"] = current_values.values
        result[f"{display_name} Delta"] = delta.round(1).values
        result[f"{display_name} Trend"] = delta.apply(
            classify_trend
        ).values

    return result.sort_values(
        "Opportunity Score Delta"
        if "Opportunity Score Delta" in result.columns
        else "symbol",
        ascending=False
        if "Opportunity Score Delta" in result.columns
        else True,
    ).reset_index(drop=True)


def build_metric_history(
    history: pd.DataFrame,
    symbol: str,
    metric: str,
) -> pd.DataFrame:
    """
    Retorna a série histórica de uma métrica específica.
    """

    if history.empty:
        return pd.DataFrame(
            columns=["snapshot_date", "symbol", metric],
        )

    if metric not in history.columns:
        return pd.DataFrame(
            columns=["snapshot_date", "symbol", metric],
        )

    filtered = history.loc[
        history["symbol"].astype(str).str.upper()
        == symbol.strip().upper(),
        ["snapshot_date", "symbol", metric],
    ].copy()

    filtered[metric] = pd.to_numeric(
        filtered[metric],
        errors="coerce",
    )

    return (
        filtered.dropna(subset=[metric])
        .sort_values("snapshot_date")
        .reset_index(drop=True)
    )


def calculate_period_delta(
    history: pd.DataFrame,
    symbol: str,
    metric: str,
    days: int,
) -> float | None:
    """
    Calcula a mudança de uma métrica entre o valor atual
    e o valor mais próximo disponível antes do período informado.
    """

    metric_history = build_metric_history(
        history,
        symbol,
        metric,
    )

    if metric_history.empty:
        return None

    current_row = metric_history.iloc[-1]
    current_date = current_row["snapshot_date"]
    current_value = current_row[metric]

    cutoff_date = current_date - pd.Timedelta(days=days)

    older = metric_history.loc[
        metric_history["snapshot_date"] <= cutoff_date
    ]

    if older.empty:
        return None

    previous_value = older.iloc[-1][metric]

    if pd.isna(current_value) or pd.isna(previous_value):
        return None

    return round(float(current_value - previous_value), 1)


def build_period_trends(
    history: pd.DataFrame,
    days: int = 30,
) -> pd.DataFrame:
    """
    Gera variações por período para cada empresa.
    """

    if history.empty or "symbol" not in history.columns:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []

    for symbol in sorted(history["symbol"].dropna().unique()):
        row: dict[str, object] = {
            "symbol": symbol,
            "Period Days": days,
        }

        for metric in SCORE_COLUMNS:
            if metric not in history.columns:
                continue

            delta = calculate_period_delta(
                history,
                str(symbol),
                metric,
                days,
            )

            display_name = DISPLAY_NAMES[metric]

            row[f"{display_name} Δ{days}d"] = delta
            row[f"{display_name} Trend"] = classify_trend(delta)

        rows.append(row)

    result = pd.DataFrame(rows)

    opportunity_delta = f"Opportunity Score Δ{days}d"

    if opportunity_delta in result.columns:
        result = result.sort_values(
            opportunity_delta,
            ascending=False,
            na_position="last",
        )

    return result.reset_index(drop=True)

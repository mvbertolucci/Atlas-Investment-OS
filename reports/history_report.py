from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.history import (
    build_period_trends,
    build_score_changes,
    load_history,
)


def build_historical_trends(
    database_path: Path,
    period_days: int = 30,
) -> pd.DataFrame:
    """
    Cria o relatório histórico consolidado do Atlas.

    O relatório combina:

    - último valor disponível;
    - valor do snapshot anterior;
    - variação entre as duas últimas execuções;
    - variação no período solicitado;
    - classificação da tendência.

    Quando ainda não houver histórico suficiente, as colunas
    correspondentes serão mantidas vazias.
    """

    history = load_history(database_path)

    if history.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "Current Date",
                "Business Score Current",
                "Business Score Delta",
                "Business Score Trend",
                "Valuation Score Current",
                "Valuation Score Delta",
                "Valuation Score Trend",
                "Financial Score Current",
                "Financial Score Delta",
                "Financial Score Trend",
                "Timing Score Current",
                "Timing Score Delta",
                "Timing Score Trend",
                "Investment Score Current",
                "Investment Score Delta",
                "Investment Score Trend",
                "Opportunity Score Current",
                "Opportunity Score Delta",
                "Opportunity Score Trend",
                "Confidence Score Current",
                "Confidence Score Delta",
                "Confidence Score Trend",
            ]
        )

    latest_changes = build_score_changes(history)
    period_trends = build_period_trends(
        history,
        days=period_days,
    )

    if latest_changes.empty:
        return period_trends

    if period_trends.empty:
        return latest_changes

    result = latest_changes.merge(
        period_trends,
        on="symbol",
        how="left",
        suffixes=("", f" {period_days}d"),
    )

    preferred_columns = [
        "symbol",
        "Current Date",
        "Opportunity Score Current",
        "Opportunity Score Previous",
        "Opportunity Score Delta",
        "Opportunity Score Trend",
        f"Opportunity Score Δ{period_days}d",
        "Business Score Current",
        "Business Score Previous",
        "Business Score Delta",
        "Business Score Trend",
        f"Business Score Δ{period_days}d",
        "Valuation Score Current",
        "Valuation Score Previous",
        "Valuation Score Delta",
        "Valuation Score Trend",
        f"Valuation Score Δ{period_days}d",
        "Financial Score Current",
        "Financial Score Previous",
        "Financial Score Delta",
        "Financial Score Trend",
        f"Financial Score Δ{period_days}d",
        "Timing Score Current",
        "Timing Score Previous",
        "Timing Score Delta",
        "Timing Score Trend",
        f"Timing Score Δ{period_days}d",
        "Investment Score Current",
        "Investment Score Previous",
        "Investment Score Delta",
        "Investment Score Trend",
        f"Investment Score Δ{period_days}d",
        "Confidence Score Current",
        "Confidence Score Previous",
        "Confidence Score Delta",
        "Confidence Score Trend",
        f"Confidence Score Δ{period_days}d",
    ]

    ordered_columns = [
        column
        for column in preferred_columns
        if column in result.columns
    ]

    remaining_columns = [
        column
        for column in result.columns
        if column not in ordered_columns
    ]

    result = result[ordered_columns + remaining_columns]

    opportunity_delta = "Opportunity Score Delta"

    if opportunity_delta in result.columns:
        result = result.sort_values(
            opportunity_delta,
            ascending=False,
            na_position="last",
        )
    else:
        result = result.sort_values("symbol")

    return result.reset_index(drop=True)


def build_history_summary(
    database_path: Path,
) -> pd.DataFrame:
    """
    Produz um resumo simples da base histórica.

    Uma linha por empresa com:

    - primeira data;
    - última data;
    - quantidade de snapshots;
    - scores atuais;
    - menor e maior Opportunity Score.
    """

    history = load_history(database_path)

    if history.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "First Snapshot",
                "Latest Snapshot",
                "Snapshot Count",
                "Current Opportunity",
                "Minimum Opportunity",
                "Maximum Opportunity",
                "Current Investment",
                "Current Business",
                "Current Valuation",
            ]
        )

    rows: list[dict[str, object]] = []

    for symbol, group in history.groupby("symbol"):
        ordered = group.sort_values("snapshot_date")
        latest = ordered.iloc[-1]

        opportunity = pd.to_numeric(
            ordered.get("opportunity_score"),
            errors="coerce",
        )

        rows.append(
            {
                "symbol": symbol,
                "First Snapshot": ordered["snapshot_date"].min(),
                "Latest Snapshot": ordered["snapshot_date"].max(),
                "Snapshot Count": len(ordered),
                "Current Opportunity": latest.get("opportunity_score"),
                "Minimum Opportunity": (
                    opportunity.min()
                    if opportunity.notna().any()
                    else pd.NA
                ),
                "Maximum Opportunity": (
                    opportunity.max()
                    if opportunity.notna().any()
                    else pd.NA
                ),
                "Current Investment": latest.get("investment_score"),
                "Current Business": latest.get("business_score"),
                "Current Valuation": latest.get("valuation_score"),
            }
        )

    result = pd.DataFrame(rows)

    if "Current Opportunity" in result.columns:
        result = result.sort_values(
            "Current Opportunity",
            ascending=False,
            na_position="last",
        )

    return result.reset_index(drop=True)
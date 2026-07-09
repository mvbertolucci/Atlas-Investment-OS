from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.history_report import build_historical_trends


ALERT_COLUMNS = [
    "symbol",
    "Alert Level",
    "Alert Type",
    "Alert Message",
    "Opportunity Score Current",
    "Opportunity Score Delta",
    "Business Score Delta",
    "Valuation Score Delta",
    "Financial Score Delta",
    "Timing Score Delta",
]


def _numeric(
    frame: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")

    return (
        pd.to_numeric(frame[column], errors="coerce")
        .fillna(default)
    )


def _add_alert(
    rows: list[dict[str, object]],
    row: pd.Series,
    level: str,
    alert_type: str,
    message: str,
) -> None:
    rows.append(
        {
            "symbol": row.get("symbol", ""),
            "Alert Level": level,
            "Alert Type": alert_type,
            "Alert Message": message,
            "Opportunity Score Current": row.get(
                "Opportunity Score Current"
            ),
            "Opportunity Score Delta": row.get(
                "Opportunity Score Delta"
            ),
            "Business Score Delta": row.get(
                "Business Score Delta"
            ),
            "Valuation Score Delta": row.get(
                "Valuation Score Delta"
            ),
            "Financial Score Delta": row.get(
                "Financial Score Delta"
            ),
            "Timing Score Delta": row.get(
                "Timing Score Delta"
            ),
        }
    )


def build_alerts_from_trends(
    trends: pd.DataFrame,
    strong_opportunity_threshold: float = 80.0,
    new_opportunity_threshold: float = 70.0,
    strong_change_threshold: float = 5.0,
    deterioration_threshold: float = -5.0,
) -> pd.DataFrame:
    """
    Gera alertas a partir do relatório histórico do Atlas.

    Tipos de alerta:

    - Strong Opportunity
    - New Opportunity
    - Opportunity Improving
    - Opportunity Weakening
    - Business Improving
    - Business Deterioration
    - Valuation Improving
    - Financial Deterioration
    """

    if trends.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    frame = trends.copy()

    opportunity_current = _numeric(
        frame,
        "Opportunity Score Current",
    )
    opportunity_previous = _numeric(
        frame,
        "Opportunity Score Previous",
    )
    opportunity_delta = _numeric(
        frame,
        "Opportunity Score Delta",
    )
    business_delta = _numeric(
        frame,
        "Business Score Delta",
    )
    valuation_delta = _numeric(
        frame,
        "Valuation Score Delta",
    )
    financial_delta = _numeric(
        frame,
        "Financial Score Delta",
    )

    alerts: list[dict[str, object]] = []

    for index, row in frame.iterrows():
        symbol = str(row.get("symbol", "")).strip()

        if not symbol:
            continue

        current = float(opportunity_current.loc[index])
        previous = float(opportunity_previous.loc[index])
        opportunity_change = float(opportunity_delta.loc[index])
        business_change = float(business_delta.loc[index])
        valuation_change = float(valuation_delta.loc[index])
        financial_change = float(financial_delta.loc[index])

        if current >= strong_opportunity_threshold:
            _add_alert(
                alerts,
                row,
                "HIGH",
                "Strong Opportunity",
                (
                    f"{symbol} possui Opportunity Score de "
                    f"{current:.1f}."
                ),
            )

        if (
            current >= new_opportunity_threshold
            and previous < new_opportunity_threshold
        ):
            _add_alert(
                alerts,
                row,
                "HIGH",
                "New Opportunity",
                (
                    f"{symbol} ultrapassou o limite de oportunidade: "
                    f"{previous:.1f} → {current:.1f}."
                ),
            )

        if opportunity_change >= strong_change_threshold:
            _add_alert(
                alerts,
                row,
                "MEDIUM",
                "Opportunity Improving",
                (
                    f"{symbol} melhorou {opportunity_change:+.1f} pontos "
                    "no Opportunity Score."
                ),
            )

        if opportunity_change <= deterioration_threshold:
            _add_alert(
                alerts,
                row,
                "HIGH",
                "Opportunity Weakening",
                (
                    f"{symbol} piorou {opportunity_change:+.1f} pontos "
                    "no Opportunity Score."
                ),
            )

        if business_change >= strong_change_threshold:
            _add_alert(
                alerts,
                row,
                "MEDIUM",
                "Business Improving",
                (
                    f"{symbol} melhorou {business_change:+.1f} pontos "
                    "no Business Score."
                ),
            )

        if business_change <= deterioration_threshold:
            _add_alert(
                alerts,
                row,
                "HIGH",
                "Business Deterioration",
                (
                    f"{symbol} piorou {business_change:+.1f} pontos "
                    "no Business Score."
                ),
            )

        if valuation_change >= strong_change_threshold:
            _add_alert(
                alerts,
                row,
                "MEDIUM",
                "Valuation Improving",
                (
                    f"{symbol} melhorou {valuation_change:+.1f} pontos "
                    "no Valuation Score."
                ),
            )

        if financial_change <= deterioration_threshold:
            _add_alert(
                alerts,
                row,
                "HIGH",
                "Financial Deterioration",
                (
                    f"{symbol} piorou {financial_change:+.1f} pontos "
                    "no Financial Score."
                ),
            )

    if not alerts:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    result = pd.DataFrame(alerts)

    level_order = {
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 2,
    }

    result["_level_order"] = (
        result["Alert Level"]
        .map(level_order)
        .fillna(99)
    )

    result = result.sort_values(
        [
            "_level_order",
            "Opportunity Score Delta",
            "symbol",
        ],
        ascending=[True, False, True],
        na_position="last",
    )

    return (
        result.drop(columns="_level_order")
        .reset_index(drop=True)
    )


def build_alerts(
    database_path: Path,
    period_days: int = 30,
) -> pd.DataFrame:
    """
    Carrega o histórico do SQLite e produz os alertas do Atlas.
    """

    if not database_path.exists():
        return pd.DataFrame(columns=ALERT_COLUMNS)

    trends = build_historical_trends(
        database_path=database_path,
        period_days=period_days,
    )

    return build_alerts_from_trends(trends)
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.alerts import build_alerts
from reports.history_report import build_history_summary


DEFAULT_TOP_COUNT = 5


def _numeric_series(
    df: pd.DataFrame,
    column: str,
    default: float = 0.0,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(
            default,
            index=df.index,
            dtype="float64",
        )

    return (
        pd.to_numeric(df[column], errors="coerce")
        .fillna(default)
    )


def _safe_number(
    value: Any,
    digits: int = 1,
) -> str:
    numeric = pd.to_numeric(value, errors="coerce")

    if pd.isna(numeric):
        return "-"

    return f"{float(numeric):.{digits}f}"


def _count_alert_level(
    alerts: pd.DataFrame,
    level: str,
) -> int:
    if alerts.empty or "Alert Level" not in alerts.columns:
        return 0

    return int(
        alerts["Alert Level"]
        .astype(str)
        .str.upper()
        .eq(level.upper())
        .sum()
    )


def _count_alert_type(
    alerts: pd.DataFrame,
    alert_type: str,
) -> int:
    if alerts.empty or "Alert Type" not in alerts.columns:
        return 0

    return int(
        alerts["Alert Type"]
        .astype(str)
        .eq(alert_type)
        .sum()
    )


def build_top_opportunities(
    current_df: pd.DataFrame,
    top_count: int = DEFAULT_TOP_COUNT,
) -> pd.DataFrame:
    """
    Retorna as principais oportunidades da execução atual.
    """

    columns = [
        column
        for column in [
            "symbol",
            "name",
            "Opportunity Score",
            "Opportunity Rating",
            "Conviction Score",
            "Conviction Rating",
            "Decision",
            "Decision Rating",
            "Suggested Action",
            "Decision Confidence",
            "Investment Thesis",
            "Thesis Strengths",
            "Thesis Risks",
            "Thesis Catalysts",
            "Investment Score",
            "Business Score",
            "Valuation Score",
            "Financial Score",
            "Timing Score",
            "Confidence Score",
            "Opportunity Drivers",
        ]
        if column in current_df.columns
    ]

    if current_df.empty or "Opportunity Score" not in current_df.columns:
        return pd.DataFrame(columns=columns)

    result = current_df[columns].copy()

    result["Opportunity Score"] = pd.to_numeric(
        result["Opportunity Score"],
        errors="coerce",
    )

    result = (
        result.dropna(subset=["Opportunity Score"])
        .sort_values(
            "Opportunity Score",
            ascending=False,
        )
        .head(max(int(top_count), 0))
        .reset_index(drop=True)
    )

    result.insert(
        0,
        "Rank",
        range(1, len(result) + 1),
    )

    return result


def build_improving_companies(
    alerts: pd.DataFrame,
    max_items: int = 5,
) -> pd.DataFrame:
    """
    Seleciona alertas relacionados a melhora.
    """

    columns = [
        "symbol",
        "Alert Type",
        "Alert Message",
        "Opportunity Score Current",
        "Opportunity Score Delta",
        "Business Score Delta",
        "Valuation Score Delta",
    ]

    if alerts.empty or "Alert Type" not in alerts.columns:
        return pd.DataFrame(columns=columns)

    improving_types = {
        "New Opportunity",
        "Opportunity Improving",
        "Business Improving",
        "Valuation Improving",
        "Strong Opportunity",
    }

    result = alerts.loc[
        alerts["Alert Type"].isin(improving_types)
    ].copy()

    if result.empty:
        return pd.DataFrame(columns=columns)

    result["_priority"] = result["Alert Type"].map(
        {
            "New Opportunity": 0,
            "Strong Opportunity": 1,
            "Opportunity Improving": 2,
            "Business Improving": 3,
            "Valuation Improving": 4,
        }
    ).fillna(99)

    result["_delta"] = _numeric_series(
        result,
        "Opportunity Score Delta",
    )

    result = (
        result.sort_values(
            ["_priority", "_delta", "symbol"],
            ascending=[True, False, True],
        )
        .drop_duplicates(
            subset=["symbol"],
            keep="first",
        )
        .head(max(int(max_items), 0))
        .drop(
            columns=["_priority", "_delta"],
            errors="ignore",
        )
    )

    return result[
        [column for column in columns if column in result.columns]
    ].reset_index(drop=True)


def build_weakening_companies(
    alerts: pd.DataFrame,
    max_items: int = 5,
) -> pd.DataFrame:
    """
    Seleciona alertas relacionados a deterioração.
    """

    columns = [
        "symbol",
        "Alert Type",
        "Alert Message",
        "Opportunity Score Current",
        "Opportunity Score Delta",
        "Business Score Delta",
        "Financial Score Delta",
    ]

    if alerts.empty or "Alert Type" not in alerts.columns:
        return pd.DataFrame(columns=columns)

    weakening_types = {
        "Opportunity Weakening",
        "Business Deterioration",
        "Financial Deterioration",
    }

    result = alerts.loc[
        alerts["Alert Type"].isin(weakening_types)
    ].copy()

    if result.empty:
        return pd.DataFrame(columns=columns)

    result["_priority"] = result["Alert Type"].map(
        {
            "Opportunity Weakening": 0,
            "Business Deterioration": 1,
            "Financial Deterioration": 2,
        }
    ).fillna(99)

    result["_delta"] = _numeric_series(
        result,
        "Opportunity Score Delta",
    )

    result = (
        result.sort_values(
            ["_priority", "_delta", "symbol"],
            ascending=[True, True, True],
        )
        .drop_duplicates(
            subset=["symbol"],
            keep="first",
        )
        .head(max(int(max_items), 0))
        .drop(
            columns=["_priority", "_delta"],
            errors="ignore",
        )
    )

    return result[
        [column for column in columns if column in result.columns]
    ].reset_index(drop=True)


def build_brief_summary(
    current_df: pd.DataFrame,
    alerts: pd.DataFrame,
    database_path: Path,
) -> dict[str, Any]:
    """
    Produz os indicadores gerais usados pelo Morning Brief.
    """

    history_summary = build_history_summary(database_path)

    snapshot_count = 0
    historical_symbols = 0
    first_snapshot = None
    latest_snapshot = None

    if not history_summary.empty:
        historical_symbols = int(
            history_summary["symbol"].nunique()
        )

        if "Snapshot Count" in history_summary.columns:
            snapshot_count = int(
                pd.to_numeric(
                    history_summary["Snapshot Count"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

        if "First Snapshot" in history_summary.columns:
            first_snapshot = pd.to_datetime(
                history_summary["First Snapshot"],
                errors="coerce",
            ).min()

        if "Latest Snapshot" in history_summary.columns:
            latest_snapshot = pd.to_datetime(
                history_summary["Latest Snapshot"],
                errors="coerce",
            ).max()

    opportunity = _numeric_series(
        current_df,
        "Opportunity Score",
        default=0.0,
    )

    return {
        "Generated At": datetime.now(),
        "Companies Analysed": int(len(current_df)),
        "New Opportunities": _count_alert_type(
            alerts,
            "New Opportunity",
        ),
        "Strong Opportunities": _count_alert_type(
            alerts,
            "Strong Opportunity",
        ),
        "High Alerts": _count_alert_level(
            alerts,
            "HIGH",
        ),
        "Medium Alerts": _count_alert_level(
            alerts,
            "MEDIUM",
        ),
        "Total Alerts": int(len(alerts)),
        "Average Opportunity": (
            round(float(opportunity.mean()), 1)
            if len(opportunity)
            else None
        ),
        "Maximum Opportunity": (
            round(float(opportunity.max()), 1)
            if len(opportunity)
            else None
        ),
        "Historical Symbols": historical_symbols,
        "Historical Rows": snapshot_count,
        "First Snapshot": first_snapshot,
        "Latest Snapshot": latest_snapshot,
    }


def build_morning_brief_tables(
    current_df: pd.DataFrame,
    database_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
) -> dict[str, Any]:
    """
    Constrói todos os dados do Morning Brief.
    """

    alerts = build_alerts(
        database_path=database_path,
        period_days=period_days,
    )

    summary = build_brief_summary(
        current_df=current_df,
        alerts=alerts,
        database_path=database_path,
    )

    top_opportunities = build_top_opportunities(
        current_df=current_df,
        top_count=top_count,
    )

    improving = build_improving_companies(
        alerts=alerts,
        max_items=top_count,
    )

    weakening = build_weakening_companies(
        alerts=alerts,
        max_items=top_count,
    )

    important_alerts = alerts.head(10).copy()

    return {
        "summary": summary,
        "top_opportunities": top_opportunities,
        "improving": improving,
        "weakening": weakening,
        "alerts": alerts,
        "important_alerts": important_alerts,
    }


def build_morning_brief_dataframe(
    current_df: pd.DataFrame,
    database_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
) -> pd.DataFrame:
    """
    Produz uma tabela vertical adequada para uma aba do Excel.
    """

    data = build_morning_brief_tables(
        current_df=current_df,
        database_path=database_path,
        period_days=period_days,
        top_count=top_count,
    )

    summary = data["summary"]
    rows: list[dict[str, Any]] = []

    def add_row(
        section: str,
        item: str = "",
        value: Any = "",
        details: str = "",
    ) -> None:
        rows.append(
            {
                "Section": section,
                "Item": item,
                "Value": value,
                "Details": details,
            }
        )

    add_row(
        "Overview",
        "Generated At",
        summary["Generated At"].strftime("%Y-%m-%d %H:%M:%S"),
    )
    add_row(
        "Overview",
        "Companies Analysed",
        summary["Companies Analysed"],
    )
    add_row(
        "Overview",
        "New Opportunities",
        summary["New Opportunities"],
    )
    add_row(
        "Overview",
        "Strong Opportunities",
        summary["Strong Opportunities"],
    )
    add_row(
        "Overview",
        "HIGH Alerts",
        summary["High Alerts"],
    )
    add_row(
        "Overview",
        "MEDIUM Alerts",
        summary["Medium Alerts"],
    )
    add_row(
        "Overview",
        "Average Opportunity",
        summary["Average Opportunity"],
    )
    add_row(
        "Overview",
        "Maximum Opportunity",
        summary["Maximum Opportunity"],
    )

    top_opportunities = data["top_opportunities"]

    for _, row in top_opportunities.iterrows():
        details = " | ".join(
            part
            for part in [
                str(row.get("Decision Rating", "")).strip(),
                str(row.get("Investment Thesis", "")).strip(),
            ]
            if part and part.lower() not in {"nan", "none"}
        )

        add_row(
            "Top Opportunities",
            f"{int(row.get('Rank', 0))}. {row.get('symbol', '')}",
            _safe_number(row.get("Opportunity Score")),
            details or str(row.get("Opportunity Drivers", "")),
        )

    improving = data["improving"]

    for _, row in improving.iterrows():
        add_row(
            "Improving",
            str(row.get("symbol", "")),
            _safe_number(
                row.get("Opportunity Score Delta"),
            ),
            str(row.get("Alert Message", "")),
        )

    weakening = data["weakening"]

    for _, row in weakening.iterrows():
        add_row(
            "Weakening",
            str(row.get("symbol", "")),
            _safe_number(
                row.get("Opportunity Score Delta"),
            ),
            str(row.get("Alert Message", "")),
        )

    important_alerts = data["important_alerts"]

    for _, row in important_alerts.iterrows():
        add_row(
            "Important Alerts",
            str(row.get("symbol", "")),
            str(row.get("Alert Level", "")),
            (
                f"{row.get('Alert Type', '')}: "
                f"{row.get('Alert Message', '')}"
            ),
        )

    add_row(
        "History",
        "Historical Rows",
        summary["Historical Rows"],
    )
    add_row(
        "History",
        "Historical Symbols",
        summary["Historical Symbols"],
    )
    add_row(
        "History",
        "First Snapshot",
        (
            summary["First Snapshot"].strftime("%Y-%m-%d %H:%M:%S")
            if pd.notna(summary["First Snapshot"])
            else "-"
        ),
    )
    add_row(
        "History",
        "Latest Snapshot",
        (
            summary["Latest Snapshot"].strftime("%Y-%m-%d %H:%M:%S")
            if pd.notna(summary["Latest Snapshot"])
            else "-"
        ),
    )

    return pd.DataFrame(rows)


def render_morning_brief(
    current_df: pd.DataFrame,
    database_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
) -> str:
    """
    Gera o Morning Brief em formato de texto/Markdown.
    """

    data = build_morning_brief_tables(
        current_df=current_df,
        database_path=database_path,
        period_days=period_days,
        top_count=top_count,
    )

    summary = data["summary"]
    lines: list[str] = []

    lines.extend(
        [
            "=" * 70,
            "ATLAS MORNING BRIEF",
            "=" * 70,
            "",
            f"Gerado em: {summary['Generated At']:%Y-%m-%d %H:%M:%S}",
            f"Empresas analisadas: {summary['Companies Analysed']}",
            f"Novas oportunidades: {summary['New Opportunities']}",
            f"Oportunidades fortes: {summary['Strong Opportunities']}",
            f"Alertas HIGH: {summary['High Alerts']}",
            f"Alertas MEDIUM: {summary['Medium Alerts']}",
            (
                "Opportunity médio: "
                f"{_safe_number(summary['Average Opportunity'])}"
            ),
            "",
            "-" * 70,
            "TOP OPPORTUNITIES",
            "-" * 70,
        ]
    )

    top_opportunities = data["top_opportunities"]

    if top_opportunities.empty:
        lines.append("Nenhuma oportunidade disponível.")
    else:
        for _, row in top_opportunities.iterrows():
            lines.append(
                f"{int(row['Rank'])}. "
                f"{row.get('symbol', ''):<8} "
                f"{_safe_number(row.get('Opportunity Score'))}"
            )

            decision = str(
                row.get("Decision Rating", "")
            ).strip()

            conviction = _safe_number(
                row.get("Conviction Score")
            )

            thesis = str(
                row.get("Investment Thesis", "")
            ).strip()

            risks = str(
                row.get("Thesis Risks", "")
            ).strip()

            action = str(
                row.get("Suggested Action", "")
            ).strip()

            drivers = str(
                row.get("Opportunity Drivers", "")
            ).strip()

            if decision and decision.lower() not in {"nan", "none"}:
                lines.append(f"   Decisão: {decision}")

            if conviction != "-":
                lines.append(f"   Conviction: {conviction}")

            if thesis and thesis.lower() not in {"nan", "none"}:
                lines.append(f"   Tese: {thesis}")

            if (
                risks
                and risks.lower() not in {"nan", "none"}
                and risks != "Nenhum risco crítico identificado"
            ):
                lines.append(f"   Riscos: {risks}")

            if action and action.lower() not in {"nan", "none"}:
                lines.append(f"   Ação: {action}")

            if drivers and drivers != "Nenhum":
                lines.append(f"   Drivers: {drivers}")

    lines.extend(
        [
            "",
            "-" * 70,
            "EMPRESAS EM ALTA",
            "-" * 70,
        ]
    )

    improving = data["improving"]

    if improving.empty:
        lines.append("Nenhuma melhora relevante detectada.")
    else:
        for _, row in improving.iterrows():
            lines.append(
                f"▲ {row.get('symbol', '')} — "
                f"{row.get('Alert Message', '')}"
            )

    lines.extend(
        [
            "",
            "-" * 70,
            "EMPRESAS EM QUEDA",
            "-" * 70,
        ]
    )

    weakening = data["weakening"]

    if weakening.empty:
        lines.append("Nenhuma deterioração relevante detectada.")
    else:
        for _, row in weakening.iterrows():
            lines.append(
                f"▼ {row.get('symbol', '')} — "
                f"{row.get('Alert Message', '')}"
            )

    lines.extend(
        [
            "",
            "-" * 70,
            "ALERTAS IMPORTANTES",
            "-" * 70,
        ]
    )

    important_alerts = data["important_alerts"]

    if important_alerts.empty:
        lines.append("Nenhum alerta importante.")
    else:
        for _, row in important_alerts.iterrows():
            lines.append(
                f"[{row.get('Alert Level', '')}] "
                f"{row.get('symbol', '')} — "
                f"{row.get('Alert Type', '')}: "
                f"{row.get('Alert Message', '')}"
            )

    lines.extend(
        [
            "",
            "-" * 70,
            "HISTÓRICO",
            "-" * 70,
            f"Registros históricos: {summary['Historical Rows']}",
            f"Empresas no histórico: {summary['Historical Symbols']}",
            (
                "Último snapshot: "
                + (
                    summary["Latest Snapshot"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if pd.notna(summary["Latest Snapshot"])
                    else "-"
                )
            ),
            "",
            "Resumo gerado pelo Atlas.",
        ]
    )

    return "\n".join(lines)


def write_morning_brief(
    current_df: pd.DataFrame,
    database_path: Path,
    output_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
) -> Path:
    """
    Salva o Morning Brief em arquivo Markdown.
    """

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = render_morning_brief(
        current_df=current_df,
        database_path=database_path,
        period_days=period_days,
        top_count=top_count,
    )

    output_path.write_text(
        content,
        encoding="utf-8",
    )

    return output_path
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from analytics.alerts import build_alerts
from outcomes.analytics import OutcomeAnalyticsReport
from portfolio.report import PortfolioReport
from reports.history_report import build_history_summary
from reports.report_engine import build_company_reports
from reports.report_models import CompanyReport


DEFAULT_TOP_COUNT = 5


def _safe_percent(value: Any, digits: int = 1) -> str:
    numeric = pd.to_numeric(value, errors="coerce")

    if pd.isna(numeric):
        return "-"

    return f"{float(numeric) * 100:.{digits}f}%"


def _safe_money(
    value: Any,
    currency: str,
) -> str:
    numeric = pd.to_numeric(value, errors="coerce")

    if pd.isna(numeric):
        return "-"

    return f"{currency} {float(numeric):,.2f}"


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


def _top_company_reports(
    reports: Sequence[CompanyReport],
    top_count: int,
) -> list[CompanyReport]:
    candidates = [
        report
        for report in reports
        if report.opportunity_score is not None
    ]

    return sorted(
        candidates,
        key=lambda report: report.opportunity_score or 0.0,
        reverse=True,
    )[:max(int(top_count), 0)]


def build_portfolio_brief(
    portfolio_report: PortfolioReport,
    company_reports: Sequence[CompanyReport],
    top_count: int = DEFAULT_TOP_COUNT,
) -> dict[str, Any]:
    """Constrói a visão executiva de carteira do Morning Brief."""

    if not isinstance(portfolio_report, PortfolioReport):
        raise TypeError(
            "portfolio_report deve ser PortfolioReport."
        )

    limit = max(int(top_count), 0)
    weights = portfolio_report.allocation.get(
        "by_symbol",
        {},
    )
    reports = {
        report.symbol: report
        for report in company_reports
    }

    positions: list[dict[str, Any]] = []

    for symbol, weight in weights.items():
        report = reports.get(str(symbol).upper())
        positions.append(
            {
                "symbol": str(symbol).upper(),
                "weight": float(weight),
                "conviction_score": (
                    report.conviction_score
                    if report is not None
                    else None
                ),
                "risk_penalty": (
                    report.risk_penalty
                    if report is not None
                    else None
                ),
                "decision": (
                    report.decision
                    if report is not None
                    else ""
                ),
                "decision_rating": (
                    report.decision_rating
                    if report is not None
                    else ""
                ),
            }
        )

    largest_positions = sorted(
        positions,
        key=lambda item: item["weight"],
        reverse=True,
    )[:limit]

    highest_conviction = sorted(
        (
            item
            for item in positions
            if item["conviction_score"] is not None
        ),
        key=lambda item: item["conviction_score"],
        reverse=True,
    )[:limit]

    risk_priority = {
        "AVOID": 3,
        "WATCH": 2,
        "HOLD": 1,
    }
    highest_risk = sorted(
        positions,
        key=lambda item: (
            item["risk_penalty"] or 0.0,
            risk_priority.get(item["decision"], 0),
            item["weight"],
        ),
        reverse=True,
    )[:limit]

    actions = sorted(
        portfolio_report.rebalance.get("actions", []),
        key=lambda item: int(item.get("priority", 100)),
    )[:limit]

    return {
        "report": portfolio_report,
        "summary": portfolio_report.summary,
        "largest_positions": largest_positions,
        "highest_conviction": highest_conviction,
        "highest_risk": highest_risk,
        "rebalance_actions": actions,
        "warnings": list(portfolio_report.warnings),
    }


def build_top_opportunities(
    current_df: pd.DataFrame,
    top_count: int = DEFAULT_TOP_COUNT,
) -> pd.DataFrame:
    """
    Interface legada mantida para compatibilidade.

    A seleção é feita por objetos CompanyReport e convertida
    novamente em DataFrame apenas para consumidores antigos.
    """

    reports = build_company_reports(current_df)
    top_reports = _top_company_reports(reports, top_count)

    rows: list[dict[str, Any]] = []

    for rank, report in enumerate(top_reports, start=1):
        rows.append(
            {
                "Rank": rank,
                "symbol": report.symbol,
                "name": report.company_name,
                "Opportunity Score": report.opportunity_score,
                "Conviction Score": report.conviction_score,
                "Decision": report.decision,
                "Decision Rating": report.decision_rating,
                "Suggested Action": report.suggested_action,
                "Decision Confidence": report.decision_confidence,
                "Investment Thesis": report.investment_thesis,
                "Thesis Strengths": "; ".join(report.strengths),
                "Thesis Risks": "; ".join(report.risks),
                "Thesis Catalysts": "; ".join(report.catalysts),
                "Investment Score": report.investment_score,
                "Business Score": report.business_score,
                "Valuation Score": report.valuation_score,
                "Financial Score": report.financial_score,
                "Timing Score": report.timing_score,
                "Confidence Score": report.confidence_score,
                "Decision Drivers": "; ".join(
                    report.decision_drivers
                ),
            }
        )

    return pd.DataFrame(rows)


def build_improving_companies(
    alerts: pd.DataFrame,
    max_items: int = 5,
) -> pd.DataFrame:
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

    reports = build_company_reports(current_df)
    opportunities = [
        report.opportunity_score
        for report in reports
        if report.opportunity_score is not None
    ]

    return {
        "Generated At": datetime.now(),
        "Companies Analysed": len(reports),
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
            round(sum(opportunities) / len(opportunities), 1)
            if opportunities
            else None
        ),
        "Maximum Opportunity": (
            round(max(opportunities), 1)
            if opportunities
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
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> dict[str, Any]:
    alerts = build_alerts(
        database_path=database_path,
        period_days=period_days,
    )

    company_reports = build_company_reports(current_df)
    top_reports = _top_company_reports(
        company_reports,
        top_count,
    )

    result = {
        "summary": build_brief_summary(
            current_df=current_df,
            alerts=alerts,
            database_path=database_path,
        ),
        "company_reports": company_reports,
        "top_reports": top_reports,
        "top_opportunities": build_top_opportunities(
            current_df=current_df,
            top_count=top_count,
        ),
        "improving": build_improving_companies(
            alerts=alerts,
            max_items=top_count,
        ),
        "weakening": build_weakening_companies(
            alerts=alerts,
            max_items=top_count,
        ),
        "alerts": alerts,
        "important_alerts": alerts.head(10).copy(),
    }

    result["portfolio"] = (
        build_portfolio_brief(
            portfolio_report,
            company_reports,
            top_count=top_count,
        )
        if portfolio_report is not None
        else None
    )
    result["outcome"] = outcome_report

    return result


def build_morning_brief_dataframe(
    current_df: pd.DataFrame,
    database_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> pd.DataFrame:
    data = build_morning_brief_tables(
        current_df=current_df,
        database_path=database_path,
        period_days=period_days,
        top_count=top_count,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
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
        summary["Generated At"].strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
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

    for rank, report in enumerate(
        data["top_reports"],
        start=1,
    ):
        details = " | ".join(
            part
            for part in [
                report.decision_rating,
                report.investment_thesis,
            ]
            if part
        )

        add_row(
            "Top Opportunities",
            f"{rank}. {report.symbol}",
            _safe_number(report.opportunity_score),
            details,
        )

    for _, row in data["improving"].iterrows():
        add_row(
            "Improving",
            str(row.get("symbol", "")),
            _safe_number(
                row.get("Opportunity Score Delta"),
            ),
            str(row.get("Alert Message", "")),
        )

    for _, row in data["weakening"].iterrows():
        add_row(
            "Weakening",
            str(row.get("symbol", "")),
            _safe_number(
                row.get("Opportunity Score Delta"),
            ),
            str(row.get("Alert Message", "")),
        )

    for _, row in data["important_alerts"].iterrows():
        add_row(
            "Important Alerts",
            str(row.get("symbol", "")),
            str(row.get("Alert Level", "")),
            (
                f"{row.get('Alert Type', '')}: "
                f"{row.get('Alert Message', '')}"
            ),
        )

    portfolio = data["portfolio"]

    if portfolio is not None:
        portfolio_summary = portfolio["summary"]
        add_row(
            "Portfolio Overview",
            "Portfolio",
            portfolio_summary.get("portfolio_name", ""),
            str(portfolio_summary.get("quality_rating", "")),
        )
        add_row(
            "Portfolio Overview",
            "Quality Score",
            portfolio_summary.get("quality_score"),
        )

        for position in portfolio["largest_positions"]:
            add_row(
                "Portfolio Allocation",
                position["symbol"],
                position["weight"],
                position["decision_rating"],
            )

        for action in portfolio["rebalance_actions"]:
            add_row(
                "Portfolio Rebalance (Advisory)",
                str(action.get("symbol", "")),
                str(action.get("action", "")),
                str(action.get("reason", "")),
            )

    outcome = data["outcome"]

    if outcome is not None:
        hit_rate = outcome.hit_rate
        add_row(
            "Outcome Analytics",
            "Directional Hit Rate",
            hit_rate.hit_rate,
            f"{hit_rate.hit_count}/{hit_rate.eligible_count}",
        )
        add_row(
            "Outcome Analytics",
            "Excluded Decisions",
            hit_rate.excluded_count,
            "HOLD and WATCH",
        )
        for row in hit_rate.by_horizon:
            add_row(
                "Outcome by Horizon",
                f"{row['horizon_days']} days",
                row["hit_rate"],
                f"n={row['eligible_count']}",
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
            summary["First Snapshot"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if pd.notna(summary["First Snapshot"])
            else "-"
        ),
    )
    add_row(
        "History",
        "Latest Snapshot",
        (
            summary["Latest Snapshot"].strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if pd.notna(summary["Latest Snapshot"])
            else "-"
        ),
    )

    return pd.DataFrame(rows)


def _append_company_report(
    lines: list[str],
    rank: int,
    report: CompanyReport,
) -> None:
    lines.append(
        f"{rank}. {report.symbol:<8} "
        f"{_safe_number(report.opportunity_score)}"
    )

    if report.decision_rating:
        lines.append(
            f"   Decisão: {report.decision_rating}"
        )

    if report.conviction_score is not None:
        lines.append(
            "   Conviction: "
            f"{_safe_number(report.conviction_score)}"
        )

    if report.investment_thesis:
        lines.append(
            f"   Tese: {report.investment_thesis}"
        )

    if report.risks:
        lines.append(
            "   Riscos: " + "; ".join(report.risks)
        )

    if report.suggested_action:
        lines.append(
            f"   Ação: {report.suggested_action}"
        )

    if report.decision_drivers:
        lines.append(
            "   Drivers: "
            + "; ".join(report.decision_drivers)
        )


def render_morning_brief(
    current_df: pd.DataFrame,
    database_path: Path,
    period_days: int = 30,
    top_count: int = DEFAULT_TOP_COUNT,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> str:
    data = build_morning_brief_tables(
        current_df=current_df,
        database_path=database_path,
        period_days=period_days,
        top_count=top_count,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    summary = data["summary"]
    lines: list[str] = [
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

    top_reports = data["top_reports"]

    if not top_reports:
        lines.append("Nenhuma oportunidade disponível.")
    else:
        for rank, report in enumerate(
            top_reports,
            start=1,
        ):
            _append_company_report(
                lines,
                rank,
                report,
            )

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
        lines.append(
            "Nenhuma melhora relevante detectada."
        )
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
        lines.append(
            "Nenhuma deterioração relevante detectada."
        )
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

    portfolio = data["portfolio"]

    if portfolio is not None:
        portfolio_summary = portfolio["summary"]
        currency = str(
            portfolio_summary.get("currency", "BRL")
        )
        lines.extend(
            [
                "",
                "-" * 70,
                "PORTFOLIO INTELLIGENCE",
                "-" * 70,
                (
                    "Carteira: "
                    f"{portfolio_summary.get('portfolio_name', '')}"
                ),
                (
                    "Valor total: "
                    + _safe_money(
                        portfolio_summary.get("total_value"),
                        currency,
                    )
                ),
                (
                    "Qualidade: "
                    f"{_safe_number(portfolio_summary.get('quality_score'))} "
                    f"({portfolio_summary.get('quality_rating', '-')})"
                ),
                (
                    "Caixa: "
                    f"{_safe_percent(portfolio_summary.get('cash_weight'))}"
                ),
                (
                    "Maior posição: "
                    f"{_safe_percent(portfolio_summary.get('largest_position_weight'))}"
                ),
                (
                    "Concentração: "
                    f"{_safe_number(portfolio_summary.get('concentration_score'))}"
                ),
                (
                    "Diversificação: "
                    f"{_safe_number(portfolio_summary.get('diversification_score'))}"
                ),
                "",
                "Maiores posições:",
            ]
        )

        for position in portfolio["largest_positions"]:
            lines.append(
                f"- {position['symbol']}: "
                f"{_safe_percent(position['weight'])}"
            )

        lines.append("")
        lines.append("Maior convicção:")
        if portfolio["highest_conviction"]:
            for position in portfolio["highest_conviction"]:
                lines.append(
                    f"- {position['symbol']}: "
                    f"{_safe_number(position['conviction_score'])}"
                )
        else:
            lines.append("- Dados de convicção indisponíveis.")

        lines.append("")
        lines.append("Maior risco:")
        if portfolio["highest_risk"]:
            for position in portfolio["highest_risk"]:
                lines.append(
                    f"- {position['symbol']}: penalidade "
                    f"{_safe_number(position['risk_penalty'])}"
                    + (
                        f" | {position['decision_rating']}"
                        if position["decision_rating"]
                        else ""
                    )
                )
        else:
            lines.append("- Dados de risco indisponíveis.")

        lines.extend(
            [
                "",
                "Rebalanceamento consultivo:",
                "As ações abaixo são sugestões; nenhuma ordem é executada.",
            ]
        )
        if portfolio["rebalance_actions"]:
            for action in portfolio["rebalance_actions"]:
                lines.append(
                    f"- {action.get('symbol', '')}: "
                    f"{action.get('action', '')} | "
                    f"{_safe_percent(action.get('current_weight'))} → "
                    f"{_safe_percent(action.get('target_weight'))} | "
                    f"{action.get('reason', '')}"
                )
        else:
            lines.append("- Nenhuma ação sugerida.")

        if portfolio["warnings"]:
            lines.append("")
            lines.append("Alertas da carteira:")
            for warning in portfolio["warnings"][:top_count]:
                lines.append(f"- {warning}")

    outcome = data["outcome"]

    if outcome is not None:
        hit_rate = outcome.hit_rate
        lines.extend(
            [
                "",
                "-" * 70,
                "OUTCOME ANALYTICS",
                "-" * 70,
            ]
        )

        if hit_rate.eligible_count == 0:
            lines.append(
                "Amostra insuficiente: nenhum resultado direcional maduro."
            )
        else:
            lines.append(
                "Hit rate direcional: "
                f"{_safe_number(hit_rate.hit_rate)}% "
                f"({hit_rate.hit_count}/{hit_rate.eligible_count})"
            )
            lines.append(
                "Decisões excluídas: "
                f"{hit_rate.excluded_count} (HOLD/WATCH)"
            )
            lines.append("Por horizonte:")
            for row in hit_rate.by_horizon[:top_count]:
                lines.append(
                    f"- {row['horizon_days']} dias: "
                    f"{_safe_number(row['hit_rate'])}% "
                    f"(n={row['eligible_count']})"
                )

            calibration = [
                *outcome.opportunity_calibration,
                *outcome.conviction_calibration,
            ]
            calibration = sorted(
                calibration,
                key=lambda row: (
                    row.get("count", 0),
                    row.get("average_return_pct", 0.0),
                ),
                reverse=True,
            )[:top_count]
            if calibration:
                lines.append("Faixas com maior amostra:")
                for row in calibration:
                    lines.append(
                        f"- {row['score']} "
                        f"{row['bucket_min']}-{row['bucket_max']} | "
                        f"{row['horizon_days']} dias | "
                        f"retorno médio "
                        f"{_safe_number(row['average_return_pct'])}% | "
                        f"n={row['count']}"
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
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> Path:
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
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    output_path.write_text(
        content,
        encoding="utf-8",
    )

    return output_path

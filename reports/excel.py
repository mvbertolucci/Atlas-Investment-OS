from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd

from reports.diagnostics import build_diagnostics
from reports.explainability import build_explainability
from reports.history_report import (
    build_historical_trends,
    build_history_summary,
)


def _format_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
) -> None:
    """
    Aplica formatação básica e reutilizável às abas do Excel.
    """

    worksheet = writer.sheets.get(sheet_name)

    if worksheet is None:
        return

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter

        for cell in column_cells:
            value = cell.value

            if value is not None:
                max_length = max(
                    max_length,
                    len(str(value)),
                )

        worksheet.column_dimensions[column_letter].width = min(
            max_length + 2,
            40,
        )


def _build_historical_reports(
    database_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Gera os relatórios históricos sem interromper a criação
    do Excel caso o banco ainda não exista ou esteja vazio.
    """

    if not database_path.exists():
        return pd.DataFrame(), pd.DataFrame()

    try:
        trends = build_historical_trends(
            database_path=database_path,
            period_days=30,
        )

        summary = build_history_summary(
            database_path=database_path,
        )

        return trends, summary

    except Exception as exc:
        print(
            "[AVISO] Não foi possível gerar os relatórios históricos: "
            f"{exc}"
        )

        return pd.DataFrame(), pd.DataFrame()


def write_latest_and_history(
    df: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path | None]:
    """
    Gera o arquivo Excel histórico da execução e atualiza latest.xlsx.

    Abas geradas:

    - Ranking
    - Summary
    - Opportunity Analysis
    - Decision Analysis
    - Explainability
    - Diagnostics
    - Historical Trends
    - History Summary
    """

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    history_dir = output_dir / "history"

    history_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    root_dir = output_dir.parent
    database_path = root_dir / "data" / "atlas_history.db"

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    history_file = (
        history_dir
        / f"atlas_snapshot_{timestamp}.xlsx"
    )

    latest_file = output_dir / "latest.xlsx"

    summary_columns = [
        column
        for column in [
            "symbol",
            "name",
            "Investment Score",
            "Opportunity Score",
            "Opportunity Rating",
            "Conviction Score",
            "Conviction Rating",
            "Decision",
            "Decision Rating",
            "Suggested Action",
            "Decision Confidence",
            "Business Score",
            "Valuation Score",
            "Financial Score",
            "Timing Score",
            "Confidence Score",
            "Risk Penalty",
            "Recommendation",
        ]
        if column in df.columns
    ]

    opportunity_columns = [
        column
        for column in [
            "symbol",
            "name",
            "Opportunity Base",
            "Opportunity Bonus",
            "Opportunity Penalty",
            "Opportunity Score",
            "Opportunity Rating",
            "Opportunity Drivers",
            "Investment Score",
            "Business Score",
            "Valuation Score",
            "Financial Score",
            "Timing Score",
            "Confidence Score",
            "Risk Penalty",
            "Deal Breakers",
        ]
        if column in df.columns
    ]

    decision_columns = [
        column
        for column in [
            "symbol",
            "name",
            "Decision",
            "Decision Rating",
            "Suggested Action",
            "Decision Confidence",
            "Decision Drivers",
            "Investment Thesis",
            "Thesis Strengths",
            "Thesis Risks",
            "Thesis Catalysts",
            "Opportunity Score",
            "Conviction Score",
            "Investment Score",
            "Business Score",
            "Valuation Score",
            "Financial Score",
            "Timing Score",
            "Confidence Score",
            "Risk Penalty",
            "Deal Breakers",
        ]
        if column in df.columns
    ]

    explainability_df = build_explainability(df)
    diagnostics_df = build_diagnostics(df)

    historical_trends_df, history_summary_df = (
        _build_historical_reports(database_path)
    )

    with pd.ExcelWriter(
        history_file,
        engine="openpyxl",
    ) as writer:

        # --------------------------------------------------------------
        # Ranking
        # --------------------------------------------------------------
        df.to_excel(
            writer,
            sheet_name="Ranking",
            index=False,
        )

        # --------------------------------------------------------------
        # Summary
        # --------------------------------------------------------------
        if summary_columns:
            df[summary_columns].to_excel(
                writer,
                sheet_name="Summary",
                index=False,
            )

        # --------------------------------------------------------------
        # Opportunity Analysis
        # --------------------------------------------------------------
        if opportunity_columns:
            opportunity_df = df[
                opportunity_columns
            ].copy()

            if "Opportunity Score" in opportunity_df.columns:
                opportunity_df = opportunity_df.sort_values(
                    "Opportunity Score",
                    ascending=False,
                    na_position="last",
                )

            opportunity_df.to_excel(
                writer,
                sheet_name="Opportunity Analysis",
                index=False,
            )


        # --------------------------------------------------------------
        # Decision Analysis
        # --------------------------------------------------------------
        if decision_columns:
            decision_df = df[
                decision_columns
            ].copy()

            sort_columns = [
                column
                for column in [
                    "Decision Priority",
                    "Opportunity Score",
                    "Conviction Score",
                ]
                if column in df.columns
            ]

            if sort_columns:
                decision_df = decision_df.join(
                    df[
                        [
                            column
                            for column in sort_columns
                            if column not in decision_df.columns
                        ]
                    ]
                )

                ascending = [
                    True if column == "Decision Priority" else False
                    for column in sort_columns
                ]

                decision_df = decision_df.sort_values(
                    sort_columns,
                    ascending=ascending,
                    na_position="last",
                )

                if "Decision Priority" not in decision_columns:
                    decision_df = decision_df.drop(
                        columns=["Decision Priority"],
                        errors="ignore",
                    )

            decision_df.to_excel(
                writer,
                sheet_name="Decision Analysis",
                index=False,
            )

        # --------------------------------------------------------------
        # Explainability
        # --------------------------------------------------------------
        explainability_df.to_excel(
            writer,
            sheet_name="Explainability",
            index=False,
        )

        # --------------------------------------------------------------
        # Diagnostics
        # --------------------------------------------------------------
        if not diagnostics_df.empty:
            diagnostics_df.to_excel(
                writer,
                sheet_name="Diagnostics",
                index=False,
            )

        # --------------------------------------------------------------
        # Historical Trends
        # --------------------------------------------------------------
        if not historical_trends_df.empty:
            historical_trends_df.to_excel(
                writer,
                sheet_name="Historical Trends",
                index=False,
            )

        # --------------------------------------------------------------
        # History Summary
        # --------------------------------------------------------------
        if not history_summary_df.empty:
            history_summary_df.to_excel(
                writer,
                sheet_name="History Summary",
                index=False,
            )

        # --------------------------------------------------------------
        # Formatting
        # --------------------------------------------------------------
        for sheet_name in writer.sheets:
            _format_sheet(
                writer,
                sheet_name,
            )

    copied_file: Path | None = None

    try:
        shutil.copy2(
            history_file,
            latest_file,
        )

        copied_file = latest_file

    except PermissionError:
        print(
            "[AVISO] latest.xlsx está aberto. "
            "O arquivo histórico foi salvo normalmente."
        )

    return history_file, copied_file
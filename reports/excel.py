from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd

from reports.explainability import build_explainability
from reports.diagnostics import build_diagnostics


def _format_sheet(writer: pd.ExcelWriter, sheet_name: str) -> None:
    worksheet = writer.sheets.get(sheet_name)
    if worksheet is None:
        return

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_cells in worksheet.columns:
        max_length = 0
        col_letter = column_cells[0].column_letter

        for cell in column_cells:
            value = cell.value
            if value is not None:
                max_length = max(max_length, len(str(value)))

        worksheet.column_dimensions[col_letter].width = min(max_length + 2, 40)


def write_latest_and_history(df: pd.DataFrame, output_dir: Path) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)

    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    history_file = history_dir / f"atlas_snapshot_{stamp}.xlsx"
    latest_file = output_dir / "latest.xlsx"

    summary_cols = [
        c for c in [
            "symbol",
            "name",
            "Investment Score",
            "Business Score",
            "Valuation Score",
            "Financial Score",
            "Timing Score",
            "Confidence Score",
            "Recommendation",
        ]
        if c in df.columns
    ]

    explainability_df = build_explainability(df)
    diagnostics_df = build_diagnostics(df)

    with pd.ExcelWriter(history_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Ranking", index=False)

        if summary_cols:
            df[summary_cols].to_excel(writer, sheet_name="Summary", index=False)

        explainability_df.to_excel(writer, sheet_name="Explainability", index=False)

        if not diagnostics_df.empty:
            diagnostics_df.to_excel(writer, sheet_name="Diagnostics", index=False)

        for sheet_name in writer.sheets:
            _format_sheet(writer, sheet_name)

    copied = None

    try:
        shutil.copy2(history_file, latest_file)
        copied = latest_file
    except PermissionError:
        print("[AVISO] latest.xlsx está aberto. Histórico salvo normalmente.")

    return history_file, copied
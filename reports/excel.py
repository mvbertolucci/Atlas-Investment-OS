from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd


def write_latest_and_history(df: pd.DataFrame, output_dir: Path) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    history_file = history_dir / f"atlas_snapshot_{stamp}.xlsx"
    latest_file = output_dir / "latest.xlsx"

    with pd.ExcelWriter(history_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Ranking", index=False)
        summary_cols = [c for c in ["symbol", "name", "Investment Score", "Business Score", "Valuation Score", "Financial Score", "Timing Score", "Confidence Score", "Recommendation"] if c in df.columns]
        df[summary_cols].to_excel(writer, sheet_name="Summary", index=False)

    copied = None
    try:
        shutil.copy2(history_file, latest_file)
        copied = latest_file
    except PermissionError:
        print("[AVISO] latest.xlsx está aberto. Histórico salvo normalmente.")

    return history_file, copied

from __future__ import annotations

from pathlib import Path
import pandas as pd


def write_change_report(changes: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "change_report.xlsx"
    changes.to_excel(path, index=False)
    return path

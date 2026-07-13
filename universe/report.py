from __future__ import annotations

import json
from pathlib import Path

from universe.models import UniverseReport


def write_universe_report(
    report: UniverseReport,
    output_path: str | Path,
) -> Path:
    if not isinstance(report, UniverseReport):
        raise TypeError("report deve ser UniverseReport.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path

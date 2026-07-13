from __future__ import annotations

import json
from pathlib import Path

from priority.models import PriorityReport


def write_priority_report(
    report: PriorityReport,
    output_path: Path,
) -> Path:
    if not isinstance(report, PriorityReport):
        raise TypeError("report deve ser PriorityReport.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path

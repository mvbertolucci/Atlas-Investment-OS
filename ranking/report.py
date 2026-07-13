from __future__ import annotations

import json
from pathlib import Path

from ranking.models import RankingReport


def write_ranking_report(report: RankingReport, path: str | Path) -> Path:
    if not isinstance(report, RankingReport):
        raise TypeError("report deve ser RankingReport.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output

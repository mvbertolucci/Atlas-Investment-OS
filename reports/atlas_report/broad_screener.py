from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# Coleta de Mercado Amplo/ADR leva horas (milhares de símbolos, providers com
# rate limit) -- não pode rodar dentro de run_all.py --full a cada
# invocação. Este módulo só LÊ o resultado da última coleta manual
# (`python -m universe.collector`/pipeline via ranking/pipeline.py), a
# mesma fonte que reports/research_html.py já usa para os 3 screeners.
# Nunca dispara coleta nova.

_STALE_AFTER_DAYS = 35.0  # folga sobre a cadência mensal pretendida


@dataclass(frozen=True)
class BroadScreenerSummary:
    label: str
    included: bool
    stale: bool = False
    generated_at: str | None = None
    age_days: float | None = None
    total_count: int = 0
    universe_eligible_count: int = 0
    candidate_count: int = 0
    blocked_by_reason: dict[str, int] = field(default_factory=dict)
    top_candidates: tuple[dict[str, Any], ...] = ()


def load_broad_screener_summary(
    label: str,
    report_path: Path,
    *,
    as_of: pd.Timestamp,
    top_n: int = 10,
) -> BroadScreenerSummary:
    """
    Lê um `research_ranking_report_*.json` (mesmo formato que
    ranking/pipeline.py já persiste para o screener S&P500) e resume os
    top candidatos + idade da coleta. Arquivo ausente ou ilegível vira
    `included=False`, nunca um erro -- a coleta ampla é opcional e manual.
    """
    if not report_path.exists():
        return BroadScreenerSummary(label=label, included=False)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BroadScreenerSummary(label=label, included=False)

    generated_at = data.get("generated_at")
    age_days: float | None = None
    if generated_at:
        parsed = pd.to_datetime(generated_at, errors="coerce")
        if not pd.isna(parsed):
            age_days = round((as_of - parsed).total_seconds() / 86400, 1)

    summary = data.get("summary", {}) or {}
    candidates = sorted(
        (
            company
            for company in data.get("companies", ())
            if company.get("safeguard_passed") and company.get("candidate_rank") is not None
        ),
        key=lambda company: company.get("candidate_rank") or 10**9,
    )

    return BroadScreenerSummary(
        label=label,
        included=True,
        stale=age_days is not None and age_days > _STALE_AFTER_DAYS,
        generated_at=str(generated_at) if generated_at else None,
        age_days=age_days,
        total_count=int(summary.get("total_count", 0) or 0),
        universe_eligible_count=int(summary.get("universe_eligible_count", 0) or 0),
        candidate_count=int(summary.get("candidate_count", 0) or 0),
        blocked_by_reason=dict(summary.get("blocked_by_reason", {}) or {}),
        top_candidates=tuple(
            {
                "symbol": company.get("symbol", ""),
                "sector": company.get("sector", ""),
                "investment_score": company.get("investment_score", 0.0),
                "confidence_score": company.get("confidence_score", 0.0),
                "candidate_rank": company.get("candidate_rank", 0),
            }
            for company in candidates[:top_n]
        ),
    )

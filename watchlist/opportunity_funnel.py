from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from storage.atomic_write import atomic_write_json
from watchlist.auto_curation import select_auto_inclusion_candidates
from watchlist.auto_policy import WatchlistAutoPolicy


FUNNEL_CONTRACT_VERSION = "1.0"


@dataclass(frozen=True)
class OpportunityFunnel:
    generated_at: str
    sources: tuple[dict[str, Any], ...]
    unique_safeguarded_count: int
    qualified_count: int
    selected_count: int
    selected: tuple[dict[str, Any], ...]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": FUNNEL_CONTRACT_VERSION,
            "generated_at": self.generated_at,
            "sources": list(self.sources),
            "summary": {
                "unique_safeguarded_count": self.unique_safeguarded_count,
                "qualified_count": self.qualified_count,
                "selected_count": self.selected_count,
            },
            "policy": self.policy,
            "selected": list(self.selected),
        }


def build_opportunity_funnel(
    report_paths: Iterable[tuple[str, Path | None]],
    *,
    watchlist_symbols: Iterable[str],
    held_symbols: Iterable[str],
    policy: WatchlistAutoPolicy,
    generated_at: str | None = None,
) -> OpportunityFunnel:
    paths = tuple(report_paths)
    sources: list[dict[str, Any]] = []
    safeguarded_symbols: set[str] = set()
    for label, path in paths:
        source: dict[str, Any] = {"source": label, "available": False}
        if path is not None and Path(path).exists():
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                source["error"] = "unreadable"
            else:
                summary = data.get("summary") or {}
                companies = data.get("companies") or []
                passed = [item for item in companies if item.get("safeguard_passed")]
                safeguarded_symbols.update(
                    str(item.get("symbol", "")).strip().upper()
                    for item in passed
                    if str(item.get("symbol", "")).strip()
                )
                source.update(
                    available=True,
                    generated_at=data.get("generated_at"),
                    total_count=summary.get("total_count", len(companies)),
                    universe_eligible_count=summary.get("universe_eligible_count"),
                    candidate_count=summary.get("candidate_count", len(passed)),
                )
        sources.append(source)

    uncapped_policy = WatchlistAutoPolicy(
        selection={**policy.selection, "top_n": 1_000_000},
        exit=policy.exit,
        safeguards=policy.safeguards,
        enabled=policy.enabled,
    )
    qualified = select_auto_inclusion_candidates(
        paths,
        watchlist_symbols=watchlist_symbols,
        held_symbols=held_symbols,
        policy=uncapped_policy,
    )
    selected = qualified[: policy.top_n]
    return OpportunityFunnel(
        generated_at=generated_at or datetime.now().isoformat(timespec="seconds"),
        sources=tuple(sources),
        unique_safeguarded_count=len(safeguarded_symbols),
        qualified_count=len(qualified),
        selected_count=len(selected),
        selected=tuple(item.to_dict() for item in selected),
        policy={
            "enabled": policy.enabled,
            "top_n": policy.top_n,
            "qualifying_decisions": list(policy.qualifying_decisions),
            "min_confidence_score": policy.min_confidence_score,
            "review_sla_days": policy.review_sla_days,
        },
    )


def write_opportunity_funnel(
    funnel: OpportunityFunnel, output_path: str | Path
) -> Path:
    if not isinstance(funnel, OpportunityFunnel):
        raise TypeError("funnel deve ser OpportunityFunnel.")
    return atomic_write_json(
        output_path, funnel.to_dict(), ensure_ascii=False, indent=2
    )

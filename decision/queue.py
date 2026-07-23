from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any, Mapping

from storage.atomic_write import atomic_write_json


DECISION_QUEUE_VERSION = "1.0"


@dataclass(frozen=True)
class DecisionQueue:
    items: tuple[dict[str, Any], ...]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        groups = {name: [] for name in ("EXECUTE", "INVESTIGATE", "WAIT", "MONITOR")}
        for item in self.items:
            groups[str(item["group"])].append(dict(item))
        return {
            "contract_version": DECISION_QUEUE_VERSION,
            "generated_at": self.generated_at,
            "summary": {name.lower(): len(values) for name, values in groups.items()},
            "groups": groups,
            "items": [dict(item) for item in self.items],
        }


def build_decision_queue(
    *,
    priority: Mapping[str, Any] | None,
    active_watchlist: tuple[dict[str, Any], ...] = (),
    portfolio_actions: tuple[Mapping[str, Any], ...] = (),
    company_context: Mapping[str, Mapping[str, Any]] | None = None,
    generated_at: str | None = None,
) -> DecisionQueue:
    items: list[dict[str, Any]] = []
    context_by_symbol = {
        str(symbol).upper(): dict(context)
        for symbol, context in (company_context or {}).items()
    }

    def enrich(item: dict[str, Any]) -> dict[str, Any]:
        context = context_by_symbol.get(str(item["symbol"]).upper(), {})
        return {
            **item,
            "company_name": str(context.get("company_name", "")),
            "investment_thesis": str(context.get("investment_thesis", "")),
            "opportunity_score": context.get("opportunity_score"),
            "conviction_score": context.get("conviction_score"),
            "decision_confidence": context.get("decision_confidence"),
            "data_coverage": context.get("data_coverage"),
            "risk_penalty": context.get("risk_penalty"),
        }
    sell_items = ((priority or {}).get("sell") or {}).get("items") or []
    for raw in sell_items:
        action = str(raw.get("action", "")).upper()
        if action in {"SELL", "TRIM"}:
            group, rank = "EXECUTE", 0
        elif action == "REVISAR":
            group, rank = "INVESTIGATE", 10
        elif action == "HOLD":
            group, rank = "MONITOR", 40
        else:
            continue
        items.append(enrich(
            {
                "symbol": str(raw.get("symbol", "")).upper(),
                "group": group,
                "action": action,
                "reason": str(raw.get("reason", "")),
                "engine": "portfolio.sell_rules",
                "priority": int(raw.get("priority", rank)),
                "investment_score": raw.get("investment_score"),
                "current_weight": raw.get("current_weight"),
                "advisory_only": True,
            }
        ))

    existing_portfolio_symbols = {
        str(item["symbol"]) for item in items if item["engine"] == "portfolio.sell_rules"
    }
    for raw in portfolio_actions:
        symbol = str(raw.get("symbol", "")).upper()
        if str(raw.get("action", "")).upper() != "ACOMPANHAR" or symbol in existing_portfolio_symbols:
            continue
        items.append(enrich(
            {
                "symbol": symbol,
                "group": "MONITOR",
                "action": "ACOMPANHAR",
                "reason": str(raw.get("reason", "")),
                "engine": "portfolio.sell_rules",
                "priority": 45,
                "current_weight": raw.get("current_weight"),
                "advisory_only": True,
            }
        ))

    state_map = {
        "promotion_ready": ("EXECUTE", "REVIEW_FOR_PURCHASE", 5),
        "review_required": ("INVESTIGATE", "REVIEW", 20),
        "discard_review": ("INVESTIGATE", "REVIEW_DISCARD", 25),
        "waiting_trigger": ("WAIT", "WAIT_TRIGGER", 30),
        "analyzing": ("MONITOR", "ANALYZE", 35),
        "monitoring": ("MONITOR", "MONITOR", 40),
    }
    for raw in active_watchlist:
        state = str(raw.get("effective_state", "monitoring"))
        group, action, rank = state_map.get(state, state_map["monitoring"])
        items.append(enrich(
            {
                "symbol": str(raw.get("symbol", "")).upper(),
                "group": group,
                "action": action,
                "reason": str(raw.get("state_reason", "")),
                "engine": "watchlist.active_queue",
                "priority": rank,
                "analytical_origin": raw.get("analytical_origin"),
                "entry_rank": raw.get("entry_rank"),
                "entry_score": raw.get("entry_score"),
                "review_due_at": raw.get("review_due_at"),
                "advisory_only": True,
            }
        ))
    items.sort(key=lambda item: (int(item["priority"]), str(item["symbol"])))
    queue_generated_at = generated_at or datetime.now().isoformat(timespec="seconds")
    for item in items:
        identity = "|".join(
            (
                queue_generated_at,
                str(item["symbol"]),
                str(item["action"]),
                str(item["engine"]),
            )
        )
        item["decision_id"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return DecisionQueue(
        items=tuple(items),
        generated_at=queue_generated_at,
    )


def write_decision_queue(queue: DecisionQueue, path: str | Path) -> Path:
    if not isinstance(queue, DecisionQueue):
        raise TypeError("queue deve ser DecisionQueue.")
    return atomic_write_json(path, queue.to_dict(), ensure_ascii=False, indent=2)

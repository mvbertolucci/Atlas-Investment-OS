from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from storage.atomic_write import atomic_write_json


DECISION_DELTA_VERSION = "1.0"

# Campos numéricos comparados entre execuções. `current_weight` fica de fora
# de propósito: peso oscila com preço a cada run e viraria ruído permanente.
SCORE_FIELDS = (
    "investment_score",
    "opportunity_score",
    "conviction_score",
    "decision_confidence",
    "data_coverage",
    "risk_penalty",
)
DEFAULT_SCORE_THRESHOLD = 5.0

_SNAPSHOT_PREFIX = "decision_queue_"


@dataclass(frozen=True)
class DecisionDelta:
    generated_at: str
    baseline_generated_at: str | None
    entered: tuple[dict[str, Any], ...]
    exited: tuple[dict[str, Any], ...]
    changed: tuple[dict[str, Any], ...]
    action_transitions: tuple[dict[str, Any], ...]
    unchanged_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": DECISION_DELTA_VERSION,
            "generated_at": self.generated_at,
            "baseline_generated_at": self.baseline_generated_at,
            "summary": {
                "entered": len(self.entered),
                "exited": len(self.exited),
                "changed": len(self.changed),
                "action_transitions": len(self.action_transitions),
                "unchanged": self.unchanged_count,
            },
            "entered": [dict(item) for item in self.entered],
            "exited": [dict(item) for item in self.exited],
            "changed": [dict(item) for item in self.changed],
            "action_transitions": [dict(item) for item in self.action_transitions],
        }


def _identity_fields(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": str(item.get("decision_id", "")),
        "symbol": str(item.get("symbol", "")),
        "company_name": str(item.get("company_name", "")),
        "action": str(item.get("action", "")),
        "engine": str(item.get("engine", "")),
        "group": str(item.get("group", "")),
        "reason": str(item.get("reason", "")),
    }


def _score_change(
    before: Any,
    after: Any,
    threshold: float,
) -> dict[str, Any] | None:
    if before is None and after is None:
        return None
    if before is None or after is None:
        # Evidência apareceu ou sumiu — sempre material, independe do limiar.
        return {"from": before, "to": after}
    difference = float(after) - float(before)
    if abs(difference) < threshold:
        return None
    return {"from": before, "to": after, "delta": round(difference, 1)}


def _item_changes(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    threshold: float,
) -> tuple[dict[str, Any], ...]:
    changes: list[dict[str, Any]] = []
    if str(previous.get("group", "")) != str(current.get("group", "")):
        changes.append(
            {
                "field": "group",
                "from": str(previous.get("group", "")),
                "to": str(current.get("group", "")),
            }
        )
    for field in SCORE_FIELDS:
        moved = _score_change(previous.get(field), current.get(field), threshold)
        if moved is not None:
            changes.append({"field": field, **moved})
    previous_thesis = str(previous.get("investment_thesis", "") or "")
    current_thesis = str(current.get("investment_thesis", "") or "")
    if previous_thesis != current_thesis:
        changes.append(
            {
                "field": "investment_thesis",
                "from": previous_thesis,
                "to": current_thesis,
            }
        )
    return tuple(changes)


def build_decision_delta(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    *,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> DecisionDelta:
    generated_at = str(current.get("generated_at", ""))
    current_items = {
        str(item["decision_id"]): item for item in current.get("items", [])
    }
    if previous is None:
        return DecisionDelta(
            generated_at=generated_at,
            baseline_generated_at=None,
            entered=(),
            exited=(),
            changed=(),
            action_transitions=(),
            unchanged_count=0,
        )

    previous_items = {
        str(item["decision_id"]): item for item in previous.get("items", [])
    }
    entered_ids = sorted(set(current_items) - set(previous_items))
    exited_ids = sorted(set(previous_items) - set(current_items))

    # Como a identidade é symbol|action|engine (ADR-040), uma escalação de ação
    # (ex.: REVISAR -> SELL) aparece como saiu+entrou. Parear por
    # (symbol, engine) transforma esse par no sinal mais importante do delta.
    entered_by_key = {
        (str(current_items[i]["symbol"]), str(current_items[i]["engine"])): i
        for i in entered_ids
    }
    exited_by_key = {
        (str(previous_items[i]["symbol"]), str(previous_items[i]["engine"])): i
        for i in exited_ids
    }
    transitions: list[dict[str, Any]] = []
    for key in sorted(set(entered_by_key) & set(exited_by_key)):
        current_item = current_items[entered_by_key[key]]
        previous_item = previous_items[exited_by_key[key]]
        transitions.append(
            {
                **_identity_fields(current_item),
                "from_action": str(previous_item.get("action", "")),
                "from_group": str(previous_item.get("group", "")),
            }
        )
        entered_ids.remove(entered_by_key[key])
        exited_ids.remove(exited_by_key[key])

    changed: list[dict[str, Any]] = []
    unchanged = 0
    for decision_id in sorted(set(current_items) & set(previous_items)):
        item_changes = _item_changes(
            previous_items[decision_id],
            current_items[decision_id],
            score_threshold,
        )
        if item_changes:
            changed.append(
                {
                    **_identity_fields(current_items[decision_id]),
                    "changes": [dict(change) for change in item_changes],
                }
            )
        else:
            unchanged += 1

    return DecisionDelta(
        generated_at=generated_at,
        baseline_generated_at=str(previous.get("generated_at", "")),
        entered=tuple(
            _identity_fields(current_items[i]) for i in entered_ids
        ),
        exited=tuple(
            _identity_fields(previous_items[i]) for i in exited_ids
        ),
        changed=tuple(changed),
        action_transitions=tuple(transitions),
        unchanged_count=unchanged,
    )


def find_previous_snapshot(
    history_dir: str | Path,
    *,
    before_generated_at: str,
) -> dict[str, Any] | None:
    """Localiza o snapshot mais recente anterior à execução corrente.

    O carimbo no nome do arquivo é o `generated_at` ISO com `:` trocado por
    `-`, o que preserva a ordem lexicográfica — só o escolhido é carregado.
    """
    directory = Path(history_dir)
    if not directory.exists():
        return None
    current_stamp = before_generated_at.replace(":", "-")
    best: tuple[str, Path] | None = None
    for path in directory.glob(f"{_SNAPSHOT_PREFIX}*.json"):
        stamp = path.stem[len(_SNAPSHOT_PREFIX):]
        if stamp < current_stamp and (best is None or stamp > best[0]):
            best = (stamp, path)
    if best is None:
        return None
    return json.loads(best[1].read_text(encoding="utf-8"))


def write_decision_delta(delta: DecisionDelta, path: str | Path) -> Path:
    if not isinstance(delta, DecisionDelta):
        raise TypeError("delta deve ser DecisionDelta.")
    return atomic_write_json(path, delta.to_dict(), ensure_ascii=False, indent=2)

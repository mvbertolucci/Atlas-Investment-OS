from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from storage.atomic_write import atomic_write_json


JOURNAL_VERSION = "1.0"
DECISION_STATUSES = ("ACCEPTED", "REJECTED", "DEFERRED")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_PATH = ROOT / "output" / "dados" / "decision_queue.json"
DEFAULT_JOURNAL_PATH = ROOT / "output" / "dados" / "decision_journal.json"


@dataclass(frozen=True)
class JournalEvent:
    event_id: str
    decision_id: str
    recorded_at: str
    status: str
    reason: str
    symbol: str
    action: str
    engine: str
    queue_generated_at: str

    def to_dict(self) -> dict[str, str]:
        return dict(vars(self))


def load_journal(path: str | Path = DEFAULT_JOURNAL_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"contract_version": JOURNAL_VERSION, "events": []}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("contract_version") != JOURNAL_VERSION:
        raise ValueError("versão incompatível do Decision Journal.")
    if not isinstance(payload.get("events"), list):
        raise ValueError("Decision Journal inválido: events deve ser lista.")
    return payload


def record_decision(
    decision: dict[str, Any],
    *,
    queue_generated_at: str,
    status: str,
    reason: str,
    journal_path: str | Path = DEFAULT_JOURNAL_PATH,
    recorded_at: str | None = None,
) -> JournalEvent:
    normalized_status = status.strip().upper()
    if normalized_status not in DECISION_STATUSES:
        raise ValueError(f"status deve ser um de {DECISION_STATUSES}.")
    reason = reason.strip()
    if not reason:
        raise ValueError("reason não pode ser vazio.")
    decision_id = str(decision.get("decision_id") or "").strip()
    if not decision_id:
        raise ValueError("decisão sem decision_id.")
    timestamp = recorded_at or datetime.now().isoformat(timespec="seconds")
    event_identity = f"{decision_id}|{timestamp}|{normalized_status}|{reason}"
    event = JournalEvent(
        event_id=hashlib.sha256(event_identity.encode("utf-8")).hexdigest()[:20],
        decision_id=decision_id,
        recorded_at=timestamp,
        status=normalized_status,
        reason=reason,
        symbol=str(decision.get("symbol", "")).upper(),
        action=str(decision.get("action", "")).upper(),
        engine=str(decision.get("engine", "")),
        queue_generated_at=queue_generated_at,
    )
    payload = load_journal(journal_path)
    if any(item.get("event_id") == event.event_id for item in payload["events"]):
        raise ValueError("evento já registrado no Decision Journal.")
    payload["events"].append(event.to_dict())
    atomic_write_json(journal_path, payload, ensure_ascii=False, indent=2)
    return event


def journal_summary(payload: dict[str, Any]) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    for event in payload.get("events", []):
        latest[str(event["decision_id"])] = event
    counts = {status.lower(): 0 for status in DECISION_STATUSES}
    for event in latest.values():
        counts[str(event["status"]).lower()] += 1
    return {"total_events": len(payload.get("events", [])), "latest_decisions": len(latest), **counts}


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Registra revisão humana da Decision Queue.")
    parser.add_argument("decision_id")
    parser.add_argument("status", choices=DECISION_STATUSES)
    parser.add_argument("reason")
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    args = parser.parse_args(list(argv) if argv is not None else None)
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    decision = next(
        (item for item in queue.get("items", []) if item.get("decision_id") == args.decision_id),
        None,
    )
    if decision is None:
        parser.error("decision_id não encontrado na Decision Queue.")
    event = record_decision(
        decision,
        queue_generated_at=str(queue.get("generated_at", "")),
        status=args.status,
        reason=args.reason,
        journal_path=args.journal,
    )
    print(f"{event.status}: {event.symbol} {event.action} ({event.event_id})")


if __name__ == "__main__":
    main()

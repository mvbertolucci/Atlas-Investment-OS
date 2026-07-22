from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from decision.journal import DEFAULT_JOURNAL_PATH, load_journal
from decision.journal import DEFAULT_QUEUE_PATH
from storage.atomic_write import atomic_write_json


LEDGER_VERSION = "1.0"
SUPPORTED_ACTIONS = ("SELL", "TRIM")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER_PATH = ROOT / "output" / "dados" / "execution_ledger.json"


@dataclass(frozen=True)
class ExecutionEvent:
    execution_id: str
    decision_id: str
    recorded_at: str
    executed_at: str
    symbol: str
    action: str
    quantity: float
    price: float
    fees: float
    currency: str
    gross_value: float
    net_cash_delta: float

    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def load_execution_ledger(path: str | Path = DEFAULT_LEDGER_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"contract_version": LEDGER_VERSION, "events": []}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("contract_version") != LEDGER_VERSION:
        raise ValueError("versão incompatível do Execution Ledger.")
    if not isinstance(payload.get("events"), list):
        raise ValueError("Execution Ledger inválido: events deve ser lista.")
    return payload


def _positive_decimal(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} deve ser numérico.") from None
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        comparator = "maior ou igual a zero" if allow_zero else "maior que zero"
        raise ValueError(f"{field} deve ser {comparator}.")
    return number


def _latest_journal_status(journal: dict[str, Any], decision_id: str) -> str | None:
    latest = None
    for event in journal.get("events", []):
        if str(event.get("decision_id")) == decision_id:
            latest = str(event.get("status", "")).upper()
    return latest


def record_execution(
    decision: dict[str, Any],
    *,
    journal: dict[str, Any],
    quantity: object,
    price: object,
    fees: object = 0,
    currency: str = "USD",
    executed_at: str,
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    recorded_at: str | None = None,
) -> ExecutionEvent:
    decision_id = str(decision.get("decision_id") or "").strip()
    if not decision_id:
        raise ValueError("decisão sem decision_id.")
    action = str(decision.get("action", "")).upper()
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"action deve ser uma de {SUPPORTED_ACTIONS}.")
    if _latest_journal_status(journal, decision_id) != "ACCEPTED":
        raise ValueError("decisão precisa ter status mais recente ACCEPTED.")
    if not str(executed_at).strip():
        raise ValueError("executed_at não pode ser vazio.")
    quantity_decimal = _positive_decimal(quantity, "quantity")
    price_decimal = _positive_decimal(price, "price")
    fees_decimal = _positive_decimal(fees, "fees", allow_zero=True)
    gross = quantity_decimal * price_decimal
    net = gross - fees_decimal
    if net < 0:
        raise ValueError("fees não pode superar o valor bruto.")
    normalized_currency = currency.strip().upper()
    if not normalized_currency:
        raise ValueError("currency não pode ser vazio.")
    timestamp = recorded_at or datetime.now().isoformat(timespec="seconds")
    identity = "|".join(
        (decision_id, str(executed_at), str(quantity_decimal), str(price_decimal),
         str(fees_decimal), normalized_currency)
    )
    event = ExecutionEvent(
        execution_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        decision_id=decision_id,
        recorded_at=timestamp,
        executed_at=str(executed_at),
        symbol=str(decision.get("symbol", "")).upper(),
        action=action,
        quantity=float(quantity_decimal),
        price=float(price_decimal),
        fees=float(fees_decimal),
        currency=normalized_currency,
        gross_value=float(gross),
        net_cash_delta=float(net),
    )
    payload = load_execution_ledger(ledger_path)
    if any(item.get("execution_id") == event.execution_id for item in payload["events"]):
        raise ValueError("execução já registrada no Execution Ledger.")
    payload["events"].append(event.to_dict())
    atomic_write_json(ledger_path, payload, ensure_ascii=False, indent=2)
    return event


def execution_summary(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("events", [])
    return {
        "fills": len(events),
        "decisions_executed": len({str(item.get("decision_id")) for item in events}),
        "gross_sell_value": round(sum(float(item.get("gross_value", 0)) for item in events), 2),
        "fees": round(sum(float(item.get("fees", 0)) for item in events), 2),
        "net_cash_delta": round(sum(float(item.get("net_cash_delta", 0)) for item in events), 2),
    }


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Registra execução real informada explicitamente.")
    parser.add_argument("decision_id")
    parser.add_argument("quantity")
    parser.add_argument("price")
    parser.add_argument("executed_at")
    parser.add_argument("--fees", default="0")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    args = parser.parse_args(list(argv) if argv is not None else None)
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    decision = next(
        (item for item in queue.get("items", []) if item.get("decision_id") == args.decision_id), None
    )
    if decision is None:
        parser.error("decision_id não encontrado na Decision Queue.")
    try:
        event = record_execution(
            decision, journal=load_journal(args.journal), quantity=args.quantity,
            price=args.price, fees=args.fees, currency=args.currency,
            executed_at=args.executed_at, ledger_path=args.ledger,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"EXECUTED: {event.symbol} {event.action} {event.quantity} @ {event.price} ({event.execution_id})")


if __name__ == "__main__":
    main()

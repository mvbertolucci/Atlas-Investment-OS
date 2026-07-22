from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from decision.execution import DEFAULT_LEDGER_PATH, load_execution_ledger
from storage.atomic_write import atomic_write_json


RECONCILIATION_VERSION = "1.0"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECONCILIATION_PATH = ROOT / "output" / "dados" / "execution_reconciliation.json"
STATUSES = ("CONFIRMED", "PARTIAL", "NOT_REFLECTED", "VARIANCE", "UNVERIFIABLE")


@dataclass(frozen=True)
class ExecutionReconciliation:
    generated_at: str
    baseline_snapshot_at: str
    current_snapshot_at: str
    items: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        counts = {status.lower(): 0 for status in STATUSES}
        for item in self.items:
            counts[str(item["status"]).lower()] += 1
        return {
            "contract_version": RECONCILIATION_VERSION,
            "generated_at": self.generated_at,
            "baseline_snapshot_at": self.baseline_snapshot_at,
            "current_snapshot_at": self.current_snapshot_at,
            "summary": {"symbols": len(self.items), **counts},
            "items": [dict(item) for item in self.items],
        }


def _holdings(payload: Mapping[str, Any]) -> dict[str, float]:
    rows = payload.get("holdings")
    if not isinstance(rows, list):
        raise ValueError("snapshot de carteira deve conter holdings como lista.")
    result: dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        try:
            quantity = float(row.get("quantity"))
        except (TypeError, ValueError):
            raise ValueError(f"quantity inválida para {symbol}.") from None
        if quantity < 0:
            raise ValueError(f"quantity inválida para {symbol}.")
        result[symbol] = result.get(symbol, 0.0) + quantity
    return result


def reconcile_executions(
    ledger: Mapping[str, Any],
    *,
    baseline_portfolio: Mapping[str, Any],
    current_portfolio: Mapping[str, Any],
    baseline_snapshot_at: str,
    current_snapshot_at: str,
    tolerance: float = 1e-6,
    generated_at: str | None = None,
) -> ExecutionReconciliation:
    if tolerance < 0:
        raise ValueError("tolerance deve ser maior ou igual a zero.")
    baseline = _holdings(baseline_portfolio)
    current = _holdings(current_portfolio)
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for event in ledger.get("events", []):
        if str(event.get("action", "")).upper() not in {"SELL", "TRIM"}:
            continue
        executed_at = str(event.get("executed_at", ""))
        if baseline_snapshot_at and executed_at and executed_at <= baseline_snapshot_at:
            continue
        if current_snapshot_at and executed_at and executed_at > current_snapshot_at:
            continue
        grouped.setdefault(str(event.get("symbol", "")).upper(), []).append(event)

    items: list[dict[str, Any]] = []
    for symbol in sorted(grouped):
        events = grouped[symbol]
        expected = sum(float(event.get("quantity", 0)) for event in events)
        before = baseline.get(symbol)
        after = current.get(symbol, 0.0)
        if before is None:
            observed = None
            variance = None
            status = "UNVERIFIABLE"
            reason = "Símbolo ausente no snapshot-base; redução não pode ser medida."
        else:
            observed = before - after
            variance = observed - expected
            if abs(variance) <= tolerance:
                status, reason = "CONFIRMED", "Redução observada coincide com os fills registrados."
            elif observed <= tolerance:
                status, reason = "NOT_REFLECTED", "Nenhuma redução compatível apareceu na carteira atual."
            elif 0 < observed < expected - tolerance:
                status, reason = "PARTIAL", "A carteira reflete apenas parte da quantidade executada."
            else:
                status, reason = "VARIANCE", "A variação da posição excede ou diverge dos fills registrados."
        items.append({
            "symbol": symbol,
            "decision_ids": sorted({str(event.get("decision_id", "")) for event in events}),
            "execution_ids": [str(event.get("execution_id", "")) for event in events],
            "expected_reduction": round(expected, 8),
            "baseline_quantity": before,
            "current_quantity": after,
            "observed_reduction": None if observed is None else round(observed, 8),
            "quantity_variance": None if variance is None else round(variance, 8),
            "status": status,
            "reason": reason,
        })
    return ExecutionReconciliation(
        generated_at=generated_at or datetime.now().isoformat(timespec="seconds"),
        baseline_snapshot_at=baseline_snapshot_at,
        current_snapshot_at=current_snapshot_at,
        items=tuple(items),
    )


def write_execution_reconciliation(report: ExecutionReconciliation, path: str | Path) -> Path:
    if not isinstance(report, ExecutionReconciliation):
        raise TypeError("report deve ser ExecutionReconciliation.")
    return atomic_write_json(path, report.to_dict(), ensure_ascii=False, indent=2)


def load_reconciliation_summary(path: str | Path = DEFAULT_RECONCILIATION_PATH) -> dict[str, Any] | None:
    source = Path(path)
    if not source.exists():
        return None
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("contract_version") != RECONCILIATION_VERSION:
        raise ValueError("versão incompatível da reconciliação de execução.")
    return dict(payload.get("summary") or {})


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Reconcilia fills com dois snapshots de carteira.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--baseline-at", required=True)
    parser.add_argument("--current-at", required=True)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECONCILIATION_PATH)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = reconcile_executions(
        load_execution_ledger(args.ledger),
        baseline_portfolio=json.loads(args.baseline.read_text(encoding="utf-8")),
        current_portfolio=json.loads(args.current.read_text(encoding="utf-8")),
        baseline_snapshot_at=args.baseline_at,
        current_snapshot_at=args.current_at,
        tolerance=args.tolerance,
    )
    write_execution_reconciliation(report, args.output)
    summary = report.to_dict()["summary"]
    print(f"RECONCILED: {summary['symbols']} símbolos; {summary['confirmed']} confirmados")


if __name__ == "__main__":
    main()

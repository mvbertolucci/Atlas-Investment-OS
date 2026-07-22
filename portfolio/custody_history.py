from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from storage.atomic_write import atomic_write_json


CUSTODY_HISTORY_VERSION = "1.0"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CUSTODY_HISTORY_PATH = ROOT / "output" / "dados" / "portfolio_custody_history.json"


def load_custody_history(path: str | Path = DEFAULT_CUSTODY_HISTORY_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"contract_version": CUSTODY_HISTORY_VERSION, "snapshots": []}
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("contract_version") != CUSTODY_HISTORY_VERSION:
        raise ValueError("versão incompatível do histórico de custódia.")
    if not isinstance(payload.get("snapshots"), list):
        raise ValueError("histórico de custódia inválido: snapshots deve ser lista.")
    return payload


def capture_custody_snapshot(
    portfolio: Mapping[str, Any],
    *,
    history_path: str | Path = DEFAULT_CUSTODY_HISTORY_PATH,
) -> dict[str, Any]:
    snapshot_at = str(portfolio.get("generated_at") or "").strip()
    if not snapshot_at:
        raise ValueError("portfolio exige generated_at para snapshot de custódia.")
    rows = portfolio.get("holdings")
    if not isinstance(rows, (list, tuple)):
        raise ValueError("portfolio exige holdings para snapshot de custódia.")
    holdings = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        quantity = float(row.get("quantity"))
        if quantity < 0:
            raise ValueError(f"quantity inválida para {symbol}.")
        holdings.append({"symbol": symbol, "quantity": quantity})
    holdings.sort(key=lambda item: item["symbol"])
    identity = json.dumps(
        {"snapshot_at": snapshot_at, "holdings": holdings},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    snapshot = {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "snapshot_at": snapshot_at,
        "portfolio_name": str(portfolio.get("portfolio_name") or ""),
        "holdings": holdings,
    }
    payload = load_custody_history(history_path)
    if not any(item.get("snapshot_id") == snapshot["snapshot_id"] for item in payload["snapshots"]):
        payload["snapshots"].append(snapshot)
        payload["snapshots"].sort(key=lambda item: str(item.get("snapshot_at", "")))
        atomic_write_json(history_path, payload, ensure_ascii=False, indent=2)
    return snapshot


def custody_history_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    snapshots = payload.get("snapshots") or []
    return {
        "snapshots": len(snapshots),
        "latest_snapshot_at": str(snapshots[-1].get("snapshot_at", "")) if snapshots else None,
        "reconciliation_ready": len(snapshots) >= 2,
    }

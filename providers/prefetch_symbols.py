from __future__ import annotations

import csv
import json
from pathlib import Path


def load_symbols(path: str | Path) -> list[str]:
    source = Path(path)
    if source.suffix.casefold() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        members = payload.get("members") if isinstance(payload, dict) else None
        if not isinstance(members, list):
            raise ValueError("Prefetch exige JSON com lista members.")
        return sorted(
            {
                str(member.get("symbol") or "").strip().upper()
                for member in members
                if isinstance(member, dict)
                and member.get("eligible") is True
                and str(member.get("symbol") or "").strip()
            }
        )
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames:
            raise ValueError("Prefetch exige CSV com cabeçalho symbol.")
        symbol_field = next(
            (
                field
                for field in rows.fieldnames
                if str(field).strip().casefold() == "symbol"
            ),
            None,
        )
        if symbol_field is None:
            raise ValueError("Prefetch exige coluna symbol.")
        return sorted(
            {
                str(row.get(symbol_field) or "").strip().upper()
                for row in rows
            if str(row.get(symbol_field) or "").strip()
        }
        )

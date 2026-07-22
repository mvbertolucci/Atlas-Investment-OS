from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from storage.atomic_write import atomic_write_json


@dataclass(frozen=True)
class HistoricalReadinessReport:
    status: str
    price_file_count: int
    price_symbols: tuple[str, ...]
    price_start: str | None
    price_end: str | None
    universe_member_count: int | None
    price_coverage: float | None
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "price_file_count": self.price_file_count,
            "price_symbols": list(self.price_symbols),
            "price_start": self.price_start,
            "price_end": self.price_end,
            "universe_member_count": self.universe_member_count,
            "price_coverage": self.price_coverage,
            "blockers": list(self.blockers),
        }


def _dates_from_csv(path: Path) -> tuple[date, date] | None:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(handle)
            dates = [
                date.fromisoformat(str(row["Date"])[:10])
                for row in rows
                if row.get("Date")
            ]
    except (OSError, KeyError, ValueError):
        return None
    return (min(dates), max(dates)) if dates else None


def audit_historical_readiness(
    *,
    price_dir: str | Path,
    universe_manifest_path: str | Path | None = None,
    point_in_time_dataset_path: str | Path | None = None,
    execution_evidence_path: str | Path | None = None,
    total_return_evidence_path: str | Path | None = None,
    benchmark_symbol: str = "SPY",
) -> HistoricalReadinessReport:
    price_path = Path(price_dir)
    price_files = sorted(price_path.glob("*.csv")) if price_path.exists() else []
    symbols = tuple(path.stem.upper() for path in price_files)
    ranges = [item for item in (_dates_from_csv(path) for path in price_files) if item]
    universe_count: int | None = None
    if universe_manifest_path and Path(universe_manifest_path).exists():
        try:
            manifest = json.loads(Path(universe_manifest_path).read_text(encoding="utf-8"))
            universe_count = int(manifest["constituent_count"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            universe_count = None

    blockers: list[str] = []
    if not point_in_time_dataset_path or not Path(point_in_time_dataset_path).exists():
        blockers.append("POINT_IN_TIME_FUNDAMENTALS_MISSING")
    if not execution_evidence_path or not Path(execution_evidence_path).exists():
        blockers.append("EXECUTION_EVIDENCE_MISSING")
    if not total_return_evidence_path or not Path(total_return_evidence_path).exists():
        blockers.append("TOTAL_RETURN_EVIDENCE_MISSING")
    if benchmark_symbol.upper() not in symbols:
        blockers.append(f"BENCHMARK_PRICE_MISSING:{benchmark_symbol.upper()}")
    if universe_count is None:
        blockers.append("UNIVERSE_MANIFEST_MISSING")

    coverage = round(len(set(symbols)) / universe_count, 4) if universe_count else None
    return HistoricalReadinessReport(
        status="READY" if not blockers else "BLOCKED",
        price_file_count=len(price_files),
        price_symbols=symbols,
        price_start=min(item[0] for item in ranges).isoformat() if ranges else None,
        price_end=max(item[1] for item in ranges).isoformat() if ranges else None,
        universe_member_count=universe_count,
        price_coverage=coverage,
        blockers=tuple(blockers),
    )


def write_readiness_report(report: HistoricalReadinessReport, output_path: str | Path) -> Path:
    # This repository lives under OneDrive, which can transiently lock a
    # file mid-write (WinError 5); a plain write_text() has caused real
    # incidents twice before (ADR-032). atomic_write_json is the shared
    # write-then-replace-with-retry helper every other call site uses.
    return atomic_write_json(output_path, report.to_dict(), indent=2)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Audita a prontidão do backtest histórico.")
    parser.add_argument("--price-dir", required=True)
    parser.add_argument("--universe-manifest")
    parser.add_argument("--point-in-time-dataset")
    parser.add_argument("--execution-evidence")
    parser.add_argument("--total-return-evidence")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = audit_historical_readiness(
        price_dir=args.price_dir,
        universe_manifest_path=args.universe_manifest,
        point_in_time_dataset_path=args.point_in_time_dataset,
        execution_evidence_path=args.execution_evidence,
        total_return_evidence_path=args.total_return_evidence,
        benchmark_symbol=args.benchmark,
    )
    write_readiness_report(report, args.output)
    print(f"Prontidão histórica: {report.status}; bloqueios: {len(report.blockers)}")


if __name__ == "__main__":
    main()

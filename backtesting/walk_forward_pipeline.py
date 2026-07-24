"""Cola executável do walk-forward: da coleta SEC ao relatório reproduzido.

Todas as peças já existiam como biblioteca -- `point_in_time.py` (dataset com
corte anti-look-ahead), `walk_forward.py` (motor determinístico),
`sec_edgar_collector.py` (coleta retomável) -- mas nenhuma tinha CLI, e o
backtest nunca havia rodado ponta a ponta. Este módulo monta o pipeline:

  data/sec_edgar_collection.json      (fatos XBRL com data de arquivamento)
  + sp500_constituents_YYYY-MM-DD.csv (universo point-in-time, com CIK)
  -> PointInTimeDataset -> run_walk_forward -> walk_forward_report.json

O que ele NÃO faz, por honestidade do contrato point-in-time:
- não inventa memberships históricos: o snapshot de constituintes é de uma
  única data, então cada símbolo entra com `effective_from` naquela data;
- não preenche delistings: os símbolos sem histórico de preço são contados
  em `unresolved_delisting_count`, não escondidos.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from backtesting.point_in_time import (
    HistoricalObservation,
    PointInTimeDataset,
    StockSplitRecord,
    UniverseMembership,
)
from backtesting.price_history import (
    extract_price_observations,
    extract_split_records,
)
from backtesting.walk_forward import (
    HistoricalInputManifest,
    compute_governed_config_hashes,
    monthly_decision_calendar,
    run_walk_forward,
    write_walk_forward_report,
)

ROOT = Path(__file__).resolve().parents[1]


def load_observations(state_path: str | Path) -> tuple[HistoricalObservation, ...]:
    """Observações do checkpoint da coleta SEC, já no contrato do dataset.

    O checkpoint serializa exatamente os campos de `HistoricalObservation`
    (symbol/field_name/value/observed_on/available_at/source/revision_id),
    então a validação do __post_init__ -- inclusive `available_at` nunca
    anteceder `observed_on` -- roda de novo aqui, na fronteira de leitura.
    """
    state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    return tuple(
        HistoricalObservation(**observation)
        for observations in state.get("observations_by_symbol", {}).values()
        for observation in observations
    )


def load_memberships(
    constituents_csv: str | Path,
    *,
    effective_from: str,
) -> tuple[UniverseMembership, ...]:
    """Uma membership por constituinte, efetiva na data do snapshot.

    O snapshot da Wikipedia é de UMA data; não sabemos quando cada empresa
    entrou no índice antes disso, e inventar `effective_from` mais antigo
    fabricaria conhecimento. Decisões só são reproduzidas a partir da data
    do snapshot, que é o recorte honesto possível com esta fonte.
    """
    with Path(constituents_csv).open(encoding="utf-8", newline="") as handle:
        symbols = tuple(
            row["symbol"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("symbol", "").strip()
        )
    known_at = f"{effective_from}T00:00:00+00:00"
    return tuple(
        UniverseMembership(
            symbol=symbol,
            effective_from=effective_from,
            known_at=known_at,
            source=Path(constituents_csv).name,
        )
        for symbol in symbols
    )


def load_price_observations(
    price_dir: str | Path,
) -> tuple[tuple[HistoricalObservation, ...], tuple[StockSplitRecord, ...]]:
    """Preços diários e splits, do disco para o contrato do dataset.

    Sem esta camada o backtest RODA e não mede nada: `features.yaml` pede
    razões de valuation (pe, pb, ev_ebitda) e sinais de timing (rsi_14,
    momentum_*), todos dependentes de preço. `replay_decision_batch` chama
    `derive_point_in_time_valuation` e `derive_point_in_time_timing`, mas
    elas não inventam preço -- na ausência dele os fatores caem em neutro e
    o replay produz um mar de AVOID que parece veredicto do modelo e é só
    ausência de dado. Medido: primeira versão deste pipeline, sem preços,
    devolveu 473 de 501 em AVOID nos sete cortes, com model_confidence de
    41,8 na NVDA.

    A convenção sem look-ahead é a mesma dos filings: o fechamento de um
    pregão só fica disponível à meia-noite UTC do dia seguinte
    (`available_at_from_trade_date`).
    """
    observations: list[HistoricalObservation] = []
    splits: list[StockSplitRecord] = []
    for csv_path in sorted(Path(price_dir).glob("*.csv")):
        symbol = csv_path.stem.upper()
        try:
            history = pd.read_csv(csv_path, index_col="Date", parse_dates=True)
        except (OSError, ValueError):
            continue
        if history.empty:
            continue
        observations.extend(extract_price_observations(symbol, history))
        splits.extend(extract_split_records(symbol, history))
    return tuple(observations), tuple(splits)


def _git_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_manifest(
    *,
    universe_manifest_path: str | Path,
    constituents_csv: str | Path,
    tracked_fields: Iterable[str],
    unresolved_delistings: Iterable[str],
    calendar_description: str,
) -> HistoricalInputManifest:
    manifest = json.loads(Path(universe_manifest_path).read_text(encoding="utf-8"))
    unresolved = tuple(unresolved_delistings)
    return HistoricalInputManifest(
        source_name="SEC EDGAR companyfacts (XBRL, filing-dated)",
        source_version=(
            "collection completed "
            + datetime.now(timezone.utc).date().isoformat()
        ),
        benchmark_source="Yahoo Finance daily bars (SPY)",
        constituent_history_source=(
            f"Wikipedia S&P 500 revision {manifest.get('wikipedia_revision_id')} "
            f"({Path(constituents_csv).name}, "
            f"sha256 {str(manifest.get('csv_sha256'))[:12]}...)"
        ),
        decision_calendar_description=calendar_description,
        timezone="UTC",
        tracked_fields=tuple(sorted(set(tracked_fields))),
        revision_policy=(
            "all SEC revisions kept; revision_id = EDGAR accession number; "
            "as_of picks what was filed by the cutoff"
        ),
        delisting_coverage_description=(
            "no delisting records collected; symbols with empty price history "
            "are counted as unresolved, not hidden: "
            + (", ".join(unresolved) or "none")
        ),
        unresolved_delisting_count=len(unresolved),
        atlas_code_revision=_git_revision(),
        governed_config_hashes=compute_governed_config_hashes(
            {
                "model.yaml": ROOT / "config" / "model.yaml",
                "deal_breakers.json": ROOT / "config" / "deal_breakers.json",
                "features.yaml": ROOT / "config" / "features.yaml",
            }
        ),
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Roda o walk-forward ponta a ponta sobre a coleta SEC."
    )
    parser.add_argument(
        "--state", default=str(ROOT / "data" / "sec_edgar_collection.json")
    )
    parser.add_argument(
        "--backtest-dir",
        default=str(ROOT / "output" / "dados" / "backtest_2026-01-01"),
    )
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument(
        "--end", default=datetime.now(timezone.utc).date().isoformat()
    )
    parser.add_argument("--day-of-month", type=int, default=2)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    backtest_dir = Path(args.backtest_dir)
    constituents_csv = next(backtest_dir.glob("sp500_constituents_*.csv"))
    effective_from = constituents_csv.stem.rsplit("_", 1)[-1]

    observations = load_observations(args.state)
    prices, splits = load_price_observations(backtest_dir / "prices")
    memberships = load_memberships(
        constituents_csv, effective_from=effective_from
    )
    dataset = PointInTimeDataset.from_iterables(
        observations=observations + prices,
        memberships=memberships,
        splits=splits,
    )
    print(
        f"dataset: {len(observations)} fatos SEC + {len(prices)} preços, "
        f"{len(splits)} splits, {len(memberships)} membros"
    )

    calendar = monthly_decision_calendar(
        args.start, args.end, day_of_month=args.day_of_month
    )
    calendar_description = (
        f"monthly, day {args.day_of_month}, {args.start}..{args.end} UTC"
    )

    failures_path = backtest_dir / "price_collection_failures.json"
    unresolved: tuple[str, ...] = ()
    if failures_path.exists():
        unresolved = tuple(
            sorted(json.loads(failures_path.read_text(encoding="utf-8")))
        )

    manifest = build_manifest(
        universe_manifest_path=backtest_dir / "universe_manifest.json",
        constituents_csv=constituents_csv,
        tracked_fields=(
            obs.field_name for obs in (observations + prices)
        ),
        unresolved_delistings=unresolved,
        calendar_description=calendar_description,
    )

    report = run_walk_forward(
        dataset,
        calendar,
        manifest,
        model_path=ROOT / "config" / "model.yaml",
        deal_breakers_path=ROOT / "config" / "deal_breakers.json",
    )
    output = (
        Path(args.output)
        if args.output
        else backtest_dir / "walk_forward_report.json"
    )
    path = write_walk_forward_report(report, output)
    print(
        f"Walk-forward: {len(report.decision_dates)} datas, "
        f"{len(report.replayed_decisions)} decisões reproduzidas, "
        f"{len(report.incomplete_decisions)} incompletas -> {path}"
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from backtesting.total_return_evidence import (
    TotalReturnEvidence,
    extract_total_return_observations,
    write_total_return_evidence,
)


def _monthly_boundaries(price_history: pd.DataFrame) -> tuple[date, ...]:
    if "Date" in price_history.columns:
        dates = pd.to_datetime(price_history["Date"], errors="coerce").dropna()
    else:
        dates = pd.to_datetime(price_history.index, errors="coerce")
    trading_dates = sorted({timestamp.date() for timestamp in dates})
    if not trading_dates:
        return ()
    frame = pd.DataFrame({"date": trading_dates})
    frame["month"] = pd.to_datetime(frame["date"]).dt.to_period("M")
    starts = frame.groupby("month", sort=True)["date"].min().tolist()
    if len(starts) < 2:
        return tuple(starts)
    return tuple(starts)


def build_total_return_evidence_from_directory(
    price_dir: str | Path,
    *,
    source: str = "historical_price_csv",
    currency: str = "USD",
    benchmark_symbol: str = "SPY",
    retrieved_at: datetime | str | None = None,
) -> TotalReturnEvidence:
    directory = Path(price_dir)
    paths = sorted(directory.glob("*.csv"))
    if not paths:
        raise ValueError("price_dir não contém arquivos CSV.")

    histories: dict[str, pd.DataFrame] = {}
    for path in paths:
        frame = pd.read_csv(path)
        if "Date" not in frame.columns or "Close" not in frame.columns:
            continue
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date", "Close"]).set_index("Date")
        histories[path.stem.upper()] = frame

    if benchmark_symbol.upper() not in histories:
        raise ValueError(f"Histórico do benchmark ausente: {benchmark_symbol.upper()}")
    boundaries = _monthly_boundaries(histories[benchmark_symbol.upper()])
    if len(boundaries) < 2:
        raise ValueError("O histórico do benchmark não tem dois períodos mensais.")

    returns = []
    for symbol, history in histories.items():
        returns.extend(
            extract_total_return_observations(
                symbol,
                history,
                boundaries,
                currency=currency,
                source=source,
            )
        )
    if not returns:
        raise ValueError("Nenhum retorno total pôde ser derivado.")
    timestamp = retrieved_at or datetime.now(timezone.utc)
    return TotalReturnEvidence(retrieved_at=timestamp, returns=tuple(returns))


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gera evidência batch de retornos totais.")
    parser.add_argument("--price-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--benchmark", default="SPY")
    args = parser.parse_args(list(argv) if argv is not None else None)
    evidence = build_total_return_evidence_from_directory(
        args.price_dir,
        benchmark_symbol=args.benchmark,
    )
    write_total_return_evidence(evidence, args.output)
    print(f"Retornos gerados: {len(evidence.returns)} observações")


if __name__ == "__main__":
    main()

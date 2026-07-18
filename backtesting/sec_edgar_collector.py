from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from backtesting.point_in_time import HistoricalObservation
from backtesting.sec_edgar import (
    extract_observations,
    fetch_company_facts,
    fetch_ticker_cik_map,
)
from storage.atomic_write import replace_with_retry


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = ROOT / "data" / "sec_edgar_collection.json"
DEFAULT_TICKERS_FILE = ROOT / "config" / "watchlist.csv"
STATE_SCHEMA_VERSION = 1
USER_AGENT_ENV_VAR = "SEC_EDGAR_USER_AGENT"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _observation_to_dict(observation: HistoricalObservation) -> dict[str, Any]:
    return {
        "symbol": observation.symbol,
        "field_name": observation.field_name,
        "value": observation.value,
        "observed_on": observation.observed_on.isoformat(),
        "available_at": observation.available_at.isoformat(),
        "source": observation.source,
        "revision_id": observation.revision_id,
    }


def _observation_from_dict(payload: dict[str, Any]) -> HistoricalObservation:
    return HistoricalObservation(
        symbol=payload["symbol"],
        field_name=payload["field_name"],
        value=payload["value"],
        observed_on=payload["observed_on"],
        available_at=payload["available_at"],
        source=payload["source"],
        revision_id=payload["revision_id"],
    )


@dataclass
class SecEdgarCollectionState:
    """
    Checkpoint retomável da coleta de fatos XBRL da SEC por ticker.

    Ao contrário de universe.collector.CollectionState (uma linha de
    fundamentos por símbolo, retrato de um único dia), cada símbolo aqui
    acumula uma LISTA de HistoricalObservation -- a série histórica
    ponto-no-tempo inteira daquele ticker, não um snapshot do dia da coleta.
    """

    created_at: str
    updated_at: str
    observations_by_symbol: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    failures: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "observations_by_symbol": self.observations_by_symbol,
            "failures": self.failures,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SecEdgarCollectionState":
        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(
                "Versão incompatível do checkpoint de coleta SEC EDGAR."
            )
        return cls(
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            observations_by_symbol=dict(
                payload.get("observations_by_symbol", {})
            ),
            failures=dict(payload.get("failures", {})),
        )

    def observations(self) -> tuple[HistoricalObservation, ...]:
        """
        Todas as observações já coletadas, de todos os símbolos completos,
        prontas para alimentar um PointInTimeDataset.
        """
        result: list[HistoricalObservation] = []
        for entries in self.observations_by_symbol.values():
            result.extend(_observation_from_dict(entry) for entry in entries)
        return tuple(result)


def load_collection_state(
    path: str | Path,
    *,
    now: Callable[[], str] = _utc_timestamp,
) -> SecEdgarCollectionState:
    state_path = Path(path)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    candidates: list[SecEdgarCollectionState] = []
    for candidate_path in (state_path, temporary):
        if not candidate_path.exists():
            continue
        try:
            candidates.append(
                SecEdgarCollectionState.from_dict(
                    json.loads(candidate_path.read_text(encoding="utf-8"))
                )
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            if candidate_path == state_path:
                raise
    if candidates:
        return max(
            candidates,
            key=lambda item: (
                len(item.observations_by_symbol),
                item.updated_at,
            ),
        )

    timestamp = now()
    return SecEdgarCollectionState(created_at=timestamp, updated_at=timestamp)


def write_collection_state(
    state: SecEdgarCollectionState,
    path: str | Path,
    *,
    replace_attempts: int = 10,
    retry_delay: float = 0.2,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )
    replace_with_retry(
        temporary,
        output,
        replace_attempts=replace_attempts,
        retry_delay=retry_delay,
        sleeper=sleeper,
    )
    return output


@dataclass(frozen=True)
class TickerBatch:
    batch_number: int
    total_batches: int
    total_tickers: int
    tickers: tuple[str, ...]


def _ordered_tickers(tickers: Iterable[str]) -> list[str]:
    return sorted({str(item).strip().upper() for item in tickers if str(item).strip()})


def select_ticker_batch(
    tickers: Iterable[str],
    *,
    batch_size: int,
    batch_number: int,
) -> TickerBatch:
    ordered = _ordered_tickers(tickers)
    if batch_size <= 0:
        raise ValueError("batch_size deve ser positivo.")
    total_batches = math.ceil(len(ordered) / batch_size) if ordered else 0
    if batch_number < 1 or batch_number > total_batches:
        raise ValueError("batch_number fora do intervalo disponível.")
    start = (batch_number - 1) * batch_size
    return TickerBatch(
        batch_number=batch_number,
        total_batches=total_batches,
        total_tickers=len(ordered),
        tickers=tuple(ordered[start : start + batch_size]),
    )


def select_next_incomplete_batch(
    tickers: Iterable[str],
    *,
    batch_size: int,
    completed_symbols: Iterable[str],
) -> TickerBatch | None:
    ordered = _ordered_tickers(tickers)
    completed = set(completed_symbols)
    if batch_size <= 0:
        raise ValueError("batch_size deve ser positivo.")
    total_batches = math.ceil(len(ordered) / batch_size) if ordered else 0
    for batch_number in range(1, total_batches + 1):
        batch = select_ticker_batch(
            ordered, batch_size=batch_size, batch_number=batch_number
        )
        if any(symbol not in completed for symbol in batch.tickers):
            return batch
    return None


@dataclass(frozen=True)
class CollectionBatchResult:
    batch_number: int
    total_batches: int
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    completed_total: int
    remaining_total: int


def collect_ticker_batch(
    batch: TickerBatch,
    *,
    cik_by_ticker: dict[str, str],
    state_path: str | Path,
    user_agent: str,
    fetcher: Callable[..., dict[str, Any]] = fetch_company_facts,
    retries: int = 2,
    now: Callable[[], str] = _utc_timestamp,
) -> CollectionBatchResult:
    """
    Coleta um lote retomável de tickers: para cada um, busca companyfacts na
    SEC, converte para HistoricalObservation e persiste no checkpoint a cada
    símbolo (não só ao final do lote), mesmo padrão de
    universe.collector.collect_constituent_batch.

    Um ticker sem CIK conhecido é registrado como falha explícita (nunca
    pulado silenciosamente). Símbolos já completos são pulados.
    """
    if retries < 0:
        raise ValueError("retries não pode ser negativo.")

    state = load_collection_state(state_path, now=now)
    attempted = succeeded = failed = skipped = 0

    for symbol in batch.tickers:
        if symbol in state.observations_by_symbol:
            skipped += 1
            continue

        cik = cik_by_ticker.get(symbol)
        if cik is None:
            timestamp = now()
            previous_attempts = int(
                state.failures.get(symbol, {}).get("attempts", 0)
            )
            state.failures[symbol] = {
                "attempts": previous_attempts + 1,
                "last_error": "CIK não encontrado para o ticker.",
                "updated_at": timestamp,
            }
            state.updated_at = timestamp
            write_collection_state(state, state_path)
            failed += 1
            continue

        attempted += 1
        last_error: Exception | None = None
        for _ in range(retries + 1):
            try:
                facts = fetcher(cik, user_agent=user_agent)
                observations = extract_observations(symbol, facts)
                state.observations_by_symbol[symbol] = [
                    _observation_to_dict(item) for item in observations
                ]
                state.failures.pop(symbol, None)
                succeeded += 1
                last_error = None
                break
            except Exception as exc:  # provider boundary: persist exact failure
                last_error = exc

        timestamp = now()
        if last_error is not None:
            previous_attempts = int(
                state.failures.get(symbol, {}).get("attempts", 0)
            )
            state.failures[symbol] = {
                "attempts": previous_attempts + retries + 1,
                "last_error": str(last_error),
                "updated_at": timestamp,
            }
            failed += 1
        state.updated_at = timestamp
        write_collection_state(state, state_path)

    completed_total = len(state.observations_by_symbol)
    return CollectionBatchResult(
        batch_number=batch.batch_number,
        total_batches=batch.total_batches,
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        completed_total=completed_total,
        remaining_total=batch.total_tickers - completed_total,
    )


def _load_tickers_from_csv(path: str | Path) -> tuple[str, ...]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return tuple(
            row["symbol"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("symbol", "").strip()
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Coleta um lote retomável de fatos XBRL da SEC EDGAR para uma "
            "lista de tickers (padrão: config/watchlist.csv)."
        )
    )
    parser.add_argument("--tickers-file", default=str(DEFAULT_TICKERS_FILE))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch-number", type=int)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--user-agent",
        default=os.environ.get(USER_AGENT_ENV_VAR),
        help=(
            f"Identificação exigida pela SEC (nome/contato). Lida por "
            f"padrão da variável de ambiente {USER_AGENT_ENV_VAR} -- nunca "
            "tem um valor padrão fixo no código-fonte."
        ),
    )
    args = parser.parse_args()

    if not args.user_agent:
        raise SystemExit(
            "É obrigatório identificar o solicitante para a SEC EDGAR "
            f"(--user-agent ou variável de ambiente {USER_AGENT_ENV_VAR})."
        )

    tickers = _load_tickers_from_csv(args.tickers_file)
    cik_by_ticker = fetch_ticker_cik_map(user_agent=args.user_agent)

    if args.batch_number is None:
        batch = select_next_incomplete_batch(
            tickers,
            batch_size=args.batch_size,
            completed_symbols=load_collection_state(args.state).observations_by_symbol,
        )
        if batch is None:
            print("Coleta já está completa.")
            return
    else:
        batch = select_ticker_batch(
            tickers,
            batch_size=args.batch_size,
            batch_number=args.batch_number,
        )

    result = collect_ticker_batch(
        batch,
        cik_by_ticker=cik_by_ticker,
        state_path=args.state,
        user_agent=args.user_agent,
        retries=args.retries,
    )
    print(
        f"Lote {result.batch_number}/{result.total_batches}: "
        f"{result.succeeded} coletados, {result.failed} falharam, "
        f"{result.skipped} já completos. "
        f"Total: {result.completed_total}/{batch.total_tickers} "
        f"({result.remaining_total} restantes)."
    )


if __name__ == "__main__":
    main()

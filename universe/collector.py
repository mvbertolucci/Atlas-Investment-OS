from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import yaml

from analytics.fundamentals import compute_fundamentals
from analytics.indicators import enrich_technicals
from providers.yahoo import fetch_symbol
from providers.contracts import ProviderClient, ProviderError, ProviderPolicy
from providers.evidence import (
    apply_sector_applicability,
    ensure_field_evidence,
    reconcile_critical_fields,
)
from storage.atomic_write import replace_with_retry
from storage.raw_snapshots import resolve_raw_snapshot_path, store_raw_snapshot
from providers.sec_companyfacts import build_sec_secondary_provider
from universe.sources import (
    ConstituentBatch,
    load_constituent_snapshot,
    select_constituent_batch,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_PATH = ROOT / "data" / "research_universe_collection.json"
STATE_SCHEMA_VERSION = 1


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Valor não serializável no checkpoint: {type(value).__name__}")


def _prepare_observation(
    raw: dict[str, Any],
    *,
    quality_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = compute_fundamentals(enrich_technicals(dict(raw)))
    ensure_field_evidence(enriched)
    apply_sector_applicability(enriched, quality_policy)
    return {
        key: _json_value(value)
        for key, value in enriched.items()
        if key != "history" and not key.startswith("_")
    }


@dataclass
class CollectionState:
    snapshot_date: str
    total_constituents: int
    created_at: str
    updated_at: str
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "snapshot_date": self.snapshot_date,
            "total_constituents": self.total_constituents,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "observations": self.observations,
            "failures": self.failures,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CollectionState":
        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError("Versão incompatível do checkpoint de coleta.")
        return cls(
            snapshot_date=str(payload["snapshot_date"]),
            total_constituents=int(payload["total_constituents"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            observations=dict(payload.get("observations", {})),
            failures=dict(payload.get("failures", {})),
        )


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


def _snapshot_date(records: Iterable[dict[str, str]]) -> str:
    dates = {row.get("snapshot_date", "").strip() for row in records}
    if len(dates) != 1 or not next(iter(dates)):
        raise ValueError("O universo deve possuir uma única snapshot_date.")
    return next(iter(dates))


def load_collection_state(
    path: str | Path,
    *,
    snapshot_date: str,
    total_constituents: int,
    now: Callable[[], str] = _utc_timestamp,
) -> CollectionState:
    state_path = Path(path)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    candidates: list[CollectionState] = []
    for candidate_path in (state_path, temporary):
        if not candidate_path.exists():
            continue
        try:
            candidates.append(
                CollectionState.from_dict(
                    json.loads(candidate_path.read_text(encoding="utf-8"))
                )
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            if candidate_path == state_path:
                raise
    if candidates:
        state = max(
            candidates,
            key=lambda item: (len(item.observations), item.updated_at),
        )
        if (
            state.snapshot_date != snapshot_date
            or state.total_constituents != total_constituents
        ):
            raise ValueError(
                "Checkpoint pertence a outro snapshot do universo; "
                "use outro arquivo ou arquive o checkpoint anterior."
            )
        return state

    timestamp = now()
    return CollectionState(
        snapshot_date=snapshot_date,
        total_constituents=total_constituents,
        created_at=timestamp,
        updated_at=timestamp,
    )


def write_collection_state(
    state: CollectionState,
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
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
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


def select_next_incomplete_batch(
    records: Iterable[dict[str, str]],
    *,
    batch_size: int,
    completed_symbols: Iterable[str],
    failed_attempts: Mapping[str, int] | None = None,
    failure_attempt_budget: int | None = None,
) -> ConstituentBatch | None:
    rows = list(records)
    completed = set(completed_symbols)
    if batch_size <= 0:
        raise ValueError("batch_size deve ser positivo.")
    if failure_attempt_budget is not None and failure_attempt_budget <= 0:
        raise ValueError("failure_attempt_budget deve ser positivo.")
    exhausted_failures = {
        symbol
        for symbol, attempts in (failed_attempts or {}).items()
        if (
            failure_attempt_budget is not None
            and int(attempts) >= failure_attempt_budget
        )
    }
    resolved = completed | exhausted_failures
    total_batches = math.ceil(len(rows) / batch_size)
    for batch_number in range(1, total_batches + 1):
        batch = select_constituent_batch(
            rows,
            batch_size=batch_size,
            batch_number=batch_number,
        )
        if any(row["symbol"] not in resolved for row in batch.frame_rows):
            return batch
    return None


def collect_constituent_batch(
    batch: ConstituentBatch,
    *,
    snapshot_date: str,
    state_path: str | Path = DEFAULT_STATE_PATH,
    fetcher: Callable[..., dict[str, Any]] = fetch_symbol,
    period: str = "2y",
    interval: str = "1d",
    retries: int = 2,
    timeout_seconds: float = 30.0,
    backoff_seconds: float = 0.5,
    rate_limit_per_second: float = 2.0,
    raw_snapshot_dir: str | Path | None = None,
    secondary_fetcher: Callable[..., dict[str, Any]] | None = None,
    critical_fields: Iterable[str] = (
        "market_cap",
        "enterprise_value",
        "total_debt",
        "total_cash",
        "ebitda",
        "free_cashflow",
        "current_ratio",
        "short_float",
    ),
    confirmation_tolerance: float = 0.05,
    quality_policy: Mapping[str, Any] | None = None,
    now: Callable[[], str] = _utc_timestamp,
) -> CollectionBatchResult:
    if retries < 0:
        raise ValueError("retries não pode ser negativo.")
    state = load_collection_state(
        state_path,
        snapshot_date=snapshot_date,
        total_constituents=batch.total_constituents,
        now=now,
    )
    provider_policy = ProviderPolicy(
        timeout_seconds=timeout_seconds,
        max_retries=retries,
        backoff_seconds=backoff_seconds,
        rate_limit_per_second=rate_limit_per_second,
    )
    primary_client = ProviderClient("Yahoo Finance", provider_policy)
    secondary_client = ProviderClient(
        str(getattr(secondary_fetcher, "provider_name", "Secondary")),
        provider_policy,
    )
    snapshot_root = Path(raw_snapshot_dir or Path(state_path).parent / "raw_snapshots")
    attempted = succeeded = failed = skipped = 0

    for constituent in batch.frame_rows:
        symbol = constituent["symbol"]
        if symbol in state.observations:
            skipped += 1
            continue

        attempted += 1
        last_error: ProviderError | None = None
        try:
            raw = primary_client.execute(
                "fetch_symbol",
                fetcher,
                symbol,
                constituent.get("name", ""),
                period=period,
                interval=interval,
            )
            collected_at = str(raw.get("as_of") or now())
            receipt = store_raw_snapshot(
                raw,
                snapshot_root,
                provider=str(raw.get("source") or "Yahoo Finance"),
                symbol=symbol,
                collected_at=collected_at,
            )
            raw["raw_snapshot_hash"] = receipt.sha256
            raw["raw_snapshot_path"] = str(receipt.path)
            secondary = None
            if secondary_fetcher is not None:
                try:
                    secondary = secondary_client.execute(
                        "fetch_symbol",
                        secondary_fetcher,
                        symbol,
                        constituent.get("name", ""),
                        period=period,
                        interval=interval,
                    )
                except ProviderError as secondary_error:
                    raw["secondary_provider_error"] = secondary_error.to_dict()
                else:
                    ensure_field_evidence(secondary)
                    secondary_receipt = store_raw_snapshot(
                        secondary,
                        snapshot_root,
                        provider=str(secondary.get("source") or "Secondary"),
                        symbol=symbol,
                        collected_at=str(secondary.get("as_of") or now()),
                    )
                    raw["secondary_raw_snapshot_hash"] = secondary_receipt.sha256
                    raw["secondary_raw_snapshot_path"] = str(secondary_receipt.path)
            reconciled = reconcile_critical_fields(
                raw,
                secondary,
                critical_fields,
                tolerance=confirmation_tolerance,
            )
            observation = _prepare_observation(
                reconciled,
                quality_policy=quality_policy,
            )
            observation["universe_snapshot_date"] = snapshot_date
            observation["universe_source_symbol"] = constituent.get(
                "source_symbol", symbol
            )
            state.observations[symbol] = observation
            state.failures.pop(symbol, None)
            succeeded += 1
        except ProviderError as exc:
            last_error = exc

        timestamp = now()
        if last_error is not None:
            previous_attempts = int(state.failures.get(symbol, {}).get("attempts", 0))
            state.failures[symbol] = {
                **last_error.to_dict(),
                "attempts": previous_attempts + last_error.attempts,
                "last_error": str(last_error),
                "updated_at": timestamp,
            }
            failed += 1
        state.updated_at = timestamp
        write_collection_state(state, state_path)

    completed_total = len(state.observations)
    return CollectionBatchResult(
        batch_number=batch.batch_number,
        total_batches=batch.total_batches,
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        completed_total=completed_total,
        remaining_total=batch.total_constituents - completed_total,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Coleta um lote retomável do universo de pesquisa. Por padrão, "
            "o screener S&P 500; com --market, o screener de mercado amplo "
            "(separado, próprio snapshot/checkpoint/tamanho de lote)."
        )
    )
    parser.add_argument("--batch-number", type=int)
    parser.add_argument(
        "--market",
        action="store_true",
        help="Usa a configuração do screener de mercado amplo em vez do S&P 500.",
    )
    parser.add_argument(
        "--snapshot",
        help="Sobrescreve o caminho do snapshot de constituintes.",
    )
    parser.add_argument("--state")
    parser.add_argument("--retries", type=int)
    args = parser.parse_args()

    settings = json.loads(
        (ROOT / "config" / "settings.json").read_text(encoding="utf-8")
    )

    if args.market:
        snapshot_key = "research_universe_market_path"
        batch_size_key = "research_universe_market_batch_size"
        state_key = "research_collection_market_state_path"
        default_snapshot = "config/research_universe_market.csv"
        default_state = "data/research_universe_collection_market.json"
    else:
        snapshot_key = "research_universe_path"
        batch_size_key = "research_universe_batch_size"
        state_key = "research_collection_state_path"
        default_snapshot = "config/research_universe.csv"
        default_state = "data/research_universe_collection.json"

    records = load_constituent_snapshot(
        ROOT
        / (
            args.snapshot
            or settings.get(snapshot_key, default_snapshot)
        )
    )
    batch_size = int(settings.get(batch_size_key, 25))
    configured_state = Path(
        args.state
        or settings.get(state_key, default_state)
    )
    state_path = (
        configured_state
        if configured_state.is_absolute()
        else ROOT / configured_state
    )
    retries = (
        args.retries
        if args.retries is not None
        else int(
            settings.get(
                "provider_max_retries",
                settings.get("research_collection_retries", 2),
            )
        )
    )
    snapshot_date = _snapshot_date(records)
    state = load_collection_state(
        state_path,
        snapshot_date=snapshot_date,
        total_constituents=len(records),
    )
    if args.batch_number is None:
        failed_attempts = {
            symbol: int(details.get("attempts", 0))
            for symbol, details in state.failures.items()
        }
        failure_attempt_budget = retries + 1
        batch = select_next_incomplete_batch(
            records,
            batch_size=batch_size,
            completed_symbols=state.observations,
            failed_attempts=failed_attempts,
            failure_attempt_budget=failure_attempt_budget,
        )
        if batch is None:
            exhausted_count = sum(
                attempts >= failure_attempt_budget
                for attempts in failed_attempts.values()
            )
            if exhausted_count:
                print(
                    "Todos os lotes foram resolvidos para avanço; "
                    f"{exhausted_count} falha(s) esgotaram o orçamento de "
                    "tentativas e permanecem visíveis no checkpoint. Use "
                    "--batch-number para reprocessá-las explicitamente."
                )
            else:
                print("Coleta já está completa.")
            return
    else:
        batch = select_constituent_batch(
            records,
            batch_size=batch_size,
            batch_number=args.batch_number,
        )

    quality_path = ROOT / "config" / "data_quality.yaml"
    quality_policy = (
        yaml.safe_load(quality_path.read_text(encoding="utf-8")) or {}
        if quality_path.exists()
        else {}
    )
    result = collect_constituent_batch(
        batch,
        snapshot_date=snapshot_date,
        state_path=state_path,
        period=settings.get("history_period", "2y"),
        interval=settings.get("history_interval", "1d"),
        retries=retries,
        timeout_seconds=float(settings.get("provider_timeout_seconds", 30)),
        backoff_seconds=float(settings.get("provider_backoff_seconds", 0.5)),
        rate_limit_per_second=float(
            settings.get("provider_rate_limit_per_second", 2)
        ),
        raw_snapshot_dir=resolve_raw_snapshot_path(
            ROOT,
            settings.get("raw_snapshot_path", "data/raw_snapshots"),
        ),
        secondary_fetcher=build_sec_secondary_provider(ROOT, settings),
        critical_fields=tuple(settings.get("provider_critical_fields", ())),
        quality_policy=quality_policy,
    )
    print(
        f"Lote {result.batch_number}/{result.total_batches}: "
        f"{result.succeeded} sucesso(s), {result.failed} falha(s), "
        f"{result.skipped} já concluído(s). "
        f"Total: {result.completed_total}/{batch.total_constituents}."
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from watchlist.csv_writer import write_watchlist_rows
from watchlist.exceptions import WatchlistError
from watchlist.models import WATCHLIST_ENTRY_SOURCES

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_PATH = ROOT / "output" / "dados" / "ranking_report.json"
DEFAULT_WATCHLIST_PATH = ROOT / "config" / "watchlist.csv"


class SymbolAlreadyInWatchlistError(WatchlistError):
    """O símbolo já está na watchlist -- promoção recusada para não duplicar."""


class SymbolNotInWatchlistError(WatchlistError):
    """O símbolo não está na watchlist -- remoção recusada, nada a remover."""


@dataclass(frozen=True)
class PromotionResult:
    symbol: str
    name: str
    included_at: str
    note: str
    watchlist_path: Path
    source: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "included_at": self.included_at,
            "note": self.note,
            "watchlist_path": str(self.watchlist_path),
            "source": self.source,
        }


@dataclass(frozen=True)
class RemovalResult:
    symbol: str
    reason: str
    watchlist_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "reason": self.reason,
            "watchlist_path": str(self.watchlist_path),
        }


def _lookup_name(symbol: str, source_path: Path) -> str:
    """
    Procura o nome do símbolo no arquivo de origem. Aceita tanto o JSON de
    ranking (RankingReport.to_dict(), campo "companies" -- não carrega nome,
    só symbol/sector/scores) quanto um research_candidates*.csv
    (ranking.write_candidate_ranking_csv, que tem "name"). Símbolo ausente
    ou arquivo inexistente não bloqueia a promoção -- só resulta em nome
    vazio.
    """
    if not source_path.exists():
        return ""

    if source_path.suffix == ".csv":
        with source_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("symbol", "")).strip().upper() == symbol:
                    return str(row.get("name", "")).strip()
        return ""

    if source_path.suffix == ".json":
        data = json.loads(source_path.read_text(encoding="utf-8"))
        for company in data.get("companies", []):
            if str(company.get("symbol", "")).strip().upper() == symbol:
                return str(company.get("name", "")).strip()
    return ""


def promote_to_watchlist(
    symbol: str,
    reason: str,
    *,
    source_path: Path = DEFAULT_SOURCE_PATH,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    today: date | None = None,
    name: str | None = None,
    trigger_condition: str = "",
    source: str = "manual",
    analytical_origin: str | None = None,
    entry_rank: int | None = None,
    entry_score: float | None = None,
    review_sla_days: int = 30,
    discard_condition: str = "",
) -> PromotionResult:
    """
    Promove um símbolo do output do screener para a watchlist: preenche
    `included_at` (hoje) e `note` (o motivo) automaticamente. Recusa
    duplicata -- nunca promove um símbolo já presente. WL -> carteira fica
    fora deste PR (compra é registrada manualmente em config/portfolio.csv,
    ver PR-020). Nunca toca config/portfolio.csv, e nunca checa holdings --
    quem chama (CLI manual, planilha, ou o fluxo de curadoria automática) é
    responsável por filtrar símbolos já detidos antes de chamar isto.

    `name`, se informado, sobrescreve o lookup em `source_path` -- usado por
    `watchlist.apply_candidates_workbook`, que já tem o nome resolvido no
    momento da exportação e não deve depender do arquivo de origem ainda
    existir sem mudanças no momento da aplicação. `trigger_condition`
    permanece vazio por padrão (comportamento inalterado do CLI manual).

    `source` marca a origem da linha (`"manual"` por padrão -- CLI/planilha;
    `"auto"` só quando chamado pelo fluxo de curadoria automática). É a base
    da salvaguarda "nunca remover automaticamente uma entrada manual" em
    `select_auto_removal_candidates`.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("promote_to_watchlist exige um símbolo válido.")

    reason = reason.strip()
    if not reason:
        raise ValueError("promote_to_watchlist exige um motivo não vazio.")

    source = source.strip().lower() or "manual"
    if source not in WATCHLIST_ENTRY_SOURCES:
        raise ValueError(
            f"source inválido: {source!r} (esperado um de {WATCHLIST_ENTRY_SOURCES})"
        )
    if review_sla_days <= 0:
        raise ValueError("review_sla_days deve ser positivo.")

    watchlist_path = Path(watchlist_path)
    if not watchlist_path.exists():
        raise WatchlistError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    with watchlist_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        existing_fieldnames = list(rows[0].keys()) if rows else ["symbol", "name"]

    if any(
        str(row.get("symbol", "")).strip().upper() == symbol
        for row in rows
    ):
        raise SymbolAlreadyInWatchlistError(
            f"{symbol} já está na watchlist -- promoção recusada."
        )

    resolved_name = (
        name.strip() if name is not None else _lookup_name(symbol, Path(source_path))
    )
    included_at = (today or date.today()).isoformat()
    review_due_at = ((today or date.today()) + timedelta(days=review_sla_days)).isoformat()

    new_row = {
        "symbol": symbol,
        "name": resolved_name,
        "included_at": included_at,
        "note": reason,
        "trigger_condition": trigger_condition.strip(),
        "source": source,
        "lifecycle_state": "analyzing" if source == "auto" else "monitoring",
        "analytical_origin": (analytical_origin or source).strip(),
        "entry_rank": entry_rank if entry_rank is not None else "",
        "entry_score": entry_score if entry_score is not None else "",
        "review_due_at": review_due_at,
        "promotion_condition": trigger_condition.strip(),
        "discard_condition": discard_condition.strip(),
    }

    # União das colunas existentes (preserva o que já está no arquivo) com as
    # novas -- se o CSV ainda era só symbol,name (legado), o header ganha as
    # colunas de metadado agora; linhas antigas ficam com elas em branco,
    # exceto `source`, que é backfillada para "manual" explicitamente (toda
    # linha pré-existente foi curada à mão, por definição -- o fluxo
    # automático só passou a existir a partir desta mudança).
    fieldnames = list(existing_fieldnames)
    for column in new_row:
        if column not in fieldnames:
            fieldnames.append(column)

    backfilled_rows = [
        {**row, "source": row.get("source") or "manual"} for row in rows
    ]
    write_watchlist_rows(
        watchlist_path,
        fieldnames,
        [*backfilled_rows, new_row],
    )

    return PromotionResult(
        symbol=symbol,
        name=resolved_name,
        included_at=included_at,
        note=reason,
        watchlist_path=watchlist_path,
        source=source,
    )


def remove_from_watchlist(
    symbol: str,
    reason: str,
    *,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
) -> RemovalResult:
    """
    Remove um símbolo de config/watchlist.csv. Função simétrica e "burra"
    em relação a `promote_to_watchlist`: só remove, não decide elegibilidade
    -- quem chama (hoje, só `select_auto_removal_candidates`) é responsável
    por já ter checado as salvaguardas (holding real, `source` manual) antes
    de chamar isto. Recusa remover um símbolo ausente (nada a remover).
    Nunca toca config/portfolio.csv.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("remove_from_watchlist exige um símbolo válido.")

    reason = reason.strip()
    if not reason:
        raise ValueError("remove_from_watchlist exige um motivo não vazio.")

    watchlist_path = Path(watchlist_path)
    if not watchlist_path.exists():
        raise WatchlistError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    with watchlist_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0].keys()) if rows else ["symbol", "name"]

    remaining = [
        row
        for row in rows
        if str(row.get("symbol", "")).strip().upper() != symbol
    ]
    if len(remaining) == len(rows):
        raise SymbolNotInWatchlistError(
            f"{symbol} não está na watchlist -- remoção recusada."
        )

    write_watchlist_rows(watchlist_path, fieldnames, remaining)

    return RemovalResult(
        symbol=symbol,
        reason=reason,
        watchlist_path=watchlist_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Promove um símbolo do output do screener para a watchlist, "
            "preenchendo data de inclusão e motivo automaticamente."
        )
    )
    parser.add_argument("symbol", help="Símbolo a promover (ex.: NEM).")
    parser.add_argument("reason", help="Motivo/nota curta (por que acompanhar).")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE_PATH),
        help=(
            "Arquivo de origem para conferir o nome (ranking_report.json "
            "ou research_candidates*.csv). Default: %(default)s."
        ),
    )
    parser.add_argument(
        "--watchlist",
        default=str(DEFAULT_WATCHLIST_PATH),
        help="Caminho da watchlist. Default: %(default)s.",
    )
    args = parser.parse_args()

    result = promote_to_watchlist(
        args.symbol,
        args.reason,
        source_path=Path(args.source),
        watchlist_path=Path(args.watchlist),
    )
    print(
        f"{result.symbol} promovido para {result.watchlist_path} "
        f"(included_at={result.included_at})."
    )


if __name__ == "__main__":
    main()

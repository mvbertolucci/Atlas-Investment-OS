from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from watchlist.exceptions import WatchlistError

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_PATH = ROOT / "output" / "ranking_report.json"
DEFAULT_WATCHLIST_PATH = ROOT / "config" / "watchlist.csv"


class SymbolAlreadyInWatchlistError(WatchlistError):
    """O símbolo já está na watchlist -- promoção recusada para não duplicar."""


@dataclass(frozen=True)
class PromotionResult:
    symbol: str
    name: str
    included_at: str
    note: str
    watchlist_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "included_at": self.included_at,
            "note": self.note,
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
) -> PromotionResult:
    """
    Promove um símbolo do output do screener para a watchlist: preenche
    `included_at` (hoje) e `note` (o motivo) automaticamente. Recusa
    duplicata -- nunca promove um símbolo já presente. WL -> carteira fica
    fora deste PR (compra é registrada manualmente em config/portfolio.csv,
    ver PR-020). Nunca toca config/portfolio.csv.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("promote_to_watchlist exige um símbolo válido.")

    reason = reason.strip()
    if not reason:
        raise ValueError("promote_to_watchlist exige um motivo não vazio.")

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

    name = _lookup_name(symbol, Path(source_path))
    included_at = (today or date.today()).isoformat()

    new_row = {
        "symbol": symbol,
        "name": name,
        "included_at": included_at,
        "note": reason,
        "trigger_condition": "",
    }

    # União das colunas existentes (preserva o que já está no arquivo) com as
    # novas -- se o CSV ainda era só symbol,name (legado), o header ganha as
    # 3 colunas de metadado agora; linhas antigas ficam com elas em branco.
    fieldnames = list(existing_fieldnames)
    for column in new_row:
        if column not in fieldnames:
            fieldnames.append(column)

    with watchlist_path.open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})
        writer.writerow({column: new_row.get(column, "") for column in fieldnames})

    return PromotionResult(
        symbol=symbol,
        name=name,
        included_at=included_at,
        note=reason,
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

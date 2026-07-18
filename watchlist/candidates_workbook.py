from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from portfolio.exceptions import PortfolioError
from portfolio.loader import load_portfolio_csv
from watchlist.exceptions import WatchlistError
from watchlist.loader import load_watchlist_csv
from watchlist.screening import propose_from_broad_reports


ROOT = Path(__file__).resolve().parent.parent
MANUAL_ENTRY_ROWS = 40
COLUMNS = [
    "Incluir",
    "Symbol",
    "Name",
    "Sector",
    "Investment Score",
    "Confidence",
    "Candidate Rank",
    "Gatilho Sugerido",
    "Motivo Sugerido",
    "Nota",
]


def _watchlist_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return {entry.symbol for entry in load_watchlist_csv(path)}
    except WatchlistError:
        # Watchlist vazia (só cabeçalho) ou schema inválido -- não bloqueia
        # a exportação, só não exclui nenhum símbolo por já estar assistido.
        return set()


def _held_symbols(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        portfolio = load_portfolio_csv(path)
    except PortfolioError:
        return set()
    return {holding.symbol for holding in portfolio.holdings}


def build_candidates_frame(
    *,
    broad_market_path: Path | None,
    adr_path: Path | None,
    watchlist_symbols: set[str],
    held_symbols: set[str],
) -> pd.DataFrame:
    """
    Lista COMPLETA de candidatos dos screeners amplos, sem o corte de
    diversificação (max_per_sector) que a seção do relatório usa -- aqui o
    objetivo é navegar/escolher, não só ver o top sugerido. Nunca grava
    nada; é puramente informativo até `apply_candidates_workbook` aplicar
    as marcações do usuário.
    """
    proposals = propose_from_broad_reports(
        (broad_market_path, adr_path),
        watchlist_symbols=watchlist_symbols,
        held_symbols=held_symbols,
        max_per_sector=10**6,
        limit=None,
    )
    rows = [
        {
            "Incluir": "",
            "Symbol": proposal.symbol,
            "Name": proposal.name,
            "Sector": proposal.sector,
            "Investment Score": proposal.investment_score,
            "Confidence": proposal.confidence_score,
            "Candidate Rank": proposal.candidate_rank,
            "Gatilho Sugerido": proposal.suggested_condition,
            "Motivo Sugerido": proposal.condition_rationale,
            "Nota": "",
        }
        for proposal in proposals
    ]
    frame = pd.DataFrame(rows, columns=COLUMNS)
    manual_rows = pd.DataFrame(
        [{column: "" for column in COLUMNS} for _ in range(MANUAL_ENTRY_ROWS)],
        columns=COLUMNS,
    )
    return pd.concat([frame, manual_rows], ignore_index=True)


def write_workbook(frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Candidatos", index=False)
        sheet = writer.sheets["Candidatos"]
        sheet.freeze_panes = "A2"
        widths = {
            "A": 10, "B": 10, "C": 32, "D": 22, "E": 16,
            "F": 12, "G": 14, "H": 22, "I": 48, "J": 32,
        }
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Gera uma planilha com os candidatos dos screeners amplos "
            "(Mercado Amplo/ADR): marque 'Incluir' e/ou digite um ticker "
            "nas linhas em branco, salve, e rode "
            "watchlist.apply_candidates_workbook para aplicar."
        )
    )
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument(
        "--output",
        help="Caminho da planilha gerada (default: config em settings.json).",
    )
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    if not settings_path.is_absolute():
        settings_path = ROOT / settings_path
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    output_data = ROOT / "output" / "dados"
    broad_market_path = output_data / "research_ranking_report_market.json"
    adr_path = output_data / "research_ranking_report_adr.json"

    watchlist_path = ROOT / str(
        settings.get("watchlist_path", "config/watchlist.csv")
    )
    portfolio_path = ROOT / str(
        settings.get("portfolio_path", "config/portfolio.csv")
    )

    frame = build_candidates_frame(
        broad_market_path=broad_market_path if broad_market_path.exists() else None,
        adr_path=adr_path if adr_path.exists() else None,
        watchlist_symbols=_watchlist_symbols(watchlist_path),
        held_symbols=_held_symbols(portfolio_path),
    )

    output_path = Path(
        args.output
        or settings.get(
            "watchlist_candidates_workbook_path",
            "output/relatorios/watchlist_candidates.xlsx",
        )
    )
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    write_workbook(frame, output_path)

    candidate_count = int((frame["Symbol"] != "").sum())
    print(
        f"{candidate_count} candidatos escritos em {output_path}. "
        f"Marque 'Incluir' nas linhas desejadas (ou digite um ticker nas "
        f"linhas em branco no fim) e rode "
        f"watchlist.apply_candidates_workbook depois de salvar."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

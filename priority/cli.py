from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from priority.models import PriorityReport
from priority.pipeline import build_buy_priority, build_sell_priority
from priority.report import write_priority_report

ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _held_symbols(portfolio_path: Path) -> frozenset[str] | None:
    """
    None significa "portfolio.csv ausente -- não filtrar" (distinto de um
    conjunto vazio, que significaria "carteira sem holdings").
    """
    if not portfolio_path.exists():
        return None

    with portfolio_path.open(encoding="utf-8", newline="") as handle:
        return frozenset(
            row["symbol"].strip().upper()
            for row in csv.DictReader(handle)
            if row.get("symbol", "").strip()
        )


def build_priority_from_files(
    *,
    ranking_report_path: Path,
    research_ranking_report_path: Path,
    portfolio_path: Path,
    portfolio_report_path: Path | None = None,
    exclude_held: bool = False,
    top_n: int | None = None,
    sector: str | None = None,
) -> PriorityReport:
    """
    Monta o PriorityReport lendo os artefatos já gerados em disco (não
    recalcula scoring/ranking/rebalance). A venda copia exclusivamente as
    ações de `portfolio_report.json`; a prioridade de compra fica None quando
    o screener amplo ainda não foi rodado (python -m portfolio.model_portfolio).
    """
    held = _held_symbols(portfolio_path)
    portfolio_report_path = portfolio_report_path or (
        ranking_report_path.parent / "portfolio_report.json"
    )
    portfolio_data = _load_json(portfolio_report_path)
    rebalance_actions = (
        portfolio_data.get("rebalance", {}).get("actions", ())
        if portfolio_data is not None
        else ()
    )
    weights_by_symbol = (
        portfolio_data.get("allocation", {}).get("by_symbol", {})
        if portfolio_data is not None
        else {}
    )

    ranking_data = _load_json(ranking_report_path)
    sell = build_sell_priority(
        ranking_data["companies"] if ranking_data else (),
        rebalance_actions=rebalance_actions,
        held_symbols=held,
        weights_by_symbol=weights_by_symbol,
    )

    research_data = _load_json(research_ranking_report_path)
    buy = None
    if research_data is not None:
        buy = build_buy_priority(
            research_data["companies"],
            held_symbols=held or frozenset(),
            exclude_held=exclude_held,
            top_n=top_n,
            sector=sector,
        )

    return PriorityReport(sell=sell, buy=buy)


def _print_sell_table(report: PriorityReport) -> None:
    print("=== PRIORIDADE DE VENDA (carteira atual) ===")

    if not report.sell.items:
        print("(nenhum holding classificado -- carteira/ranking ausente.)")
        return

    print(f"{'#':>3} {'symbol':10} {'score':>6} {'acao':8}  justificativa")

    for index, item in enumerate(report.sell.items, start=1):
        score = item.investment_score or 0.0
        reasons = item.reason or ", ".join(item.triggered_rules) or "-"
        print(
            f"{index:>3} {item.symbol:10} {score:>6.1f} "
            f"{item.action:8}  {reasons}"
        )


def _print_buy_table(report: PriorityReport) -> None:
    if report.buy is None:
        print(
            "\n(Sem ranking amplo do screener disponível -- rode "
            "'python -m portfolio.model_portfolio' primeiro.)"
        )
        return

    print(
        f"\n=== PRIORIDADE DE COMPRA (screener, "
        f"{len(report.buy.items)} de {report.buy.total_candidate_count} "
        "candidatos) ==="
    )

    if not report.buy.items:
        print("(nenhum candidato após os filtros aplicados.)")
        return

    print(f"{'#':>3} {'symbol':10} {'setor':22} {'score':>6}  ja_possui")

    for item in report.buy.items:
        score = item.investment_score or 0.0
        print(
            f"{item.candidate_rank:>3} {item.symbol:10} "
            f"{item.sector:22} {score:>6.1f}  "
            f"{'sim' if item.already_held else '-'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Classificação individual de prioridade de venda (carteira "
            "atual) e de compra (screener). Não distribui peso nem aplica "
            "teto de setor -- apenas ordena por qualidade."
        )
    )
    parser.add_argument(
        "--ranking-report",
        default=str(ROOT / "output" / "dados" / "ranking_report.json"),
    )
    parser.add_argument(
        "--research-ranking-report",
        default=str(ROOT / "output" / "dados" / "research_ranking_report.json"),
    )
    parser.add_argument(
        "--portfolio",
        default=str(ROOT / "config" / "portfolio.csv"),
    )
    parser.add_argument(
        "--portfolio-report",
        default=str(ROOT / "output" / "dados" / "portfolio_report.json"),
        help=(
            "Relatório de carteira que contém as ações oficiais de rebalance. "
            "Sem ele, a prioridade de venda fica vazia."
        ),
    )
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--sector", default=None)
    parser.add_argument("--exclude-held", action="store_true")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime o relatório completo em JSON em vez de tabelas.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Também grava o relatório em JSON neste caminho.",
    )
    args = parser.parse_args()

    report = build_priority_from_files(
        ranking_report_path=Path(args.ranking_report),
        research_ranking_report_path=Path(args.research_ranking_report),
        portfolio_path=Path(args.portfolio),
        portfolio_report_path=Path(args.portfolio_report),
        exclude_held=args.exclude_held,
        top_n=args.top,
        sector=args.sector,
    )

    if args.output:
        write_priority_report(report, Path(args.output))

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_sell_table(report)
        _print_buy_table(report)


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from ranking.models import RankingReport


def write_ranking_report(report: RankingReport, path: str | Path) -> Path:
    if not isinstance(report, RankingReport):
        raise TypeError("report deve ser RankingReport.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


CANDIDATE_CSV_COLUMNS = (
    "candidate_rank",
    "symbol",
    "name",
    "sector",
    "industry",
    "investment_score",
    "opportunity_score",
    "conviction_score",
    "confidence_score",
    "market_rank",
    "sector_rank",
    "price",
    "market_cap",
    "already_held",
)


def _csv_number(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return number if number == number else ""


def write_candidate_ranking_csv(
    report: RankingReport,
    path: str | Path,
    *,
    metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path:
    """
    Escreve o grupo de candidatos (papéis que passaram as salvaguardas e
    receberam ``candidate_rank``) em CSV, ordenado por ``candidate_rank`` — a
    ordem de compra sugerida pelo modelo. Vai além das posições da carteira:
    lista todos os candidatos, não só as 20 selecionadas. Enriquece com
    nome/indústria/preço/market cap vindos das observações da coleta
    (``metadata``); campos ausentes ficam vazios.
    """
    if not isinstance(report, RankingReport):
        raise TypeError("report deve ser RankingReport.")
    company_metadata = metadata or {}
    candidates = sorted(
        (
            company
            for company in report.companies
            if company.safeguard_passed and company.candidate_rank is not None
        ),
        key=lambda company: (company.candidate_rank, company.symbol),
    )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(CANDIDATE_CSV_COLUMNS))
        writer.writeheader()
        for company in candidates:
            details = company_metadata.get(company.symbol, {})
            writer.writerow(
                {
                    "candidate_rank": company.candidate_rank,
                    "symbol": company.symbol,
                    "name": str(details.get("name", "")).strip(),
                    "sector": company.sector,
                    "industry": str(details.get("industry", "")).strip(),
                    "investment_score": _csv_number(company.investment_score),
                    "opportunity_score": _csv_number(company.opportunity_score),
                    "conviction_score": _csv_number(company.conviction_score),
                    "confidence_score": _csv_number(company.confidence_score),
                    "market_rank": company.market_rank
                    if company.market_rank is not None
                    else "",
                    "sector_rank": company.sector_rank
                    if company.sector_rank is not None
                    else "",
                    "price": _csv_number(details.get("price")),
                    "market_cap": _csv_number(details.get("market_cap")),
                    "already_held": company.already_held,
                }
            )
    return output

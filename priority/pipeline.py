from __future__ import annotations

from typing import Any, Iterable

from priority.models import (
    BuyPriorityItem,
    BuyPriorityReport,
    SellPriorityItem,
    SellPriorityReport,
)


def build_sell_priority(
    ranked_companies: Iterable[dict[str, Any]],
    *,
    held_symbols: frozenset[str] | None = None,
    weights_by_symbol: dict[str, float] | None = None,
) -> SellPriorityReport:
    """
    Classifica os holdings da carteira atual por Investment Score
    decrescente. Sinaliza SELL para quem tem ao menos um Deal Breaker ativo
    (o mesmo critério do modo sell-only do rebalance); HOLD para o resto.

    `ranked_companies` é a lista já serializada de RankedCompany (o campo
    "companies" de um RankingReport.to_dict()) computada sobre o dataframe
    da execução atual. Quando `held_symbols` é fornecido, filtra para
    incluir apenas quem de fato está na carteira (protege contra a
    watchlist conter nomes além dos holdings reais). Pura -- sem I/O, não
    recalcula score nem decisão.
    """
    items: list[SellPriorityItem] = []

    for company in ranked_companies:
        symbol = str(company.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        if held_symbols is not None and symbol not in held_symbols:
            continue

        deal_breakers = tuple(company.get("deal_breakers") or ())
        current_weight = (
            (weights_by_symbol or {}).get(symbol)
        )

        items.append(
            SellPriorityItem(
                symbol=symbol,
                investment_score=company.get("investment_score"),
                action="SELL" if deal_breakers else "HOLD",
                deal_breakers=deal_breakers,
                current_weight=current_weight,
            )
        )

    items.sort(
        key=lambda item: (
            item.investment_score is None,
            -(item.investment_score or 0.0),
            item.symbol,
        )
    )

    return SellPriorityReport(items=tuple(items))


def build_buy_priority(
    ranked_companies: Iterable[dict[str, Any]],
    *,
    held_symbols: frozenset[str] = frozenset(),
    exclude_held: bool = False,
    top_n: int | None = None,
    sector: str | None = None,
) -> BuyPriorityReport:
    """
    Classifica candidatos do screener (universo amplo) por `candidate_rank`
    (qualidade decrescente). Só inclui quem passou o safeguard governado
    (sem Deal Breaker, confiança mínima) -- o mesmo critério do ranking.

    Não atribui peso-alvo nem aplica teto de posição/setor: é uma
    classificação individual, não uma construção de carteira (isso é
    responsabilidade de portfolio.model_portfolio, um instrumento
    diferente). Pura -- sem I/O.
    """
    candidates = [
        company
        for company in ranked_companies
        if company.get("safeguard_passed")
        and company.get("candidate_rank") is not None
    ]

    if sector is not None:
        candidates = [
            company
            for company in candidates
            if company.get("sector") == sector
        ]

    total_candidate_count = len(candidates)

    items: list[BuyPriorityItem] = []

    for company in candidates:
        symbol = str(company.get("symbol", "")).strip().upper()
        if not symbol:
            continue

        is_held = symbol in held_symbols
        if exclude_held and is_held:
            continue

        items.append(
            BuyPriorityItem(
                symbol=symbol,
                sector=str(company.get("sector") or ""),
                candidate_rank=int(company["candidate_rank"]),
                investment_score=company.get("investment_score"),
                opportunity_score=company.get("opportunity_score"),
                conviction_score=company.get("conviction_score"),
                confidence_score=company.get("confidence_score"),
                already_held=is_held,
            )
        )

    items.sort(key=lambda item: item.candidate_rank)

    if top_n is not None:
        items = items[:top_n]

    return BuyPriorityReport(
        items=tuple(items),
        total_candidate_count=total_candidate_count,
    )

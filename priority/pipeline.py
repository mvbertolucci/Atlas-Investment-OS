from __future__ import annotations

from collections.abc import Mapping
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
    rebalance_actions: Iterable[Mapping[str, Any] | Any] = (),
    held_symbols: frozenset[str] | None = None,
    weights_by_symbol: dict[str, float] | None = None,
) -> SellPriorityReport:
    """
    Ordena e apresenta as ações já decididas pelo rebalance oficial.

    `ranked_companies` é a lista já serializada de RankedCompany (o campo
    "companies" de um RankingReport.to_dict()) computada sobre o dataframe
    da execução atual e fornece apenas score/Deal Breakers explicativos.
    `rebalance_actions` é a fonte exclusiva de `action`, justificativa e
    prioridade. Sem ações de rebalance não há classificação de venda: esta
    função nunca inventa SELL/HOLD a partir de Deal Breakers. Quando
    `held_symbols` é fornecido, mantém apenas holdings reais. Pura -- sem I/O,
    não recalcula score, regra ou decisão.
    """
    companies_by_symbol = {
        str(company.get("symbol", "")).strip().upper(): company
        for company in ranked_companies
        if str(company.get("symbol", "")).strip()
    }
    items: list[SellPriorityItem] = []

    for raw_action in rebalance_actions:
        action_data = (
            raw_action
            if isinstance(raw_action, Mapping)
            else raw_action.to_dict()
        )
        symbol = str(action_data.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        if held_symbols is not None and symbol not in held_symbols:
            continue

        action = str(action_data.get("action", "")).strip().upper()
        if action in ("BUY", "ACOMPANHAR"):
            # ACOMPANHAR is a comparative-only signal, never a sell
            # decision -- excluded the same way BUY already is.
            continue
        if action not in {"SELL", "TRIM", "HOLD", "REVISAR"}:
            raise ValueError(
                f"Ação de rebalance inválida para prioridade de venda: {action!r}."
            )

        company = companies_by_symbol.get(symbol, {})
        deal_breakers = tuple(company.get("deal_breakers") or ())
        current_weight = action_data.get(
            "current_weight",
            (weights_by_symbol or {}).get(symbol),
        )

        items.append(
            SellPriorityItem(
                symbol=symbol,
                investment_score=company.get("investment_score"),
                action=action,
                deal_breakers=deal_breakers,
                current_weight=current_weight,
                reason=str(action_data.get("reason") or ""),
                triggered_rules=tuple(action_data.get("triggered_rules") or ()),
                missing_data=tuple(action_data.get("missing_data") or ()),
                priority=int(action_data.get("priority", 100)),
            )
        )

    items.sort(
        key=lambda item: (
            item.priority,
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

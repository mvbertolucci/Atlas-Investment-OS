"""
Priority: classificação individual de prioridade de venda/compra.

Camada de consulta read-only sobre ações já computadas pelo rebalance e dados
já computados pelo ranking/screener -- não recalcula score, decisão, regra ou
Deal Breaker, e não constrói carteira (sem peso, sem teto de setor). Disponível como comando
(`python -m priority.cli`), artefato (`output/priority_report.json`),
recurso na API (`/priority`) e método no SDK.
"""
from __future__ import annotations

from priority.models import (
    BuyPriorityItem,
    BuyPriorityReport,
    PriorityReport,
    SellPriorityItem,
    SellPriorityReport,
)
from priority.pipeline import build_buy_priority, build_sell_priority
from priority.report import write_priority_report

__all__ = [
    "BuyPriorityItem",
    "BuyPriorityReport",
    "PriorityReport",
    "SellPriorityItem",
    "SellPriorityReport",
    "build_buy_priority",
    "build_sell_priority",
    "write_priority_report",
]

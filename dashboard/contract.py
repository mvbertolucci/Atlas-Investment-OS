from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# Versão do contrato. Incrementar SOMENTE de forma deliberada quando a forma
# serializada mudar, para que consumidores (dashboard, API, SDK) saibam
# reconciliar. Mudança de contrato é decisão explícita, nunca incidental.
DASHBOARD_CONTRACT_VERSION = "1.1"


@dataclass(frozen=True)
class DashboardView:
    """
    Contrato read-only agregado do v2.0 Platform.

    Reúne as visões que o Atlas já produz -- empresas, mercado, carteira e
    outcomes -- numa forma única, versionada e serializável, pensada para um
    dashboard/API/SDK futuros. Não recomputa score algum e não altera nenhuma
    decisão; é apenas montagem.

    Os campos guardam dicionários já serializados (a saída de `to_dict()` dos
    objetos de domínio) para que o contrato seja estável e independente das
    classes concretas que os originaram.
    """

    companies: tuple[dict[str, Any], ...] = ()
    market: dict[str, Any] | None = None
    portfolio: dict[str, Any] | None = None
    outcomes: dict[str, Any] | None = None
    priority: dict[str, Any] | None = None
    contract_version: str = DASHBOARD_CONTRACT_VERSION
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
            "market": self.market,
            "companies": [dict(company) for company in self.companies],
            "portfolio": self.portfolio,
            "outcomes": self.outcomes,
            "priority": self.priority,
        }

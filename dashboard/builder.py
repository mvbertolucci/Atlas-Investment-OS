from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from dashboard.contract import DashboardView


def _as_dict(obj: Any) -> dict[str, Any] | None:
    """
    Serializa um objeto de domínio via seu `to_dict()`, ou aceita um dict já
    pronto. `None` passa como `None`. Qualquer outra coisa é erro de contrato.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj

    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if not isinstance(result, dict):
            raise TypeError(
                "to_dict() deve retornar dict; recebido "
                f"{type(result).__name__}."
            )
        return result

    raise TypeError(
        f"Objeto sem to_dict() e não é dict: {type(obj).__name__}."
    )


def build_dashboard_view(
    companies: Iterable[Any] = (),
    *,
    market: Any = None,
    portfolio: Any = None,
    outcomes: Any = None,
    priority: Any = None,
    decision_queue: Any = None,
    portfolio_scenario: Any = None,
    decision_journal: Any = None,
) -> DashboardView:
    """
    Monta o `DashboardView` agregando os outputs existentes do Atlas.

    Aceita objetos de domínio (CompanyReport, MarketSummary, PortfolioReport,
    OutcomeAnalyticsReport -- qualquer coisa com `to_dict()`) ou dicts já
    serializados. É agregação read-only: não recalcula nem altera nada.

    `companies` vazio, `market`/`portfolio`/`outcomes` ausentes produzem um
    contrato válido e mínimo (companies=() e os demais None).
    """
    company_dicts = tuple(
        serialized
        for serialized in (_as_dict(company) for company in companies)
        if serialized is not None
    )

    return DashboardView(
        companies=company_dicts,
        market=_as_dict(market),
        portfolio=_as_dict(portfolio),
        outcomes=_as_dict(outcomes),
        priority=_as_dict(priority),
        decision_queue=_as_dict(decision_queue),
        portfolio_scenario=_as_dict(portfolio_scenario),
        decision_journal=_as_dict(decision_journal),
    )


def write_dashboard_view(
    view: DashboardView,
    output_path: Path,
) -> Path:
    """
    Serializa o contrato para JSON (mesma convenção de `write_outcome_report`).
    """
    if not isinstance(view, DashboardView):
        raise TypeError("view deve ser DashboardView.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(view.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path

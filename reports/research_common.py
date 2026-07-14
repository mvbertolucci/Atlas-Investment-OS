from __future__ import annotations

from typing import Any


def company_status(company: dict[str, Any]) -> tuple[str, str]:
    """
    Deriva o rótulo de status de uma empresa (candidato/bloqueada/fora do
    universo) a partir dos campos já computados pelo ranking -- nunca
    recalcula elegibilidade ou score. Compartilhado por research_html.py e
    research_excel.py para as duas visões nunca divergirem no critério.

    Retorna (rótulo, categoria), onde categoria é "good"/"bad"/"neutral"
    (cada consumidor mapeia para sua própria cor/estilo).
    """
    if company.get("safeguard_passed") and company.get("candidate_rank") is not None:
        return f"Candidato #{company['candidate_rank']}", "good"
    if not company.get("universe_eligible"):
        return "Fora do universo", "neutral"
    reasons = company.get("safeguard_reasons") or []
    if reasons:
        return "Bloqueado: " + ", ".join(reasons), "bad"
    return "—", "neutral"

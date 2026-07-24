from __future__ import annotations

from typing import Any, Mapping, Sequence

from analytics.mapper import DERIVED_DEPENDENCIES
from reports.field_materiality import materiality_note


# Rótulos legíveis por campo. Chaves em snake_case como o pipeline emite.
FIELD_LABELS = {
    "net_debt_ebitda": "Net Debt/EBITDA",
    "net_debt": "Dívida líquida",
    "net_debt_total_equity": "Dívida líquida/Patrimônio",
    "total_debt": "dívida total",
    "total_cash": "caixa total",
    "ebitda": "EBITDA",
    "ebit": "EBIT",
    "enterprise_value": "enterprise value",
    "market_cap": "valor de mercado",
    "free_cashflow": "fluxo de caixa livre",
    "fcf_yield": "FCF Yield",
    "shareholder_yield": "Shareholder Yield",
    "dividend_rate": "dividendo por ação",
    "price": "preço",
    "consensus_target": "preço-alvo de consenso",
    "target_upside": "upside vs. alvo",
    "ev_ebit": "EV/EBIT",
    "ev_ebitda": "EV/EBITDA",
    "current_liquidity": "liquidez corrente",
    "roe": "ROE",
    "f_score_annual": "F-Score Piotroski (anual)",
    "f_score": "F-Score Piotroski",
}

# Frase por status de evidência (providers.evidence.DataValueStatus).
_STATUS_REASON = {
    "unavailable": "nenhuma fonte retornou o dado",
    "invalid": "o valor foi rejeitado (implausível ou fontes divergem)",
    "stale": "o dado está além do prazo de validade",
    "not_applicable": "não se aplica a esta empresa/setor",
    "missing": "não foi coletado",
    "present": "presente",
}


def humanize_field(field: str) -> str:
    key = str(field).strip()
    if key.lower() in FIELD_LABELS:
        return FIELD_LABELS[key.lower()]
    return key.replace("_", " ").strip().title()


def _status_phrase(status: str | None, detail: str | None) -> str:
    base = _STATUS_REASON.get(str(status or "").lower(), "não foi coletado")
    if status == "stale" and detail:
        # Desde a ADR-047, `stale` num fundamento não significa mais "passou do
        # relógio": significa que o período SEGUINTE já venceu o prazo de
        # arquivamento e não o temos — ou seja, existe dado mais novo publicado.
        # A distinção importa porque só nesse caso recoletar resolve.
        if "next period overdue" in str(detail):
            return (
                "o período seguinte já venceu o prazo de divulgação e não foi "
                "coletado"
            )
        return f"{base} ({detail})"
    if status == "not_applicable" and detail:
        return f"{base} — {detail}"
    return base


def _dependency_culprit(
    field: str,
    field_evidence: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Para um campo derivado, retorna (dependência, frase) da pior dependência.

    A pior é a primeira não-PRESENT na ordem declarada em DERIVED_DEPENDENCIES —
    é o insumo que impediu o cálculo (ex.: total_cash inválido derruba
    net_debt_ebitda).
    """
    for dependency in DERIVED_DEPENDENCIES.get(field, ()):  # ordem importa
        evidence = field_evidence.get(dependency)
        status = str((evidence or {}).get("status", "")).lower()
        if evidence is not None and status and status != "present":
            return dependency, _status_phrase(status, (evidence or {}).get("detail"))
    return None


def reason_for_field(
    field: str,
    field_evidence: Mapping[str, Any] | None,
) -> str | None:
    """Explica por que um campo está ausente, a partir do `field_evidence`.

    Retorna None quando não há evidência registrada — o chamador cai no rótulo
    simples ("Falta: X") sem inventar uma causa.
    """
    if not field_evidence:
        return None
    label = humanize_field(field)
    # Campo derivado: a causa costuma estar numa dependência ausente/inválida.
    if field in DERIVED_DEPENDENCIES:
        culprit = _dependency_culprit(field, field_evidence)
        if culprit is not None:
            dep_label = humanize_field(culprit[0])
            return f"{label} não foi calculado: {dep_label} — {culprit[1]}."
        # Dependências presentes, mas o resultado é indefinido (ex.: divisão por
        # EBITDA zero/negativo). Só afirmamos isso se há evidência das deps.
        if any(dep in field_evidence for dep in DERIVED_DEPENDENCIES[field]):
            return (
                f"{label} não foi calculado: as dependências estão presentes, mas o "
                "resultado é indefinido (ex.: EBITDA zero/negativo)."
            )
        return None
    evidence = field_evidence.get(field)
    if evidence is None:
        return None
    phrase = _status_phrase(
        str(evidence.get("status", "")).lower(), evidence.get("detail")
    )
    return f"{label}: {phrase}."


def build_missing_reasons(
    fields: Sequence[str],
    field_evidence: Mapping[str, Any] | None,
    *,
    values: Mapping[str, Any] | None = None,
    sector: Any = None,
) -> tuple[dict[str, str], ...]:
    """Lista {field, label, reason, materiality} para cada campo ausente.

    `materiality` responde "isso muda alguma coisa?" a partir da
    configuração governada (ADR-050), para o leitor não precisar refazer
    esse julgamento a cada leitura. Campo novo e opcional: chamadores
    antigos seguem funcionando e simplesmente recebem string vazia.
    """
    out: list[dict[str, str]] = []
    for field in fields:
        reason = reason_for_field(field, field_evidence)
        note = materiality_note(
            field, (values or {}).get(str(field)), sector=sector
        )
        out.append(
            {
                "field": str(field),
                "label": humanize_field(field),
                "reason": reason or "",
                "materiality": note or "",
            }
        )
    return tuple(out)

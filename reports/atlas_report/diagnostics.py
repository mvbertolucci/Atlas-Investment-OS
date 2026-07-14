from __future__ import annotations

import re

_CONFLICT_SECTION_RE = re.compile(r"^#{2,3}\s*⚠️?\s*Conflitos sinalizados", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s")
_NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s")


def extract_status_conflicts(status_md_text: str) -> tuple[str, ...]:
    """
    Lê o texto de STATUS.md (passado pelo caller, nunca aberto aqui) e
    extrai contagens de conflitos já sinalizados pelo próprio documento:
    itens numerados sob "Conflitos sinalizados" (motores decidindo a
    mesma coisa) e linhas de tabela marcadas "CONFLITO A RESOLVER"
    (fórmulas com mais de uma implementação). Não interpreta nem julga
    nada -- só conta marcadores que o STATUS.md já usa para se
    autodescrever.
    """
    if not status_md_text:
        return ()

    lines = status_md_text.splitlines()

    engine_conflicts = 0
    in_section = False
    for line in lines:
        stripped = line.strip()
        if _CONFLICT_SECTION_RE.match(stripped):
            in_section = True
            continue
        if in_section:
            if _HEADING_RE.match(stripped) or stripped.startswith("---"):
                in_section = False
                continue
            if _NUMBERED_ITEM_RE.match(stripped):
                engine_conflicts += 1

    formula_conflicts = sum(
        1
        for line in lines
        if "CONFLITO A RESOLVER" in line and line.strip().startswith("|")
    )

    alerts: list[str] = []
    if engine_conflicts:
        plural = "s" if engine_conflicts != 1 else ""
        alerts.append(
            f"{engine_conflicts} conflito{plural} entre motores de decisão "
            "sinalizado(s) em STATUS.md — ver seção 1."
        )
    if formula_conflicts:
        plural = "s" if formula_conflicts != 1 else ""
        alerts.append(
            f"{formula_conflicts} fórmula{plural} com implementação "
            "conflitante sinalizada em STATUS.md — ver seção 2."
        )
    return tuple(alerts)

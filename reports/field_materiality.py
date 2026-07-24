"""Materialidade de uma lacuna de dado: o que ela pode, de fato, mudar.

Um campo ausente ou defasado aparece hoje com o mesmo peso visual de
qualquer outro, e o leitor precisa refazer a cada leitura o julgamento de
"isso muda alguma coisa?". Medido no snapshot de 2026-07-24, dos 77 campos
de evidência de um papel:

- **37** não entram no score nem governam limiar: a lacuna só reduz o
  Data Freshness, nunca diz nada sobre a empresa;
- **27** entram no score;
- **11** não entram direto, mas compõem um campo que entra (`total_cash` ->
  `net_debt_ebitda`, `free_cashflow` -> `fcf_yield`);
- **2** (`altman_z`, `short_float`) são governados exclusivamente por
  limiar rígido -- os únicos onde a distância até o limite responde
  sozinha se a lacuna importa.

O papel de cada campo é lido da configuração governada, não de uma lista
paralela que envelheceria em silêncio: `config/features.yaml` (o que é
pontuado e com que peso), `config/model.yaml` (peso de cada fator) e
`config/deal_breakers.json` (limiares e isenções setoriais).

Limite deliberado: nada aqui afirma que "a decisão não muda". O teto que
calculamos é sobre o **Investment Score**; a decisão sai de Opportunity e
Conviction (`decision/policy.py`), que derivam dele por transformação
própria. Afirmar o passo seguinte exigiria simular a decisão campo a campo
-- caro e fora deste escopo. Dizer menos do que se sabe é preferível a dizer
mais.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from analytics.mapper import COLUMN_MAP, DERIVED_DEPENDENCIES

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

# Margem exigida para afirmar que a lacuna não aciona o limiar: o valor
# precisaria dobrar (limite máximo) ou cair pela metade (limite mínimo).
# Abaixo disso mostramos a distância sem adjetivo -- a folga é do leitor.
SAFE_MARGIN = 2.0


@dataclass(frozen=True)
class FieldRole:
    """Papel de um campo na decisão, lido da configuração governada."""

    scored: bool = False
    factor: str | None = None
    max_score_swing: float = 0.0
    threshold_kind: str | None = None  # "min" | "max"
    threshold: float | None = None
    exempt_sectors: tuple[str, ...] = ()


def _canonical(field: str) -> str:
    """Nome canônico do campo.

    `current_ratio` e `current_liquidity` são o MESMO número sob dois nomes
    (`COLUMN_MAP`); tratá-los como campos distintos faria o `current_ratio`
    parecer governado só por limiar quando ele é pontuado (peso 0,05).
    """
    name = str(field).strip()
    return COLUMN_MAP.get(name, name)


@lru_cache(maxsize=1)
def load_field_roles(config_dir: str | None = None) -> dict[str, FieldRole]:
    base = Path(config_dir) if config_dir else CONFIG_DIR
    features = yaml.safe_load((base / "features.yaml").read_text(encoding="utf-8")) or {}
    model = yaml.safe_load((base / "model.yaml").read_text(encoding="utf-8")) or {}
    breakers = json.loads((base / "deal_breakers.json").read_text(encoding="utf-8"))

    factor_weights = model.get("factor_weights") or {}
    roles: dict[str, FieldRole] = {}

    for factor, factor_weight in factor_weights.items():
        for name, cfg in (features.get(str(factor)) or {}).items():
            if not isinstance(cfg, dict):
                continue
            column = _canonical(str(cfg.get("column") or name))
            # Os pesos internos de cada fator somam 1,0 (travado em
            # test_governed_config), então o deslocamento máximo que uma
            # feature pode causar no Investment Score é o produto dos dois
            # pesos: o percentil dela varia de 0 a 100, e nada mais.
            swing = float(factor_weight) * float(cfg.get("weight", 0.0)) * 100.0
            current = roles.get(column)
            if current is None or swing > current.max_score_swing:
                roles[column] = FieldRole(
                    scored=True, factor=str(factor), max_score_swing=swing
                )

    for key, value in breakers.items():
        for suffix, kind in (("_min", "min"), ("_max", "max")):
            if not key.endswith(suffix):
                continue
            column = _canonical(key[: -len(suffix)])
            exempt = (
                breakers.get(f"{key[:-len(suffix)]}_exempt_sectors")
                # `f_score_annual_min` tem isenção sob `f_score_exempt_sectors`
                or breakers.get(f"{key[:-len(suffix)].replace('_annual','')}_exempt_sectors")
                or ()
            )
            base_role = roles.get(column, FieldRole())
            roles[column] = FieldRole(
                scored=base_role.scored,
                factor=base_role.factor,
                max_score_swing=base_role.max_score_swing,
                threshold_kind=kind,
                threshold=float(value),
                exempt_sectors=tuple(str(s) for s in exempt),
            )
    return roles


def _sector_is_exempt(sector: Any, role: FieldRole) -> bool:
    target = str(sector or "").strip().casefold()
    return any(str(s).strip().casefold() == target for s in role.exempt_sectors)


def _headroom(value: float, role: FieldRole) -> float | None:
    """Quantas vezes o valor precisaria mudar para cruzar o limiar."""
    if role.threshold is None or not value:
        return None
    if role.threshold_kind == "max":
        return role.threshold / value if value > 0 else None
    return value / role.threshold if role.threshold else None


def materiality_note(
    field: str,
    value: Any = None,
    *,
    sector: Any = None,
    roles: Mapping[str, FieldRole] | None = None,
) -> str | None:
    """Frase sobre o que a lacuna neste campo pode mudar, ou None.

    Deliberadamente silenciosa quando não há afirmação honesta a fazer.
    """
    table = roles if roles is not None else load_field_roles()
    canonical = _canonical(field)
    role = table.get(canonical)

    if role is None:
        # Antes de declarar um campo inconsequente, checar se ele ALIMENTA
        # algum campo que importa. `total_cash` não é pontuado nem governa
        # limiar por si, mas compõe `net_debt_ebitda`, que é as duas coisas --
        # afirmar "não muda nada" ali seria falso, e falso na direção que
        # tranquiliza, que é a pior.
        dependents = sorted(
            target
            for target, deps in DERIVED_DEPENDENCIES.items()
            if canonical in deps and _canonical(target) in table
        )
        if dependents:
            names = ", ".join(dependents)
            return (
                f"não entra direto no score, mas compõe {names}, que "
                f"entra — a lacuna se propaga"
            )
        return (
            "não entra no score nem em deal breaker; o único efeito é reduzir "
            "o Data Freshness"
        )

    parts: list[str] = []
    if role.threshold is not None:
        if _sector_is_exempt(sector, role):
            parts.append(
                f"o setor é isento do deal breaker deste campo, então a lacuna "
                f"não pode acioná-lo"
            )
        else:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = None
            headroom = _headroom(numeric, role) if numeric is not None else None
            limit = f"{role.threshold:g}"
            if headroom is not None and headroom >= SAFE_MARGIN:
                # A direção importa: um limite máximo é acionado quando o
                # valor CRESCE; um mínimo, quando ele CAI.
                movement = "crescer" if role.threshold_kind == "max" else "cair"
                parts.append(
                    f"último valor {numeric:g} contra limite de {limit}: "
                    f"precisaria {movement} {headroom:.1f}x para acionar o "
                    f"deal breaker"
                )
            elif numeric is not None:
                parts.append(
                    f"último valor {numeric:g} contra limite de {limit}"
                )
            else:
                parts.append(f"governa um deal breaker (limite {limit})")

    if role.scored:
        parts.append(
            f"entra no score pelo fator {role.factor} e desloca o Investment "
            f"Score em até {role.max_score_swing:.1f} pontos"
        )
    elif role.threshold is not None:
        parts.append("não entra no score")

    return "; ".join(parts) if parts else None

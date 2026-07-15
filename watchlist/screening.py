from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from watchlist.triggers import normalize_current_row

# --- cortes reaproveitados de config de produção, NENHUM inventado --------
# Piso de confiança do screener (config/ranking.yaml::min_confidence_score):
# abaixo dele o ranking nem chama o nome de candidato.
_MIN_CONFIDENCE = 70.0
# Faixas de "zona de compra" por Investment Score
# (models/investment_model.py::classify): >=70 Acumular, >=80 Comprar,
# >=90 Comprar Forte.
_TIER_ACUMULAR = 70.0
_TIER_COMPRAR = 80.0
_TIER_COMPRAR_FORTE = 90.0


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@dataclass(frozen=True)
class DerivedTrigger:
    condition: str
    rationale: str


def derive_trigger_condition(row: Mapping[str, Any]) -> DerivedTrigger:
    """
    Deriva uma `trigger_condition` ligada ao motivo de o nome ser digno de
    acompanhamento -- a lacuna mais restritiva entre o estado atual e uma
    compra clara (primeira regra que casa vence). Todos os cortes são
    reaproveitados de config de produção; nenhum é inventado aqui.

    `row` deve estar normalizado (`watchlist.triggers.normalize_current_row`)
    ou já trazer os campos em snake_case (confidence_score, target_upside,
    investment_score). Sem score comparável, devolve condição vazia
    (acompanhamento passivo) -- nunca inventa um gatilho.
    """
    normalized = normalize_current_row(row)
    confidence = _number(normalized.get("confidence_score"))
    target_upside = _number(normalized.get("target_upside"))
    score = _number(normalized.get("investment_score"))

    if confidence is not None and confidence < _MIN_CONFIDENCE:
        return DerivedTrigger(
            "confidence >= 70",
            "confiança abaixo do piso do screener (70); vigiar até cruzar.",
        )
    if target_upside is not None and target_upside <= 0:
        return DerivedTrigger(
            "target_upside > 0",
            "negociando no/acima do alvo de consenso; vigiar até reabrir margem.",
        )
    if score is not None:
        if score < _TIER_ACUMULAR:
            return DerivedTrigger(
                "score > 70",
                "abaixo da zona Acumular; vigiar até o score entrar na faixa.",
            )
        if score < _TIER_COMPRAR:
            return DerivedTrigger(
                "score > 80",
                "na zona Acumular; vigiar até subir para Comprar.",
            )
        if score < _TIER_COMPRAR_FORTE:
            return DerivedTrigger(
                "score > 90",
                "na zona Comprar; vigiar até subir para Comprar Forte.",
            )
        return DerivedTrigger(
            "earnings_passed",
            "já em Comprar Forte; revalidar fundamentos no próximo resultado.",
        )
    return DerivedTrigger(
        "",
        "sem score comparável neste run; acompanhamento passivo.",
    )


@dataclass(frozen=True)
class WatchlistProposal:
    symbol: str
    name: str
    sector: str
    candidate_rank: int
    investment_score: float | None
    confidence_score: float | None
    suggested_condition: str
    condition_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "candidate_rank": self.candidate_rank,
            "investment_score": self.investment_score,
            "confidence_score": self.confidence_score,
            "suggested_condition": self.suggested_condition,
            "condition_rationale": self.condition_rationale,
        }


def propose_watchlist_candidates(
    ranking_report: Any,
    *,
    analyzed_by_symbol: Mapping[str, Mapping[str, Any]],
    watchlist_symbols: Iterable[str],
    max_per_sector: int = 2,
    limit: int | None = None,
) -> tuple[WatchlistProposal, ...]:
    """
    Propõe (nunca grava) inclusões na watchlist a partir dos candidatos do
    screener, por critério estabelecido:

    - candidato de fato (safeguard_passed + candidate_rank) -- ou seja, já
      passou por confiança >= 70 e sem deal breakers (config/ranking.yaml);
    - ainda NÃO em carteira (`already_held`) nem já na watchlist;
    - no máximo `max_per_sector` por setor, na ordem de `candidate_rank`
      (mesmo critério de diversificação da carteira modelo).

    Cada proposta carrega uma `trigger_condition` sugerida, derivada do perfil
    do nome (`derive_trigger_condition`) a partir do df analisado. Retorna a
    lista ordenada por `candidate_rank`; `limit` opcional corta o total.
    """
    watched = {str(symbol).strip().upper() for symbol in watchlist_symbols}

    candidates = sorted(
        (
            company
            for company in getattr(ranking_report, "companies", ())
            if company.safeguard_passed
            and company.candidate_rank is not None
            and not company.already_held
            and str(company.symbol).strip().upper() not in watched
        ),
        key=lambda company: company.candidate_rank,
    )

    proposals: list[WatchlistProposal] = []
    per_sector: dict[str, int] = {}
    for company in candidates:
        sector = str(company.sector or "").strip() or "—"
        if per_sector.get(sector, 0) >= max_per_sector:
            continue
        per_sector[sector] = per_sector.get(sector, 0) + 1

        symbol = str(company.symbol).strip().upper()
        row = analyzed_by_symbol.get(symbol, {})
        derived = derive_trigger_condition(row)
        name = str(row.get("name", "") or "").strip() or symbol

        proposals.append(
            WatchlistProposal(
                symbol=symbol,
                name=name,
                sector=sector,
                candidate_rank=int(company.candidate_rank),
                investment_score=company.investment_score,
                confidence_score=company.confidence_score,
                suggested_condition=derived.condition,
                condition_rationale=derived.rationale,
            )
        )
        if limit is not None and len(proposals) >= limit:
            break

    return tuple(proposals)


def propose_from_broad_reports(
    report_paths: Iterable[Path | None],
    *,
    watchlist_symbols: Iterable[str],
    held_symbols: Iterable[str] = (),
    max_per_sector: int = 2,
    limit: int | None = None,
) -> tuple[WatchlistProposal, ...]:
    """
    Mesma proposta de `propose_watchlist_candidates`, mas lendo direto dos
    screeners AMPLOS (`research_ranking_report_market/adr.json`) em vez do
    `ranking_report` estreito do `--full` -- que só cobre o universo
    watchlist+carteira já analisado neste run. Comparar candidatos contra a
    própria watchlist da qual eles vieram é tautológico e nunca produz
    sugestão (achado rodando de verdade: 39/39 candidatos do ranking_report
    estreito já estavam na watchlist.csv). O pool que realmente importa para
    "ainda não está no meu radar" é o screener amplo.

    `held_symbols` precisa vir de fora (ex.: `df.loc[df.origin=="portfolio",
    "symbol"]`) -- o campo `already_held` dentro do JSON amplo é sempre
    `False`, porque aquele screener roda sem conhecimento da carteira.
    Arquivo ausente/ilegível é ignorado, nunca erro (coleta ampla é manual e
    opcional, mesmo tratamento de `reports/atlas_report/broad_screener.py`).
    """
    watched = {str(symbol).strip().upper() for symbol in watchlist_symbols}
    held = {str(symbol).strip().upper() for symbol in held_symbols}
    seen: set[str] = set()
    per_sector: dict[str, int] = {}
    proposals: list[WatchlistProposal] = []

    for path in report_paths:
        if path is None or not Path(path).exists():
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        candidates = sorted(
            (
                company
                for company in data.get("companies", ())
                if company.get("safeguard_passed")
                and company.get("candidate_rank") is not None
            ),
            key=lambda company: company.get("candidate_rank") or 10**9,
        )

        for company in candidates:
            symbol = str(company.get("symbol", "")).strip().upper()
            if not symbol or symbol in watched or symbol in held or symbol in seen:
                continue
            sector = str(company.get("sector") or "").strip() or "—"
            if per_sector.get(sector, 0) >= max_per_sector:
                continue
            per_sector[sector] = per_sector.get(sector, 0) + 1
            seen.add(symbol)

            derived = derive_trigger_condition(company)
            proposals.append(
                WatchlistProposal(
                    symbol=symbol,
                    name=str(company.get("name", "") or "").strip() or symbol,
                    sector=sector,
                    candidate_rank=int(company.get("candidate_rank")),
                    investment_score=company.get("investment_score"),
                    confidence_score=company.get("confidence_score"),
                    suggested_condition=derived.condition,
                    condition_rationale=derived.rationale,
                )
            )
            if limit is not None and len(proposals) >= limit:
                return tuple(proposals)

    return tuple(proposals)

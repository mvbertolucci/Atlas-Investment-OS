from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from decision.policy import evaluate_decision
from watchlist.auto_policy import WatchlistAutoPolicy
from watchlist.loader import load_watchlist_csv
from watchlist.models import WatchlistEntry
from watchlist.promote import (
    PromotionResult,
    RemovalResult,
    SymbolAlreadyInWatchlistError,
    SymbolNotInWatchlistError,
    promote_to_watchlist,
    remove_from_watchlist,
)
from watchlist.screening import derive_trigger_condition
from watchlist.triggers import normalize_current_row


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@dataclass(frozen=True)
class AutoInclusionCandidate:
    symbol: str
    name: str
    sector: str
    investment_score: float
    confidence_score: float
    decision_estimate: str
    source_report: str
    trigger_condition: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "investment_score": self.investment_score,
            "confidence_score": self.confidence_score,
            "decision_estimate": self.decision_estimate,
            "source_report": self.source_report,
            "trigger_condition": self.trigger_condition,
            "note": self.note,
        }


@dataclass(frozen=True)
class AutoRemovalCandidate:
    symbol: str
    investment_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "investment_score": self.investment_score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AutoCurationResult:
    included: tuple[PromotionResult, ...]
    excluded: tuple[RemovalResult, ...]
    included_failures: tuple[dict[str, str], ...]
    excluded_failures: tuple[dict[str, str], ...]
    enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "included": [item.to_dict() for item in self.included],
            "excluded": [item.to_dict() for item in self.excluded],
            "included_failures": list(self.included_failures),
            "excluded_failures": list(self.excluded_failures),
        }


def select_auto_inclusion_candidates(
    report_paths: Iterable[tuple[str, Path | None]],
    *,
    watchlist_symbols: Iterable[str],
    held_symbols: Iterable[str],
    policy: WatchlistAutoPolicy,
) -> tuple[AutoInclusionCandidate, ...]:
    """
    Combina os screeners informados (ex.: `[("sp500", path), ("broad_market",
    path)]`) e seleciona os `policy.top_n` melhores candidatos para inclusão
    automática na watchlist. Mesmo padrão defensivo de
    `watchlist.screening.propose_from_broad_reports`: arquivo ausente/
    ilegível é ignorado, nunca erro -- a coleta ampla é manual e opcional.

    A Decision usada aqui (`decision_estimate`) é uma APROXIMAÇÃO --
    `decision.policy.evaluate_decision` é chamada com `risk_penalty=0.0`
    porque o risco real só existe para nomes já coletados/pontuados
    (carteira/watchlist), não para o universo amplo ainda não coletado
    neste run. `policy.min_confidence_score` é a salvaguarda confirmada
    contra essa aproximação: reduz a chance de um nome de baixa qualidade de
    dado entrar só por causa de uma decisão otimista demais.

    Dedup entre fontes: primeira ocorrência vence, na ordem de
    `report_paths` (por convenção, S&P500 antes do mercado amplo).
    """
    watched = {str(symbol).strip().upper() for symbol in watchlist_symbols}
    held = {str(symbol).strip().upper() for symbol in held_symbols}
    seen: set[str] = set()
    candidates: list[AutoInclusionCandidate] = []

    for label, path in report_paths:
        if path is None or not Path(path).exists():
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        for company in data.get("companies", ()):
            if not company.get("safeguard_passed"):
                continue
            symbol = str(company.get("symbol", "")).strip().upper()
            if not symbol or symbol in watched or symbol in held or symbol in seen:
                continue

            investment_score = _number(company.get("investment_score"))
            confidence_score = _number(company.get("confidence_score"))
            if investment_score is None or confidence_score is None:
                continue
            if confidence_score < policy.min_confidence_score:
                continue

            deal_breakers = company.get("deal_breakers") or []
            decision_estimate = evaluate_decision(
                company.get("opportunity_score"),
                company.get("conviction_score"),
                risk_penalty=0.0,
                has_deal_breaker=bool(deal_breakers),
            )
            if decision_estimate not in policy.qualifying_decisions:
                continue

            seen.add(symbol)
            derived = derive_trigger_condition(company)
            sector = str(company.get("sector") or "").strip() or "—"
            name = str(company.get("name", "") or "").strip() or symbol

            candidates.append(
                AutoInclusionCandidate(
                    symbol=symbol,
                    name=name,
                    sector=sector,
                    investment_score=investment_score,
                    confidence_score=confidence_score,
                    decision_estimate=decision_estimate,
                    source_report=label,
                    trigger_condition=derived.condition,
                    note=(
                        f"Auto-inclusão ({label}): decisão estimada "
                        f"{decision_estimate}, Investment Score "
                        f"{investment_score:.1f}."
                    ),
                )
            )

    candidates.sort(key=lambda item: item.investment_score, reverse=True)
    return tuple(candidates[: policy.top_n])


def select_auto_removal_candidates(
    watchlist_entries: Iterable[WatchlistEntry],
    *,
    scored_frame: pd.DataFrame,
    policy: WatchlistAutoPolicy,
) -> tuple[AutoRemovalCandidate, ...]:
    """
    Seleciona entradas da watchlist elegíveis para remoção automática.

    Salvaguardas (ambas confirmadas como obrigatórias, expostas em
    `policy.safeguards` como config explícito, não hardcoded):
    - `protect_manual_entries`: só considera `entry.source == "auto"` --
      nunca remove o que foi curado à mão.
    - `protect_portfolio_holdings`: nunca remove um símbolo presente em
      `scored_frame` com `origin == "portfolio"` (holding real).

    Símbolo ausente de `scored_frame`, ou com Investment Score não numérico
    neste run, nunca é removido -- falta de dado não é evidência de score
    baixo (mesma disciplina de "nunca inventar um sinal" de
    `derive_trigger_condition`).
    """
    if "symbol" not in scored_frame.columns:
        return ()

    portfolio_symbols: set[str] = set()
    if policy.protect_portfolio_holdings and "origin" in scored_frame.columns:
        portfolio_symbols = {
            str(symbol).strip().upper()
            for symbol in scored_frame.loc[
                scored_frame["origin"] == "portfolio", "symbol"
            ]
        }

    scores_by_symbol: dict[str, float | None] = {}
    for _, row in scored_frame.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        normalized = normalize_current_row(row.to_dict())
        scores_by_symbol[symbol] = _number(normalized.get("investment_score"))

    candidates: list[AutoRemovalCandidate] = []
    for entry in watchlist_entries:
        if policy.protect_manual_entries and entry.source != "auto":
            continue
        if entry.symbol in portfolio_symbols:
            continue

        score = scores_by_symbol.get(entry.symbol)
        if score is None:
            continue
        if score < policy.exit_investment_score_threshold:
            candidates.append(
                AutoRemovalCandidate(
                    symbol=entry.symbol,
                    investment_score=score,
                    reason=(
                        f"Investment Score {score:.1f} < "
                        f"{policy.exit_investment_score_threshold:.1f}"
                    ),
                )
            )

    return tuple(candidates)


def run_auto_curation(
    *,
    watchlist_path: Path,
    sp500_report_path: Path | None,
    broad_market_report_path: Path | None,
    scored_frame: pd.DataFrame,
    policy: WatchlistAutoPolicy,
    today: date | None = None,
) -> AutoCurationResult:
    """
    Ponto de entrada único do fluxo de curadoria automática. Circuit
    breaker: com `policy.enabled is False`, retorna um resultado vazio sem
    tocar `watchlist_path` de jeito nenhum.

    Inclusão roda antes de exclusão -- um símbolo recém-incluído neste
    mesmo run nunca é candidato a remoção, porque ainda não existia em
    `entries` quando `select_auto_removal_candidates` é chamada
    (auto-resolvido pela ordem, não precisa de lógica extra).
    """
    if not policy.enabled:
        return AutoCurationResult((), (), (), (), enabled=False)

    watchlist_path = Path(watchlist_path)
    entries = (
        load_watchlist_csv(watchlist_path) if watchlist_path.exists() else ()
    )
    watchlist_symbols = [entry.symbol for entry in entries]

    held_symbols: list[str] = []
    if "origin" in scored_frame.columns and "symbol" in scored_frame.columns:
        held_symbols = [
            str(symbol).strip().upper()
            for symbol in scored_frame.loc[
                scored_frame["origin"] == "portfolio", "symbol"
            ]
        ]

    inclusion_candidates = select_auto_inclusion_candidates(
        [("sp500", sp500_report_path), ("broad_market", broad_market_report_path)],
        watchlist_symbols=watchlist_symbols,
        held_symbols=held_symbols,
        policy=policy,
    )

    included: list[PromotionResult] = []
    included_failures: list[dict[str, str]] = []
    for candidate in inclusion_candidates:
        try:
            included.append(
                promote_to_watchlist(
                    candidate.symbol,
                    candidate.note,
                    watchlist_path=watchlist_path,
                    name=candidate.name,
                    trigger_condition=candidate.trigger_condition,
                    source="auto",
                    today=today,
                )
            )
        except SymbolAlreadyInWatchlistError as exc:
            included_failures.append(
                {"symbol": candidate.symbol, "error": str(exc)}
            )

    removal_candidates = select_auto_removal_candidates(
        entries, scored_frame=scored_frame, policy=policy
    )

    excluded: list[RemovalResult] = []
    excluded_failures: list[dict[str, str]] = []
    for candidate in removal_candidates:
        try:
            excluded.append(
                remove_from_watchlist(
                    candidate.symbol,
                    candidate.reason,
                    watchlist_path=watchlist_path,
                )
            )
        except SymbolNotInWatchlistError as exc:
            excluded_failures.append(
                {"symbol": candidate.symbol, "error": str(exc)}
            )

    return AutoCurationResult(
        included=tuple(included),
        excluded=tuple(excluded),
        included_failures=tuple(included_failures),
        excluded_failures=tuple(excluded_failures),
        enabled=True,
    )

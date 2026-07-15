from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from analytics.history import earnings_between_runs
from ranking.models import RankingReport
from reports.atlas_report.broad_screener import BroadScreenerSummary, load_broad_screener_summary
from reports.atlas_report.diagnostics import extract_status_conflicts
from reports.atlas_report.ticker_detail import TickerDetail, anchor_id, build_ticker_detail
from watchlist.screening import (
    WatchlistProposal,
    propose_from_broad_reports,
)
from universe.models import UniverseReport
from watchlist.models import WatchlistReport
from watchlist.triggers import normalize_current_row

_REASON_PENDING = "razão: motor pendente"

MODES = ("full", "portfolio", "ticker")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@dataclass(frozen=True)
class PortfolioRow:
    symbol: str
    name: str
    score: float | None
    score_delta: float | None
    coverage: float | None
    action: str
    reason: str
    triggered_rules: tuple[str, ...] = ()
    legacy_flagged: bool = False
    anchor_id: str = ""
    rule_results: tuple[Mapping[str, Any], ...] = ()

    @property
    def has_state_change(self) -> bool:
        return (
            self.action != "HOLD"
            or bool(self.triggered_rules)
            or self.legacy_flagged
        )


@dataclass(frozen=True)
class WatchlistRow:
    symbol: str
    name: str
    trigger_condition: str
    status: str
    triggered_this_run: bool
    score: float | None
    age_days: int | None
    cleanup_suggested: bool
    message: str
    anchor_id: str = ""


@dataclass(frozen=True)
class EarningsRow:
    symbol: str
    name: str
    origin: str
    changed_fundamentals: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequiredAction:
    symbol: str
    kind: str
    label: str
    message: str
    engine: str = "motor pendente"


@dataclass(frozen=True)
class ScreenerSummary:
    included: bool
    total_count: int = 0
    universe_eligible_count: int = 0
    candidate_count: int = 0
    blocked_by_reason: Mapping[str, int] = field(default_factory=dict)
    new_candidates: tuple[str, ...] = ()
    top_candidates: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class DataQualityFootnote:
    fetch_failures: tuple[str, ...] = ()
    phantom_weight_pct: float = 0.0
    stale_statements: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportContext:
    mode: str
    generated_at: datetime
    snapshot_date: str
    previous_snapshot_date: str | None
    symbol_count: int
    average_coverage: float | None
    required_actions: tuple[RequiredAction, ...]
    portfolio_rows: tuple[PortfolioRow, ...]
    portfolio_included: bool
    portfolio_blocked_reason: str | None
    portfolio_warnings: tuple[str, ...]
    watchlist_rows: tuple[WatchlistRow, ...]
    watchlist_included: bool
    earnings_rows: tuple[EarningsRow, ...]
    screener: ScreenerSummary
    data_quality: DataQualityFootnote
    engine_conflicts: tuple[str, ...] = ()
    ticker_details: tuple[TickerDetail, ...] = ()
    broad_screeners: tuple[BroadScreenerSummary, ...] = ()
    watchlist_proposals: tuple[WatchlistProposal, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode inválido: {self.mode!r}. Use um de {MODES!r}.")


def _fundamental_changes(
    current: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if previous is None:
        return ()
    changes: list[str] = []
    for field_name, label in (
        ("f_score_annual", "F-Score"),
        ("roic", "ROIC"),
        ("altman_z", "Altman Z"),
        ("interest_coverage", "Interest Coverage"),
        ("target_upside", "Target Upside"),
    ):
        current_value = _number(current.get(field_name))
        previous_value = _number(previous.get(field_name))
        if current_value is None or previous_value is None:
            continue
        delta = current_value - previous_value
        if abs(delta) < 1e-9:
            continue
        changes.append(
            f"{label}: {previous_value:.2f} → {current_value:.2f} "
            f"({'+' if delta > 0 else ''}{delta:.2f})"
        )
    return tuple(changes)


def build_report_context(
    *,
    mode: str,
    df: pd.DataFrame,
    snapshot_date: str,
    previous_run_at: pd.Timestamp | None = None,
    baseline_status: str = "first_run",
    previous_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    rebalance: Mapping[str, Any] | None = None,
    portfolio_blocked_reason: str | None = None,
    portfolio_warnings: tuple[str, ...] = (),
    watchlist_report: WatchlistReport | None = None,
    ranking_report: RankingReport | None = None,
    universe_report: UniverseReport | None = None,
    fetch_failures: tuple[str, ...] = (),
    phantom_weight_pct: float = 0.0,
    stale_statements: tuple[str, ...] = (),
    status_md_text: str = "",
    holdings: tuple[Mapping[str, Any], ...] = (),
    score_history: pd.DataFrame | None = None,
    features_path: Path | None = None,
    model_path: Path | None = None,
    broad_market_report_path: Path | None = None,
    adr_report_path: Path | None = None,
) -> ReportContext:
    """
    Monta o contexto de apresentação a partir dos objetos que os motores já
    produziram neste run -- nenhuma decisão é tomada aqui, só leitura e
    formatação. `previous_by_symbol`/`baseline_status` são os MESMOS que
    PR-020/021 já calculam em run_all.py antes de save_history_snapshot.
    """
    previous_by_symbol = previous_by_symbol or {}

    current_by_symbol: dict[str, dict[str, Any]] = {}
    name_by_symbol: dict[str, str] = {}
    sector_by_symbol: dict[str, str] = {}
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        current_by_symbol[symbol] = normalize_current_row(row.to_dict())
        name_by_symbol[symbol] = str(row.get("name", "")).strip() or symbol
        sector_by_symbol[symbol] = str(row.get("sector", "")).strip()

    def _symbol_comparable(symbol: str) -> bool:
        return baseline_status == "comparable" and symbol in previous_by_symbol

    def _score_delta(symbol: str) -> float | None:
        if not _symbol_comparable(symbol):
            return None
        current_score = _number(current_by_symbol.get(symbol, {}).get("investment_score"))
        previous_score = _number(previous_by_symbol.get(symbol, {}).get("investment_score"))
        if current_score is None or previous_score is None:
            return None
        return round(current_score - previous_score, 1)

    # --- carteira -----------------------------------------------------
    # `rebalance` é o dict já serializado (RebalancePlan.to_dict(), o que
    # PortfolioReport.rebalance de fato guarda em run_all.py) -- lido, nunca
    # recalculado.
    portfolio_rows: list[PortfolioRow] = []
    required_actions: list[RequiredAction] = []
    if rebalance is None and portfolio_blocked_reason:
        required_actions.append(
            RequiredAction(
                symbol="—",
                kind="portfolio_blocked",
                label="REVISAR",
                message=portfolio_blocked_reason,
                engine="portfolio.sell_rules",
            )
        )
    if rebalance is not None:
        for action in rebalance.get("actions", []):
            symbol = str(action.get("symbol", ""))
            action_value = str(action.get("action", "HOLD"))
            reason = str(action.get("reason", "")).strip()
            triggered_rules = tuple(action.get("triggered_rules", ()) or ())
            current = current_by_symbol.get(symbol, {})
            portfolio_rows.append(
                PortfolioRow(
                    symbol=symbol,
                    name=name_by_symbol.get(symbol, symbol),
                    score=_number(current.get("investment_score")),
                    score_delta=_score_delta(symbol),
                    coverage=_number(
                        current.get("score_coverage", current.get("confidence_score"))
                    ),
                    action=action_value,
                    reason=reason or _REASON_PENDING,
                    triggered_rules=triggered_rules,
                    legacy_flagged=bool(action.get("legacy_flagged", False)),
                    anchor_id=anchor_id(symbol),
                    rule_results=tuple(action.get("rule_results", ()) or ()),
                )
            )
            if action_value != "HOLD":
                required_actions.append(
                    RequiredAction(
                        symbol=symbol,
                        kind="sell_engine",
                        label=action_value,
                        message=reason or _REASON_PENDING,
                        engine="portfolio.sell_rules",
                    )
                )

    # --- watchlist ------------------------------------------------------
    watchlist_rows: list[WatchlistRow] = []
    if watchlist_report is not None:
        for result in watchlist_report.results:
            current = current_by_symbol.get(result.symbol, {})
            watchlist_rows.append(
                WatchlistRow(
                    symbol=result.symbol,
                    name=name_by_symbol.get(result.symbol, result.symbol),
                    trigger_condition=result.trigger_condition,
                    status=result.status,
                    triggered_this_run=result.triggered_this_run,
                    score=_number(current.get("investment_score")),
                    age_days=result.age_days,
                    cleanup_suggested=result.cleanup_suggested,
                    message=result.message,
                    anchor_id=anchor_id(result.symbol),
                )
            )
            if result.triggered_this_run:
                required_actions.append(
                    RequiredAction(
                        symbol=result.symbol,
                        kind="watchlist_trigger",
                        label="TRIGGER",
                        message=result.message or _REASON_PENDING,
                        engine="watchlist.triggers",
                    )
                )

    # --- one-pager por ticker (seção de detalhe, âncorada a partir das
    # linhas de carteira/watchlist) -- só monta quando features_path foi
    # informado (run_all.py sempre informa; testes que não precisam desta
    # seção simplesmente não a recebem, em vez de quebrar).
    ticker_details: list[TickerDetail] = []
    if features_path is not None:
        holdings_by_symbol = {
            str(item.get("symbol", "")).strip().upper(): item
            for item in holdings
            if str(item.get("symbol", "")).strip()
        }
        portfolio_rows_by_symbol = {row.symbol: row for row in portfolio_rows}
        watchlist_rows_by_symbol = {row.symbol: row for row in watchlist_rows}
        detail_symbols = dict.fromkeys(
            (*portfolio_rows_by_symbol, *watchlist_rows_by_symbol)
        )
        history_df = score_history if score_history is not None else pd.DataFrame()
        as_of = pd.Timestamp(snapshot_date)
        for symbol in detail_symbols:
            portfolio_row = portfolio_rows_by_symbol.get(symbol)
            watchlist_row = watchlist_rows_by_symbol.get(symbol)
            if portfolio_row is not None:
                action = portfolio_row.action
                action_engine = "portfolio.sell_rules"
                action_reason = portfolio_row.reason
            elif watchlist_row is not None:
                action = "TRIGGER" if watchlist_row.triggered_this_run else watchlist_row.status
                action_engine = "watchlist.triggers"
                action_reason = watchlist_row.message or _REASON_PENDING
            else:
                action = "HOLD"
                action_engine = "motor pendente"
                action_reason = _REASON_PENDING
            ticker_details.append(
                build_ticker_detail(
                    symbol=symbol,
                    name=name_by_symbol.get(symbol, symbol),
                    sector=sector_by_symbol.get(symbol, ""),
                    origin="portfolio" if portfolio_row is not None else "watchlist",
                    action=action,
                    action_engine=action_engine,
                    action_reason=action_reason,
                    score=portfolio_row.score if portfolio_row is not None else watchlist_row.score,
                    score_delta=portfolio_row.score_delta if portfolio_row is not None else None,
                    coverage=portfolio_row.coverage if portfolio_row is not None else None,
                    current=current_by_symbol.get(symbol, {}),
                    df=df,
                    rule_results=portfolio_row.rule_results if portfolio_row is not None else (),
                    holding=holdings_by_symbol.get(symbol),
                    score_history=history_df,
                    features_path=features_path,
                    model_path=model_path,
                    as_of=as_of,
                )
            )

    # --- earnings (carteira + watchlist, união por símbolo) ------------
    earnings_symbols: dict[str, str] = {}
    for row in portfolio_rows:
        earnings_symbols[row.symbol] = "portfolio"
    for row in watchlist_rows:
        earnings_symbols.setdefault(row.symbol, "watchlist")

    earnings_rows: list[EarningsRow] = []
    for symbol, origin in earnings_symbols.items():
        current = current_by_symbol.get(symbol, {})
        happened = earnings_between_runs(
            current.get("earnings_date"),
            previous_run_at,
            snapshot_date,
        )
        if happened:
            earnings_rows.append(
                EarningsRow(
                    symbol=symbol,
                    name=name_by_symbol.get(symbol, symbol),
                    origin=origin,
                    changed_fundamentals=_fundamental_changes(
                        current, previous_by_symbol.get(symbol)
                    ),
                )
            )

    # --- screener (funil) -- só --full ----------------------------------
    if ranking_report is not None:
        candidates = sorted(
            (
                company
                for company in ranking_report.companies
                if company.safeguard_passed and company.candidate_rank is not None
            ),
            key=lambda company: company.candidate_rank or 10**9,
        )
        new_candidates = tuple(
            company.symbol
            for company in candidates
            if baseline_status == "comparable"
            and not previous_by_symbol.get(company.symbol, {}).get("is_candidate")
        )
        screener = ScreenerSummary(
            included=True,
            total_count=ranking_report.total_count,
            universe_eligible_count=ranking_report.universe_eligible_count,
            candidate_count=ranking_report.candidate_count,
            blocked_by_reason=ranking_report.blocked_by_reason,
            new_candidates=new_candidates,
            top_candidates=tuple(
                {
                    "symbol": company.symbol,
                    "sector": company.sector,
                    "investment_score": company.investment_score,
                    "confidence_score": company.confidence_score,
                    "candidate_rank": company.candidate_rank,
                }
                for company in candidates[:10]
            ),
        )
    else:
        screener = ScreenerSummary(included=False)

    # --- screeners de Mercado Amplo / ADR -- só lê o resultado da última
    # coleta manual (universe.collector), nunca dispara coleta nova (leva
    # horas, ver reports/atlas_report/broad_screener.py) -------------------
    as_of_for_screeners = pd.Timestamp(snapshot_date)
    broad_screeners: list[BroadScreenerSummary] = []
    if broad_market_report_path is not None:
        broad_screeners.append(
            load_broad_screener_summary(
                "Mercado Amplo", broad_market_report_path, as_of=as_of_for_screeners
            )
        )
    if adr_report_path is not None:
        broad_screeners.append(
            load_broad_screener_summary(
                "ADR", adr_report_path, as_of=as_of_for_screeners
            )
        )

    # --- sugestões para a watchlist (screener amplo -> WL, por critério) ---
    # Só PROPÕE (nunca grava): candidatos do screener AMPLO (Mercado
    # Amplo/ADR) já filtrados (confiança >= 70, sem deal breaker), fora da
    # carteira e da watchlist, diversificados por setor, cada um com uma
    # trigger_condition derivada do perfil. Ver watchlist/screening.py.
    #
    # Fonte é o screener amplo, NÃO o `ranking_report` estreito do --full: o
    # `ranking_report` só cobre o universo já mesclado watchlist+carteira, e
    # todo candidato não-held nele por definição já está na watchlist (foi
    # assim que entrou na análise) -- comparar contra a própria origem é
    # tautológico e nunca produz sugestão (achado rodando de verdade).
    # `held_symbols` vem de `origin` na df analisada, não de
    # `already_held` do JSON amplo (sempre False lá, calculado sem
    # conhecimento da carteira).
    watchlist_proposals: tuple[WatchlistProposal, ...] = ()
    if broad_market_report_path is not None or adr_report_path is not None:
        watched_symbols = [row.symbol for row in watchlist_rows]
        held_symbols = (
            df.loc[df["origin"] == "portfolio", "symbol"].tolist()
            if "origin" in df.columns
            else []
        )
        watchlist_proposals = propose_from_broad_reports(
            (broad_market_report_path, adr_report_path),
            watchlist_symbols=watched_symbols,
            held_symbols=held_symbols,
            max_per_sector=2,
        )

    average_coverage = (
        universe_report.average_data_coverage_pct
        if universe_report is not None
        else (
            round(
                pd.to_numeric(
                    df.get("Score Coverage", df.get("Confidence Score")),
                    errors="coerce",
                ).mean(),
                1,
            )
            if not df.empty
            else None
        )
    )

    return ReportContext(
        mode=mode,
        generated_at=datetime.now(),
        snapshot_date=str(snapshot_date),
        previous_snapshot_date=(
            str(previous_run_at) if previous_run_at is not None else None
        ),
        symbol_count=len(df),
        average_coverage=average_coverage,
        required_actions=tuple(required_actions),
        portfolio_rows=tuple(portfolio_rows),
        portfolio_included=rebalance is not None,
        portfolio_blocked_reason=portfolio_blocked_reason,
        portfolio_warnings=tuple(portfolio_warnings),
        watchlist_rows=tuple(watchlist_rows),
        watchlist_included=watchlist_report is not None,
        earnings_rows=tuple(earnings_rows),
        screener=screener,
        data_quality=DataQualityFootnote(
            fetch_failures=fetch_failures,
            phantom_weight_pct=phantom_weight_pct,
            stale_statements=stale_statements,
        ),
        engine_conflicts=extract_status_conflicts(status_md_text),
        ticker_details=tuple(ticker_details),
        broad_screeners=tuple(broad_screeners),
        watchlist_proposals=watchlist_proposals,
    )

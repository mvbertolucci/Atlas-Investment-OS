from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from portfolio.models import RebalanceAction, RebalancePlan
from ranking.models import RankedCompany, RankingPolicy, RankingReport
from reports.atlas_report.context import build_report_context
from reports.atlas_report.render import render_report
from watchlist.models import WatchlistReport, WatchlistTriggerResult

_EXTERNAL_RESOURCE_PATTERN = re.compile(
    r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)["\']', re.IGNORECASE
)


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "Investment Score": 80.0,
                "Confidence Score": 90.0,
                "earnings_date": None,
            },
            {
                "symbol": "BBB",
                "name": "Beta",
                "sector": "Health",
                "Investment Score": 50.0,
                "Confidence Score": 60.0,
                "earnings_date": None,
            },
        ]
    )


def _full_context():
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA", action="HOLD", current_weight=0.1, target_weight=0.1,
                target_value=100, trade_value=0, reason="ok",
            ),
            RebalanceAction(
                symbol="BBB", action="SELL", current_weight=0.1, target_weight=0.0,
                target_value=0, trade_value=-100, reason="distress disparou",
                triggered_rules=("distress",),
            ),
        ),
        warnings=("aviso de carteira",),
    )
    wl = WatchlistReport(
        results=(
            WatchlistTriggerResult(
                symbol="AAA", trigger_condition="score > 75", status="triggered",
                message="score > 75: passou a valer.",
            ),
        )
    )
    ranking = RankingReport(
        RankingPolicy("Test"),
        (
            RankedCompany(
                symbol="AAA", sector="Tech", universe_eligible=True,
                safeguard_passed=True, safeguard_reasons=(), market_rank=1,
                sector_rank=1, candidate_rank=1, investment_score=80.0,
                opportunity_score=70.0, conviction_score=80.0,
                confidence_score=90.0, deal_breakers=(),
            ),
        ),
    )
    return build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        previous_run_at=pd.Timestamp("2026-07-01"),
        rebalance=plan.to_dict(),
        portfolio_warnings=plan.warnings,
        watchlist_report=wl,
        ranking_report=ranking,
        phantom_weight_pct=3.5,
    )


def test_full_fixture_renders_all_sections() -> None:
    html = render_report(_full_context())
    for heading in (
        "Ações requeridas",
        "Carteira",
        "Watchlist",
        "Earnings",
        "Screener",
        "Qualidade de dados",
    ):
        assert f">{heading}<" in html


def test_portfolio_mode_marks_screener_not_included() -> None:
    ctx = build_report_context(
        mode="portfolio", df=_df(), snapshot_date="2026-07-14T00:00:00"
    )
    html = render_report(ctx)
    assert "Screener não incluído neste run." in html


def test_never_empty_silently_when_no_data() -> None:
    ctx = build_report_context(
        mode="portfolio", df=_df(), snapshot_date="2026-07-14T00:00:00"
    )
    html = render_report(ctx)
    assert "Carteira não incluído neste run." in html
    assert "Watchlist não incluído neste run." in html


_PILL_LABEL_PATTERN = re.compile(r'<span class="pill pill-\w+">(\w+)</span>')


def test_pill_matches_rebalance_action_1_to_1() -> None:
    """
    BBB (SELL, com mudança de estado) aparece com pill; AAA (HOLD, sem
    regra disparada) é colapsada no resumo -- nunca tem pill isolado, mas
    também nunca aparece com um pill de OUTRA decisão. Sem watchlist neste
    contexto para não confundir o pill de decisão com o badge "DISPAROU".
    """
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA", action="HOLD", current_weight=0.1, target_weight=0.1,
                target_value=100, trade_value=0, reason="ok",
            ),
            RebalanceAction(
                symbol="BBB", action="SELL", current_weight=0.1, target_weight=0.0,
                target_value=0, trade_value=-100, reason="distress disparou",
                triggered_rules=("distress",),
            ),
        ),
    )
    context = build_report_context(
        mode="full", df=_df(), snapshot_date="2026-07-14T00:00:00", rebalance=plan.to_dict()
    )
    html = render_report(context)
    pill_labels = set(_PILL_LABEL_PATTERN.findall(html))
    actions_with_state_change = {
        row.action for row in context.portfolio_rows if row.has_state_change
    }
    assert pill_labels == actions_with_state_change
    assert '<span class="pill pill-sell">SELL</span>' in html


@pytest.mark.parametrize("action_value", ["HOLD", "REVISAR", "ACOMPANHAR", "TRIM", "SELL"])
def test_pill_never_shows_a_decision_not_in_the_source_action(action_value: str) -> None:
    """
    Com uma única posição na carteira, qualquer pill renderizado em
    QUALQUER seção da página (Ações Requeridas, Sinais Informativos ou
    Carteira) só pode mostrar o mesmo action_value que veio do
    RebalanceAction -- nunca uma decisão diferente, nunca recalculada.
    """
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA",
                action=action_value,
                current_weight=0.1,
                target_weight=0.1 if action_value in ("HOLD", "REVISAR", "ACOMPANHAR") else 0.0,
                target_value=100,
                trade_value=0,
                reason="teste",
            ),
        )
    )
    ctx = build_report_context(
        mode="full", df=_df(), snapshot_date="2026-07-14T00:00:00", rebalance=plan.to_dict()
    )
    html = render_report(ctx)
    pill_labels = set(_PILL_LABEL_PATTERN.findall(html))
    assert pill_labels <= {action_value}


def test_no_external_resources_in_generated_html() -> None:
    html = render_report(_full_context())
    matches = _EXTERNAL_RESOURCE_PATTERN.findall(html)
    assert matches == []


def test_required_action_card_shows_which_engine_signed_it() -> None:
    html = render_report(_full_context())
    assert "[portfolio.sell_rules]" in html


def test_acompanhar_renders_in_informational_section_not_required_actions() -> None:
    """ACOMPANHAR must never inflate Ações Requeridas -- it belongs only in
    the separate, lighter "Sinais informativos" section, correctly pilled
    (not silently falling back to pill-revisar's default)."""
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA",
                action="ACOMPANHAR",
                current_weight=0.1,
                target_weight=0.1,
                target_value=100,
                trade_value=0,
                reason="Sinal exclusivamente relativo/informativo",
            ),
        )
    )
    ctx = build_report_context(
        mode="full", df=_df(), snapshot_date="2026-07-14T00:00:00", rebalance=plan.to_dict()
    )
    html = render_report(ctx)

    assert "<h2>Sinais informativos</h2>" in html
    assert '<span class="pill pill-acompanhar">ACOMPANHAR</span>' in html
    required_section = html.split("<h2>Sinais informativos</h2>")[0]
    assert "ACOMPANHAR" not in required_section


def test_diagnostico_heading_present() -> None:
    html = render_report(_full_context())
    assert ">Diagnóstico<" in html


def test_engine_conflict_alerts_rendered_in_diagnostico() -> None:
    ctx = build_report_context(
        mode="portfolio",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        status_md_text="### ⚠️ Conflitos sinalizados\n1. Motor A vs Motor B.\n\n---\n",
    )
    html = render_report(ctx)
    assert "1 conflito entre motores" in html
    assert 'class="alert"' in html


def test_no_conflict_alerts_when_status_md_not_supplied() -> None:
    html = render_report(_full_context())
    assert 'class="alert"' not in html


def _df_with_features() -> pd.DataFrame:
    df = _df()
    df["gross_margin"] = [60, 20]
    df["roic"] = [0.25, 0.05]
    df["pe"] = [15, 40]
    df["debt_to_equity"] = [0.3, 2.0]
    df["rsi_14"] = [80, 50]
    return df


def _full_context_with_ticker_details():
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA", action="HOLD", current_weight=0.1, target_weight=0.1,
                target_value=100, trade_value=0, reason="ok",
                rule_results=({"name": "distress", "status": "clear", "message": "sem risco de distress."},),
            ),
            RebalanceAction(
                symbol="BBB", action="SELL", current_weight=0.1, target_weight=0.0,
                target_value=0, trade_value=-100, reason="distress disparou",
                triggered_rules=("distress",),
                rule_results=({"name": "distress", "status": "triggered", "message": "Altman Z abaixo do piso."},),
            ),
        ),
    )
    return build_report_context(
        mode="full",
        df=_df_with_features(),
        snapshot_date="2026-07-14T00:00:00",
        rebalance=plan.to_dict(),
        holdings=(
            {
                "symbol": "AAA",
                "thesis": "Tese de longo prazo em software.",
                "average_price": 100.0,
                "current_price": 120.0,
                "unrealized_return": 20.0,
            },
        ),
        score_history=pd.DataFrame(
            {
                "snapshot_date": ["2026-06-01"],
                "symbol": ["AAA"],
                "investment_score": [70.0],
            }
        ),
        features_path=Path("config/features.yaml"),
        model_path=Path("config/model.yaml"),
    )


def test_ticker_detail_section_rendered_and_anchored() -> None:
    context = _full_context_with_ticker_details()
    html = render_report(context)
    assert ">Detalhe por ativo<" in html
    assert 'id="ticker-AAA"' in html
    assert 'id="ticker-BBB"' in html
    # AAA é HOLD sem mudança de estado -- colapsada no resumo da tabela de
    # carteira (comportamento existente), então só BBB (SELL) aparece linkada
    # na tabela; o anchor id de AAA continua existindo na seção de detalhe
    # (verificado acima), só não referenciado por essa tabela.
    #
    # O símbolo passou a apontar para a página completa da empresa
    # (`/company/SYM`, servida por api.server). A âncora interna sobrevive em
    # `data-anchor`: é para ela que o script cai quando o relatório é aberto
    # via file://, onde não existe servidor.
    assert 'href="/company/BBB"' in html
    assert 'data-anchor="ticker-BBB"' in html
    assert "Tese de longo prazo em software." in html


def test_symbol_links_fall_back_to_the_internal_anchor_offline() -> None:
    """Aberto via file:// o relatório precisa continuar navegável sozinho."""
    html = render_report(_full_context_with_ticker_details())
    assert 'location.protocol !== "file:"' in html
    assert 'a.setAttribute("href", "#" + anchor)' in html
    # O link "ver página completa" não vira auto-link offline: some.
    assert 'a.style.display = "none"' in html


def test_ticker_detail_no_external_resources_even_with_real_content() -> None:
    """
    Reforça test_no_external_resources_in_generated_html com um contexto
    que de fato popula ticker_details (features_path informado) -- sem
    isso o teste original nunca exercita esta seção.
    """
    html = render_report(_full_context_with_ticker_details())
    matches = _EXTERNAL_RESOURCE_PATTERN.findall(html)
    assert matches == []


def test_ticker_detail_omitted_when_features_path_not_given() -> None:
    html = render_report(_full_context())
    assert "Detalhe por ativo não incluído neste run." in html


def _write_broad_report(path: Path, *, generated_at: str) -> None:
    import json

    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "summary": {
                    "total_count": 7093,
                    "universe_eligible_count": 2429,
                    "candidate_count": 999,
                    "blocked_by_reason": {"DEAL_BREAKER_TRIGGERED": 4002},
                },
                "companies": [
                    {
                        "symbol": "SSRM",
                        "sector": "Basic Materials",
                        "safeguard_passed": True,
                        "candidate_rank": 1,
                        "investment_score": 72.1,
                        "confidence_score": 100.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_broad_screeners_omitted_when_no_path_given() -> None:
    html = render_report(_full_context())
    assert "Screeners amplos não incluído neste run." in html


def test_broad_screener_renders_top_candidates_and_no_stale_alert(tmp_path: Path) -> None:
    report_path = tmp_path / "research_ranking_report_market.json"
    _write_broad_report(report_path, generated_at="2026-07-01T00:00:00")
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        broad_market_report_path=report_path,
    )
    html = render_report(ctx)
    assert ">Mercado Amplo<" in html
    assert "SSRM" in html
    assert 'class="alert"' not in html


def test_watchlist_proposals_rendered_with_derived_trigger(tmp_path: Path) -> None:
    """
    Fonte é o screener AMPLO (research_ranking_report_market.json), não o
    ranking_report estreito do --full: comparar candidatos contra a própria
    watchlist da qual eles vieram é tautológico e nunca produz sugestão
    (achado rodando de verdade contra o screener real -- 39/39 candidatos
    não-held do ranking_report estreito já estavam na watchlist.csv).
    """
    import json

    report_path = tmp_path / "research_ranking_report_market.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-14T00:00:00",
                "summary": {
                    "total_count": 1,
                    "universe_eligible_count": 1,
                    "candidate_count": 1,
                    "blocked_by_reason": {},
                },
                "companies": [
                    {
                        "symbol": "ZZZ",
                        "name": "Zeta Corp",
                        "sector": "Energy",
                        "safeguard_passed": True,
                        "candidate_rank": 1,
                        "investment_score": 72.0,
                        "confidence_score": 95.0,
                        "already_held": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        broad_market_report_path=report_path,
    )
    html = render_report(ctx)
    assert ">Sugestões para a watchlist<" in html
    assert "ZZZ" in html
    assert "Zeta Corp" in html
    # score 72 (zona Acumular), sem info de valuation -> próxima faixa
    assert "score &gt; 80" in html or "score > 80" in html


def test_watchlist_proposals_omitted_without_broad_screener() -> None:
    ctx = build_report_context(
        mode="portfolio", df=_df(), snapshot_date="2026-07-14T00:00:00"
    )
    html = render_report(ctx)
    assert "Sugestões para a watchlist não incluído neste run." in html


def test_watchlist_proposals_exclude_held_and_watched(tmp_path: Path) -> None:
    """
    held_symbols vem de df["origin"]=="portfolio" (confiável mesmo com o
    motor de venda bloqueado / portfolio_report ausente), não do campo
    already_held do JSON amplo (sempre False lá).
    """
    import json

    report_path = tmp_path / "research_ranking_report_market.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-14T00:00:00",
                "summary": {},
                "companies": [
                    {
                        "symbol": "HELD", "sector": "Tech", "safeguard_passed": True,
                        "candidate_rank": 1, "investment_score": 80.0,
                        "confidence_score": 100.0, "already_held": False,
                    },
                    {
                        "symbol": "AAA", "sector": "Tech", "safeguard_passed": True,
                        "candidate_rank": 2, "investment_score": 78.0,
                        "confidence_score": 100.0, "already_held": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    df = _df()
    df["symbol"] = ["HELD", "BBB"]
    df["origin"] = ["portfolio", "watchlist"]
    ctx = build_report_context(
        mode="full",
        df=df,
        snapshot_date="2026-07-14T00:00:00",
        broad_market_report_path=report_path,
    )
    html = render_report(ctx)
    # HELD legitimamente aparece na tabela crua "Screeners amplos" (ranking
    # sem filtro pessoal) -- restringe a checagem à seção de sugestões.
    section_start = html.index(">Sugestões para a watchlist<")
    section_end = html.index("<h2>Earnings</h2>")
    section = html[section_start:section_end]
    assert ">HELD<" not in section
    assert "AAA" in section


def test_broad_screener_flags_stale_collection(tmp_path: Path) -> None:
    report_path = tmp_path / "research_ranking_report_adr.json"
    _write_broad_report(report_path, generated_at="2026-01-01T00:00:00")
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        adr_report_path=report_path,
    )
    html = render_report(ctx)
    assert ">ADR<" in html
    assert 'class="alert"' in html
    assert "considere rodar a coleta novamente" in html

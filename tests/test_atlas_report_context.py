from __future__ import annotations

import pandas as pd
import pytest

from portfolio.models import RebalanceAction, RebalancePlan
from ranking.models import RankedCompany, RankingPolicy, RankingReport
from reports.atlas_report.context import build_report_context
from watchlist.models import WatchlistReport, WatchlistTriggerResult


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "Investment Score": 80.0,
                "Confidence Score": 90.0,
                "earnings_date": "2026-07-10",
                "f_score_annual": 6,
                "roic": 0.20,
            },
            {
                "symbol": "BBB",
                "name": "Beta",
                "sector": "Health",
                "Investment Score": 50.0,
                "Confidence Score": 60.0,
                "earnings_date": None,
                "f_score_annual": 4,
                "roic": 0.05,
            },
        ]
    )


def test_mode_validation_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        build_report_context(mode="bogus", df=_df(), snapshot_date="2026-07-14T00:00:00")


def test_portfolio_and_screener_not_included_by_default() -> None:
    ctx = build_report_context(mode="portfolio", df=_df(), snapshot_date="2026-07-14T00:00:00")
    assert ctx.portfolio_included is False
    assert ctx.screener.included is False
    assert ctx.watchlist_included is False


def test_portfolio_blocked_reason_surfaces_as_required_action() -> None:
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        portfolio_blocked_reason="posições sem tese",
    )
    assert ctx.portfolio_included is False
    assert ctx.portfolio_blocked_reason == "posições sem tese"
    assert any(
        action.kind == "portfolio_blocked" for action in ctx.required_actions
    )


def test_rebalance_actions_populate_portfolio_rows_and_required_actions() -> None:
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA",
                action="HOLD",
                current_weight=0.1,
                target_weight=0.1,
                target_value=100,
                trade_value=0,
                reason="ok",
            ),
            RebalanceAction(
                symbol="BBB",
                action="SELL",
                current_weight=0.1,
                target_weight=0.0,
                target_value=0,
                trade_value=-100,
                reason="distress disparou",
                triggered_rules=("distress",),
            ),
        ),
        warnings=("aviso de teste",),
    )
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        rebalance=plan.to_dict(),
        portfolio_warnings=plan.warnings,
    )
    assert ctx.portfolio_included is True
    assert len(ctx.portfolio_rows) == 2
    bbb = next(row for row in ctx.portfolio_rows if row.symbol == "BBB")
    assert bbb.action == "SELL"
    assert bbb.has_state_change is True
    aaa = next(row for row in ctx.portfolio_rows if row.symbol == "AAA")
    assert aaa.has_state_change is False
    assert any(action.symbol == "BBB" for action in ctx.required_actions)
    assert ctx.portfolio_warnings == ("aviso de teste",)


def test_score_delta_only_when_baseline_comparable() -> None:
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA", action="HOLD", current_weight=0.1, target_weight=0.1,
                target_value=100, trade_value=0, reason="ok",
            ),
        ),
    )
    comparable = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        rebalance=plan.to_dict(),
        previous_by_symbol={"AAA": {"investment_score": 70.0}},
        baseline_status="comparable",
    )
    assert comparable.portfolio_rows[0].score_delta == 10.0

    not_comparable = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        rebalance=plan.to_dict(),
        previous_by_symbol={"AAA": {"investment_score": 70.0}},
        baseline_status="model_version_changed",
    )
    assert not_comparable.portfolio_rows[0].score_delta is None


def test_watchlist_triggers_populate_rows_and_required_actions() -> None:
    wl = WatchlistReport(
        results=(
            WatchlistTriggerResult(
                symbol="AAA",
                trigger_condition="score > 75",
                status="triggered",
                message="score > 75: passou a valer.",
            ),
            WatchlistTriggerResult(
                symbol="BBB",
                trigger_condition="",
                status="no_condition",
                message="passivo",
                age_days=200,
                cleanup_suggested=True,
            ),
        )
    )
    ctx = build_report_context(
        mode="full", df=_df(), snapshot_date="2026-07-14T00:00:00", watchlist_report=wl
    )
    assert ctx.watchlist_included is True
    assert len(ctx.watchlist_rows) == 2
    assert any(action.symbol == "AAA" for action in ctx.required_actions)
    bbb_row = next(row for row in ctx.watchlist_rows if row.symbol == "BBB")
    assert bbb_row.cleanup_suggested is True


def test_earnings_rows_union_portfolio_and_watchlist() -> None:
    plan = RebalancePlan(
        actions=(
            RebalanceAction(
                symbol="AAA", action="HOLD", current_weight=0.1, target_weight=0.1,
                target_value=100, trade_value=0, reason="ok",
            ),
        ),
    )
    wl = WatchlistReport(
        results=(
            WatchlistTriggerResult(
                symbol="BBB", trigger_condition="", status="no_condition", message="x"
            ),
        )
    )
    ctx = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        rebalance=plan.to_dict(),
        watchlist_report=wl,
        previous_run_at=pd.Timestamp("2026-07-01"),
        previous_by_symbol={"AAA": {"f_score_annual": 9, "roic": 0.30}},
        baseline_status="comparable",
    )
    # AAA teve earnings_date dentro da janela (2026-07-10, entre 07-01 e 07-14).
    assert any(row.symbol == "AAA" for row in ctx.earnings_rows)
    aaa_earnings = next(row for row in ctx.earnings_rows if row.symbol == "AAA")
    assert aaa_earnings.origin == "portfolio"
    assert aaa_earnings.changed_fundamentals  # F-Score/ROIC mudaram
    # BBB não tem earnings_date -- não entra.
    assert not any(row.symbol == "BBB" for row in ctx.earnings_rows)


def test_screener_new_candidates_only_when_comparable() -> None:
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
    comparable = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        ranking_report=ranking,
        previous_by_symbol={},
        baseline_status="comparable",
    )
    assert comparable.screener.included is True
    assert comparable.screener.new_candidates == ("AAA",)

    not_comparable = build_report_context(
        mode="full",
        df=_df(),
        snapshot_date="2026-07-14T00:00:00",
        ranking_report=ranking,
        baseline_status="first_run",
    )
    assert not_comparable.screener.new_candidates == ()

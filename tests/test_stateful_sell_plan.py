from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portfolio.models import Holding, Portfolio
from portfolio.rebalance import SellEngineBlockedError, build_stateful_sell_plan
from portfolio.sell_rules import load_sell_rules_policy
from universe import evaluate_universe, load_universe_policy
from ranking import RankingPolicy, rank_companies


@pytest.fixture(scope="module")
def policy():
    return load_sell_rules_policy(Path("config/sell_rules.yaml"))


def _holding(
    symbol: str,
    *,
    thesis: str = "Tese de teste.",
    origin: str = "portfolio",
    quantity: float = 10.0,
) -> Holding:
    return Holding(
        symbol=symbol,
        quantity=quantity,
        average_price=100.0,
        current_price=100.0,
        sector="Consumer Cyclical",
        industry="Retail - Apparel",
        thesis=thesis,
        origin=origin,
    )


def _row(symbol: str, **overrides) -> dict:
    base = {
        "symbol": symbol,
        "sector": "Consumer Cyclical",
        "industry": "Retail - Apparel",
        "Confidence Score": 90.0,
        "Score Coverage": 90.0,
        "Deal Breakers": "Nenhum",
    }
    base.update(overrides)
    return base


def _analysis_df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_missing_thesis_blocks_the_sell_engine_entirely(policy) -> None:
    portfolio = Portfolio(
        name="Blocked",
        holdings=(_holding("AAA", thesis=""), _holding("BBB", thesis="OK")),
    )
    df = _analysis_df(_row("AAA"), _row("BBB"))

    with pytest.raises(SellEngineBlockedError) as exc_info:
        build_stateful_sell_plan(portfolio, df, sell_rules_policy=policy)

    assert exc_info.value.missing_thesis_symbols == ("AAA",)


def test_missing_thesis_does_not_block_screener_or_watchlist(policy) -> None:
    """
    O bloqueio é só do motor de venda -- ranking/universe (que alimentam
    screener/watchlist) continuam funcionando normalmente sobre o mesmo
    DataFrame analisado, mesmo com a carteira bloqueada.
    """
    portfolio = Portfolio(
        name="Blocked",
        holdings=(_holding("AAA", thesis=""),),
    )
    df = _analysis_df(
        {
            "symbol": "AAA",
            "sector": "Consumer Cyclical",
            "quote_type": "EQUITY",
            "currency": "USD",
            "country": "United States",
            "price": 100.0,
            "market_cap": 1_000_000_000.0,
            "volume": 1_000_000.0,
            "Investment Score": 80.0,
            "Opportunity Score": 80.0,
            "Conviction Score": 80.0,
            "Confidence Score": 90.0,
            "Deal Breakers": "Nenhum",
        }
    )

    with pytest.raises(SellEngineBlockedError):
        build_stateful_sell_plan(portfolio, df, sell_rules_policy=policy)

    universe_report = evaluate_universe(df, load_universe_policy("config/universe.yaml"))
    ranking_report = rank_companies(df, universe_report, RankingPolicy("Test"))
    assert ranking_report.total_count == 1


def test_quantity_increase_warns_without_blocking(policy) -> None:
    portfolio = Portfolio(
        name="Increase",
        holdings=(_holding("AAA", quantity=20.0),),
    )
    df = _analysis_df(_row("AAA"))
    previous_by_symbol = {"AAA": {"quantity": 10.0}}

    plan = build_stateful_sell_plan(
        portfolio,
        df,
        sell_rules_policy=policy,
        previous_by_symbol=previous_by_symbol,
        baseline_status="comparable",
    )

    assert any("aumentou" in warning for warning in plan.warnings)


def test_quantity_decrease_does_not_warn(policy) -> None:
    portfolio = Portfolio(
        name="Decrease",
        holdings=(_holding("AAA", quantity=5.0),),
    )
    df = _analysis_df(_row("AAA"))
    previous_by_symbol = {"AAA": {"quantity": 10.0}}

    plan = build_stateful_sell_plan(
        portfolio,
        df,
        sell_rules_policy=policy,
        previous_by_symbol=previous_by_symbol,
        baseline_status="comparable",
    )

    assert not any("aumentou" in warning for warning in plan.warnings)


def test_first_run_without_previous_quantity_does_not_warn(policy) -> None:
    portfolio = Portfolio(name="First", holdings=(_holding("AAA"),))
    df = _analysis_df(_row("AAA"))

    plan = build_stateful_sell_plan(portfolio, df, sell_rules_policy=policy)

    assert not any("aumentou" in warning for warning in plan.warnings)


def test_model_version_changed_baseline_prevents_any_numeric_delta(policy) -> None:
    portfolio = Portfolio(name="VersionChange", holdings=(_holding("AAA"),))
    df = _analysis_df(_row("AAA", f_score_annual=2, roic=0.05))
    previous_by_symbol = {"AAA": {"f_score_annual": 9, "roic": 0.30}}

    plan = build_stateful_sell_plan(
        portfolio,
        df,
        sell_rules_policy=policy,
        previous_by_symbol=previous_by_symbol,
        baseline_status="model_version_changed",
    )

    action = plan.actions[0]
    assert action.baseline_status == "model_version_changed"
    fundamental_decay = next(
        item for item in action.rule_results if item["name"] == "fundamental_decay"
    )
    assert fundamental_decay["status"] == "not_evaluated"
    assert "fundamental_decay" not in action.triggered_rules


def test_sell_signal_only_for_portfolio_origin(policy) -> None:
    portfolio = Portfolio(
        name="OriginCheck",
        holdings=(
            _holding("AAA", origin="portfolio"),
            _holding("BBB", origin="watchlist"),
        ),
    )
    df = _analysis_df(_row("AAA"), _row("BBB"))

    plan = build_stateful_sell_plan(portfolio, df, sell_rules_policy=policy)

    action_symbols = {action.symbol for action in plan.actions}
    assert action_symbols == {"AAA"}
    assert any("BBB" in warning for warning in plan.warnings)


def test_earnings_since_last_run_is_a_transition(policy) -> None:
    portfolio = Portfolio(name="Earnings", holdings=(_holding("AAA"),))
    df = _analysis_df(_row("AAA", earnings_date="2026-07-10"))

    inside_window = build_stateful_sell_plan(
        portfolio,
        df,
        sell_rules_policy=policy,
        previous_run_at=pd.Timestamp("2026-07-01"),
        current_run_at=pd.Timestamp("2026-07-13"),
    )
    assert inside_window.actions[0].earnings_since_last_run is True
    assert "divulgação de resultado" in inside_window.actions[0].reason

    outside_window = build_stateful_sell_plan(
        portfolio,
        df,
        sell_rules_policy=policy,
        previous_run_at=pd.Timestamp("2026-07-11"),
        current_run_at=pd.Timestamp("2026-07-13"),
    )
    assert outside_window.actions[0].earnings_since_last_run is False


def test_legacy_flagged_diverges_without_changing_action(policy) -> None:
    """
    O deal-breaker antigo (coluna "Deal Breakers", já computado por
    apply_deal_breakers) é só anotado quando diverge -- nunca sobrepõe a
    decisão do motor novo.
    """
    portfolio = Portfolio(name="Legacy", holdings=(_holding("AAA"),))
    # Motor novo não dispara nada (tudo limpo); legado sinaliza um problema
    # que o catálogo novo não cobre (ex.: critério fora do catálogo).
    df = _analysis_df(_row("AAA", **{"Deal Breakers": "Short float alto"}))

    plan = build_stateful_sell_plan(portfolio, df, sell_rules_policy=policy)

    action = plan.actions[0]
    assert action.action == "HOLD"
    assert action.legacy_flagged is True
    assert any("diverge" in warning for warning in plan.warnings)

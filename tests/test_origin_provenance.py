"""
Contract tests for universe provenance: every row in the analyzed
DataFrame carries an `origin` tag (run_all.merge_watchlist_with_portfolio,
hierarchy portfolio > watchlist > universe) so decision engines know why a
row is being analyzed.

Two invariants must hold end to end, through the real production code
paths (portfolio.pipeline + portfolio.rebalance for the first, ranking for
the second) -- not just at the merge function itself:

(a) the sell-only rebalance engine never emits an action for a symbol whose
    origin is not "portfolio";
(b) any ranking/buy-screener output explicitly flags a row whose origin is
    "portfolio" (already_held=True) -- it is never presented as a fresh
    candidate without that flag.
"""
from __future__ import annotations

import pandas as pd
import pytest

from portfolio.models import Holding, Portfolio
from portfolio.pipeline import enrich_portfolio_from_analysis
from portfolio.rebalance import RebalancePolicy, build_sell_only_plan
from priority.pipeline import build_buy_priority
from ranking import RankingPolicy, rank_companies
from universe import UniversePolicy, evaluate_universe


def _analyzed_frame() -> pd.DataFrame:
    """
    Mirrors what run_all.collect_market_data + build_scores produce: real
    holdings (origin="portfolio") mixed with research-only symbols
    (origin="watchlist") in the same scored batch. CCC is a watchlist-only
    symbol that scores AVOID -- exactly the case that must never leak into
    a sell signal, since Atlas does not hold it.
    """
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "sector": "Technology",
                "origin": "portfolio",
                "Decision": "AVOID",
                "Investment Score": 30,
                "Opportunity Score": 30,
                "Conviction Score": 30,
                "Confidence Score": 100,
                "Deal Breakers": "Altman Z baixo",
            },
            {
                "symbol": "BBB",
                "sector": "Technology",
                "origin": "portfolio",
                "Decision": "HOLD",
                "Investment Score": 60,
                "Opportunity Score": 60,
                "Conviction Score": 60,
                "Confidence Score": 100,
                "Deal Breakers": "Nenhum",
            },
            {
                "symbol": "CCC",
                "sector": "Health",
                "origin": "watchlist",
                "Decision": "AVOID",
                "Investment Score": 20,
                "Opportunity Score": 20,
                "Conviction Score": 20,
                "Confidence Score": 100,
                "Deal Breakers": "Piotroski baixo",
            },
            {
                "symbol": "DDD",
                "sector": "Industrials",
                "origin": "watchlist",
                "Decision": "BUY",
                "Investment Score": 90,
                "Opportunity Score": 90,
                "Conviction Score": 90,
                "Confidence Score": 100,
                "Deal Breakers": "Nenhum",
            },
        ]
    )


def _universe(frame: pd.DataFrame):
    metadata = frame[["symbol", "sector"]].copy()
    metadata["quote_type"] = "EQUITY"
    metadata["currency"] = "USD"
    metadata["country"] = "United States"
    metadata["price"] = 100.0
    metadata["market_cap"] = 10_000_000_000.0
    metadata["volume"] = 1_000_000.0
    return evaluate_universe(metadata, UniversePolicy("US", "S&P 500", "monthly"))


def test_sell_only_never_emits_a_signal_outside_portfolio_origin() -> None:
    """
    (a) End to end through the real path: enrich_portfolio_from_analysis
    (which ties a Holding to a CompanyReport by symbol) + build_sell_only_plan.
    Portfolio.holdings mirrors what config/portfolio.csv would contain --
    only AAA and BBB, the two rows tagged origin="portfolio". CCC scores
    AVOID too, but it is not a real holding and must never appear.
    """
    frame = _analyzed_frame()
    portfolio_origin_symbols = set(
        frame.loc[frame["origin"] == "portfolio", "symbol"]
    )
    assert portfolio_origin_symbols == {"AAA", "BBB"}

    portfolio = Portfolio(
        name="Real",
        cash=0,
        holdings=(
            Holding(symbol="AAA", quantity=10, average_price=100, current_price=100),
            Holding(symbol="BBB", quantity=10, average_price=100, current_price=100),
        ),
    )
    enriched = enrich_portfolio_from_analysis(portfolio, frame)
    plan = build_sell_only_plan(
        enriched,
        policy=RebalancePolicy(
            tolerance=0.01,
            minimum_trade_value=0,
            allow_sells=True,
            maximum_position_weight=1.0,
            minimum_cash_weight=0.0,
        ),
    )

    action_symbols = {action.symbol for action in plan.actions}
    assert action_symbols == portfolio_origin_symbols
    assert "CCC" not in action_symbols

    sell_actions = {a.symbol for a in plan.actions if a.action == "SELL"}
    assert sell_actions == {"AAA"}  # only the AVOID real holding


def test_sell_only_cannot_be_constructed_from_non_portfolio_origin_rows() -> None:
    """
    Defensive proof of (a) from the other direction: if a Portfolio were
    ever built from a watchlist-only symbol (a bug -- Portfolio.holdings
    must only ever come from config/portfolio.csv), the resulting sell-only
    action would carry a symbol whose origin in the analyzed frame is NOT
    "portfolio". This test pins the invariant so such a regression fails
    loudly instead of silently selling a symbol Atlas never held.
    """
    frame = _analyzed_frame()
    origin_by_symbol = dict(zip(frame["symbol"], frame["origin"]))

    buggy_portfolio = Portfolio(
        name="Buggy",
        cash=0,
        holdings=(
            Holding(symbol="CCC", quantity=10, average_price=100, current_price=100),
        ),
    )
    enriched = enrich_portfolio_from_analysis(buggy_portfolio, frame)
    plan = build_sell_only_plan(enriched)

    # This assertion is the actual contract: it must fail if a non-portfolio
    # origin symbol ever appears in a sell-only action.
    for action in plan.actions:
        assert origin_by_symbol.get(action.symbol) == "portfolio", (
            f"sell-only emitted a signal for {action.symbol!r}, whose "
            f"origin is {origin_by_symbol.get(action.symbol)!r}, not "
            "'portfolio'"
        )


def test_ranking_report_flags_portfolio_origin_as_already_held() -> None:
    """
    (b), first output: the raw ranking report (dashboard/Excel/research
    consumers) marks every portfolio-origin row already_held=True, even
    when it also passes every safeguard and would otherwise look like a
    fresh, ordinary candidate.
    """
    frame = _analyzed_frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    by_symbol = {company.symbol: company for company in report.companies}

    assert by_symbol["AAA"].already_held is True
    assert by_symbol["BBB"].already_held is True
    assert by_symbol["CCC"].already_held is False
    assert by_symbol["DDD"].already_held is False

    # DDD is a genuine new candidate (safeguard passed, not held) -- the
    # positive control proving already_held is not just always True/False.
    assert by_symbol["DDD"].safeguard_passed is True
    assert by_symbol["DDD"].candidate_rank is not None


def test_buy_priority_never_presents_a_held_symbol_without_the_flag() -> None:
    """
    (b), second output: priority.build_buy_priority (the buy screener) must
    mark already_held=True for any candidate that is also a real holding --
    it is a screener bug if a symbol Atlas already owns is ever handed back
    as an unflagged BuyPriorityItem.
    """
    frame = _analyzed_frame()
    report = rank_companies(frame, _universe(frame), RankingPolicy("Test"))
    ranked_companies = [company.to_dict() for company in report.companies]
    held_symbols = frozenset(
        frame.loc[frame["origin"] == "portfolio", "symbol"]
    )

    buy = build_buy_priority(ranked_companies, held_symbols=held_symbols)

    for item in buy.items:
        is_portfolio_origin = item.symbol in held_symbols
        assert item.already_held == is_portfolio_origin, (
            f"{item.symbol} already_held={item.already_held} does not "
            f"match its portfolio-origin membership ({is_portfolio_origin})"
        )

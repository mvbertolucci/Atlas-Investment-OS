from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backtesting.historical_portfolio import (
    HistoricalPortfolioConstructionError,
    _factor_exposures_by_symbol,
    build_historical_target_portfolio,
    build_historical_target_portfolios,
)
from backtesting.point_in_time import (
    HistoricalObservation,
    PointInTimeDataset,
    UniverseMembership,
)


MODEL_PATH = Path("config/model.yaml")
DEAL_BREAKERS_PATH = Path("config/deal_breakers.json")


def _observation(
    symbol: str,
    field_name: str,
    value,
    observed_on: str = "2025-01-01",
    available_at: str = "2025-01-02T00:00:00Z",
    revision: str = "initial",
) -> HistoricalObservation:
    return HistoricalObservation(
        symbol=symbol,
        field_name=field_name,
        value=value,
        observed_on=observed_on,
        available_at=available_at,
        source="synthetic-point-in-time-fixture",
        revision_id=revision,
    )


def _membership(symbol: str) -> UniverseMembership:
    return UniverseMembership(
        symbol=symbol,
        effective_from="2020-01-01",
        known_at="2020-01-01T00:00:00Z",
        source="synthetic-membership",
    )


def _company_observations(
    symbol: str,
    sector: str,
    roic: float,
) -> tuple[HistoricalObservation, ...]:
    values = {
        "quote_type": "EQUITY",
        "currency": "USD",
        "country": "United States",
        "sector": sector,
        "industry": "Synthetic",
        "price": 100.0,
        "market_cap": 10_000_000_000.0,
        "volume": 1_000_000.0,
        "roic": roic,
    }
    return tuple(
        _observation(symbol, field_name, value)
        for field_name, value in values.items()
    )


def _dataset(*, include_empty_member: bool = True) -> PointInTimeDataset:
    observations = (
        *_company_observations("AAA", "Technology", 0.10),
        *_company_observations("BBB", "Health", 0.30),
        *_company_observations("CCC", "Industrials", 0.20),
        _observation(
            "AAA",
            "roic",
            0.90,
            observed_on="2025-03-01",
            available_at="2025-03-02T00:00:00Z",
            revision="future-improvement",
        ),
    )
    members = [
        _membership("AAA"),
        _membership("BBB"),
        _membership("CCC"),
    ]
    if include_empty_member:
        members.append(_membership("DDD"))
    return PointInTimeDataset(
        observations=observations,
        memberships=tuple(members),
    )


def _write_policies(tmp_path: Path, *, target_positions: int) -> dict[str, Path]:
    universe = tmp_path / "universe.yaml"
    ranking = tmp_path / "ranking.yaml"
    portfolio = tmp_path / "portfolio.yaml"
    universe.write_text(
        """name: Historical Test Universe
benchmark: SPY
rebalance_frequency: monthly
allowed_quote_types: [EQUITY]
allowed_currencies: [USD]
allowed_countries: [United States]
min_market_cap: 1
min_price: 1
min_volume: 1
required_fields: [symbol, quote_type, currency, country, sector, price, market_cap, volume]
""",
        encoding="utf-8",
    )
    ranking.write_text(
        """name: Historical Test Ranking
primary_score: Investment Score
tie_breakers: [Opportunity Score, Conviction Score]
min_confidence_score: 0
require_no_deal_breakers: false
""",
        encoding="utf-8",
    )
    equal_weight = 1 / target_positions
    portfolio.write_text(
        f"""name: Historical Test Portfolio
target_positions: {target_positions}
weighting_method: equal
max_position_weight: {equal_weight}
max_sector_weight: 1.0
cash_weight: 0.0
max_initial_turnover: 1.0
""",
        encoding="utf-8",
    )
    return {
        "universe_policy_path": universe,
        "ranking_policy_path": ranking,
        "model_portfolio_policy_path": portfolio,
    }


def _build(snapshot, paths):
    return build_historical_target_portfolio(
        snapshot,
        model_path=MODEL_PATH,
        deal_breakers_path=DEAL_BREAKERS_PATH,
        **paths,
    )


def test_historical_target_uses_governed_pipeline_and_keeps_gaps_visible(
    tmp_path: Path,
) -> None:
    target = _build(
        _dataset().as_of("2025-02-01T00:00:00Z"),
        _write_policies(tmp_path, target_positions=2),
    )

    assert target.constructed is True
    assert len(target.target_weights) == 2
    assert sum(target.target_weights.values()) == 1.0
    assert set(target.target_weights) == set(target.sectors)
    assert target.universe_member_count == 4
    assert target.universe_eligible_count == 3
    assert target.candidate_count == 3
    assert target.incomplete_decisions[0].symbol == "DDD"
    assert target.incomplete_decisions[0].reasons == ("NO_DATA_AVAILABLE",)
    assert target.to_dict()["coverage"]["incomplete_decision_count"] == 1
    assert set(target.governed_config_hashes) == {
        "model",
        "deal_breakers",
        "universe_policy",
        "ranking_policy",
        "model_portfolio_policy",
    }
    assert all(len(value) == 64 for value in target.governed_config_hashes.values())
    assert set(target.factor_exposures) == set(target.target_weights)
    assert set(next(iter(target.factor_exposures.values()))) == {
        "business",
        "valuation",
        "financial",
        "timing",
    }


def test_execution_date_is_explicit_and_cannot_precede_decision(
    tmp_path: Path,
) -> None:
    target = _build(
        _dataset(include_empty_member=False).as_of("2025-02-01T00:00:00Z"),
        _write_policies(tmp_path, target_positions=2),
    )

    with pytest.raises(ValueError, match="não pode anteceder"):
        target.to_rebalance("2025-01-31")
    rebalance = target.to_rebalance("2025-02-03")
    assert rebalance.effective_on.isoformat() == "2025-02-03"
    assert rebalance.target_weights == target.target_weights
    assert rebalance.sectors == target.sectors
    assert rebalance.factor_exposures == target.factor_exposures


def test_future_fundamental_cannot_change_earlier_target(
    tmp_path: Path,
) -> None:
    paths = _write_policies(tmp_path, target_positions=1)
    dataset = _dataset(include_empty_member=False)

    before = _build(dataset.as_of("2025-02-01T00:00:00Z"), paths)
    after = _build(dataset.as_of("2025-04-01T00:00:00Z"), paths)

    assert tuple(before.target_weights) == ("BBB",)
    assert tuple(after.target_weights) == ("AAA",)


def test_historical_target_sequence_is_sorted_deduplicated_and_point_in_time(
    tmp_path: Path,
) -> None:
    paths = _write_policies(tmp_path, target_positions=1)
    targets = build_historical_target_portfolios(
        _dataset(include_empty_member=False),
        (
            "2025-04-01T00:00:00Z",
            "2025-02-01T00:00:00Z",
            "2025-02-01T00:00:00Z",
        ),
        model_path=MODEL_PATH,
        deal_breakers_path=DEAL_BREAKERS_PATH,
        **paths,
    )

    assert [item.decision_at.date().isoformat() for item in targets] == [
        "2025-02-01",
        "2025-04-01",
    ]
    assert [tuple(item.target_weights) for item in targets] == [
        ("BBB",),
        ("AAA",),
    ]


def test_insufficient_candidates_returns_no_partial_portfolio(
    tmp_path: Path,
) -> None:
    target = _build(
        _dataset(include_empty_member=False).as_of("2025-02-01T00:00:00Z"),
        _write_policies(tmp_path, target_positions=4),
    )

    assert target.constructed is False
    assert target.target_weights == {}
    assert "Candidatos insuficientes" in str(target.construction_error)
    with pytest.raises(HistoricalPortfolioConstructionError):
        target.to_rebalance("2025-02-03")


def test_factor_exposures_by_symbol_skips_missing_columns_and_non_numeric_values() -> None:
    scored = pd.DataFrame(
        [
            {
                "symbol": "aaa",
                "Business Factor": 60.0,
                "Valuation Factor": float("nan"),
                "Financial Factor": "not-a-number",
            },
            {"symbol": "BBB", "Business Factor": 40.0},
        ]
    )
    exposures = _factor_exposures_by_symbol(scored)
    assert exposures == {"AAA": {"business": 60.0}, "BBB": {"business": 40.0}}


def test_factor_exposures_by_symbol_returns_empty_without_any_factor_columns() -> None:
    assert _factor_exposures_by_symbol(pd.DataFrame([{"symbol": "AAA"}])) == {}


def test_no_scorable_members_is_an_explicit_construction_failure(
    tmp_path: Path,
) -> None:
    dataset = PointInTimeDataset(memberships=(_membership("EMPTY"),))
    target = _build(
        dataset.as_of("2025-02-01T00:00:00Z"),
        _write_policies(tmp_path, target_positions=1),
    )

    assert target.constructed is False
    assert target.construction_error == "NO_SCORABLE_MEMBERS"
    assert target.incomplete_decisions[0].reasons == ("NO_DATA_AVAILABLE",)

from __future__ import annotations

import pytest

from providers.market_cap_composition import compose_market_cap


def test_composes_market_cap_when_price_and_shares_align() -> None:
    record = compose_market_cap(
        "aapl",
        grouped_daily_row={"close": 200.0, "trade_date": "2026-07-16"},
        shares_outstanding=15_000_000_000.0,
        shares_observed_at="2026-04-17",
        shares_alignment_days=100,
    )

    assert record["symbol"] == "AAPL"
    assert record["status"] == "composed"
    assert record["market_cap"] == pytest.approx(3_000_000_000_000.0)
    assert record["field_evidence"]["market_cap"]["status"] == "present"


def test_price_unavailable_never_invents_market_cap() -> None:
    record = compose_market_cap(
        "AAPL",
        grouped_daily_row=None,
        shares_outstanding=15_000_000_000.0,
        shares_observed_at="2026-04-17",
        shares_alignment_days=100,
    )

    assert record["status"] == "price_unavailable"
    assert record["market_cap"] is None
    assert record["field_evidence"]["market_cap"]["status"] == "unavailable"


def test_shares_unavailable_never_invents_market_cap() -> None:
    record = compose_market_cap(
        "AAPL",
        grouped_daily_row={"close": 200.0, "trade_date": "2026-07-16"},
        shares_outstanding=None,
        shares_observed_at=None,
        shares_alignment_days=100,
    )

    assert record["status"] == "shares_unavailable"
    assert record["market_cap"] is None


def test_stale_shares_outside_alignment_window_is_not_composed() -> None:
    record = compose_market_cap(
        "AAPL",
        grouped_daily_row={"close": 200.0, "trade_date": "2026-07-16"},
        shares_outstanding=15_000_000_000.0,
        shares_observed_at="2025-01-01",  # far more than 100 days old
        shares_alignment_days=100,
    )

    assert record["status"] == "shares_stale"
    assert record["market_cap"] is None
    assert "outside 100-day window" in record["field_evidence"]["market_cap"]["detail"]


def test_shares_within_alignment_window_composes() -> None:
    record = compose_market_cap(
        "AAPL",
        grouped_daily_row={"close": 200.0, "trade_date": "2026-07-16"},
        shares_outstanding=15_000_000_000.0,
        shares_observed_at="2026-04-10",  # 97 days before trade_date
        shares_alignment_days=100,
    )

    assert record["status"] == "composed"
    assert record["market_cap"] == pytest.approx(3_000_000_000_000.0)

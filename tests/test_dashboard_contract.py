"""
Tests for the read-only dashboard contract (v2.0 Platform, first increment).

The contract is pure assembly of existing Atlas outputs. These tests lock its
shape, its versioning and its read-only nature (it never recomputes anything).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dashboard import (
    DASHBOARD_CONTRACT_VERSION,
    DashboardView,
    build_dashboard_view,
    write_dashboard_view,
)
from reports.report_models import (
    CompanyReport,
    MarketSummary,
    PortfolioReport,
)


def _company(symbol: str, decision: str = "BUY") -> CompanyReport:
    return CompanyReport(
        symbol=symbol,
        company_name=f"{symbol} Inc",
        decision=decision,
        investment_score=80.0,
    )


def test_empty_build_is_valid_and_versioned() -> None:
    view = build_dashboard_view()
    data = view.to_dict()

    assert data["contract_version"] == DASHBOARD_CONTRACT_VERSION
    assert data["companies"] == []
    assert data["market"] is None
    assert data["portfolio"] is None
    assert data["outcomes"] is None
    assert "generated_at" in data


def test_companies_are_serialized_in_order() -> None:
    view = build_dashboard_view([_company("AAA"), _company("bbb")])
    data = view.to_dict()

    symbols = [company["symbol"] for company in data["companies"]]
    assert symbols == ["AAA", "BBB"]  # CompanyReport upper-cases the symbol
    assert data["companies"][0]["decision"] == "BUY"


def test_all_views_assembled_from_domain_objects() -> None:
    market = MarketSummary(companies_analyzed=3, new_opportunities=1)
    portfolio = PortfolioReport(
        portfolio_name="Main", holdings_count=2
    )
    outcomes = {"hit_rate": {"hit_rate": 100.0}}  # dict passthrough

    view = build_dashboard_view(
        [_company("AAA")],
        market=market,
        portfolio=portfolio,
        outcomes=outcomes,
    )
    data = view.to_dict()

    assert data["market"]["companies_analyzed"] == 3
    assert data["portfolio"]["portfolio_name"] == "Main"
    assert data["outcomes"]["hit_rate"]["hit_rate"] == 100.0
    assert len(data["companies"]) == 1


def test_build_is_read_only_passthrough() -> None:
    """The builder must not recompute; it forwards existing to_dict output."""
    company = _company("AAA")
    view = build_dashboard_view([company])
    assert view.companies[0] == company.to_dict()


def test_rejects_object_without_to_dict() -> None:
    with pytest.raises(TypeError):
        build_dashboard_view([object()])


def test_write_dashboard_view_roundtrips(tmp_path: Path) -> None:
    view = build_dashboard_view(
        [_company("AAA")],
        market=MarketSummary(companies_analyzed=1),
    )
    path = write_dashboard_view(view, tmp_path / "output" / "dashboard.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["contract_version"] == DASHBOARD_CONTRACT_VERSION
    assert data["companies"][0]["symbol"] == "AAA"
    assert data["market"]["companies_analyzed"] == 1


def test_write_validates_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_dashboard_view(object(), tmp_path / "dashboard.json")

from __future__ import annotations

import re
from pathlib import Path

from reports.research_html import (
    _company_status,
    render_research_report,
    write_research_report,
)

_EXTERNAL_RESOURCE_PATTERN = re.compile(
    r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)["\']', re.IGNORECASE
)


def _ranking() -> dict:
    return {
        "generated_at": "2026-07-14T00:00:00",
        "policy": {"name": "Atlas Analytical Ranking", "min_confidence_score": 70.0},
        "summary": {
            "total_count": 3,
            "universe_eligible_count": 2,
            "candidate_count": 1,
            "blocked_by_reason": {"CONFIDENCE_BELOW_MINIMUM": 1},
        },
        "companies": [
            {
                "symbol": "AAA",
                "sector": "Tech",
                "universe_eligible": True,
                "safeguard_passed": True,
                "safeguard_reasons": [],
                "market_rank": 1,
                "investment_score": 80.0,
                "opportunity_score": 70.0,
                "conviction_score": 85.0,
                "confidence_score": 90.0,
                "candidate_rank": 1,
                "already_held": True,
            },
            {
                "symbol": "BBB",
                "sector": "Health",
                "universe_eligible": True,
                "safeguard_passed": False,
                "safeguard_reasons": ["CONFIDENCE_BELOW_MINIMUM"],
                "market_rank": 2,
                "investment_score": 60.0,
                "opportunity_score": 50.0,
                "conviction_score": 55.0,
                "confidence_score": 40.0,
                "candidate_rank": None,
                "already_held": False,
            },
            {
                "symbol": "CCC",
                "sector": "Energy",
                "universe_eligible": False,
                "safeguard_passed": False,
                "safeguard_reasons": ["UNIVERSE_INELIGIBLE"],
                "market_rank": None,
                "investment_score": 40.0,
                "opportunity_score": 30.0,
                "conviction_score": 35.0,
                "confidence_score": 20.0,
                "candidate_rank": None,
                "already_held": False,
            },
        ],
    }


def _portfolio() -> dict:
    return {
        "summary": {
            "invested_weight": 1.0,
            "sector_weights": {"Tech": 0.6, "Health": 0.4},
            "warnings": ["aviso de teste"],
        },
        "positions": [
            {
                "candidate_rank": 1,
                "symbol": "AAA",
                "name": "Alpha",
                "sector": "Tech",
                "target_weight": 0.6,
                "investment_score": 80.0,
                "reference_price": 123.45,
            },
        ],
    }


def test_company_status_candidate() -> None:
    label, css_class = _company_status(_ranking()["companies"][0])
    assert label == "Candidato #1"
    assert css_class == "badge-good"


def test_company_status_blocked() -> None:
    label, css_class = _company_status(_ranking()["companies"][1])
    assert "CONFIDENCE_BELOW_MINIMUM" in label
    assert css_class == "badge-bad"


def test_company_status_ineligible() -> None:
    label, css_class = _company_status(_ranking()["companies"][2])
    assert label == "Fora do universo"
    assert css_class == "badge-neutral"


def test_render_includes_all_companies_and_model_portfolio() -> None:
    html = render_research_report(_ranking(), _portfolio(), label="Test")
    for symbol in ("AAA", "BBB", "CCC"):
        assert symbol in html
    assert "Carteira-modelo sugerida" in html
    assert "aviso de teste" in html
    assert "3 de 3 empresas" in html


def test_render_without_portfolio_omits_that_section() -> None:
    html = render_research_report(_ranking(), None, label="Test")
    assert "Carteira-modelo sugerida" not in html


def test_no_external_resources() -> None:
    html = render_research_report(_ranking(), _portfolio(), label="Test")
    assert _EXTERNAL_RESOURCE_PATTERN.findall(html) == []


def test_write_research_report_creates_file(tmp_path: Path) -> None:
    html = render_research_report(_ranking(), None, label="Test")
    output = write_research_report(html, tmp_path / "nested" / "report.html")
    assert output.exists()
    assert output.read_text(encoding="utf-8") == html

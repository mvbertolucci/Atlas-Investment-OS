from __future__ import annotations

import json
from pathlib import Path

from watchlist.auto_policy import WatchlistAutoPolicy
from watchlist.opportunity_funnel import (
    FUNNEL_CONTRACT_VERSION,
    build_opportunity_funnel,
    write_opportunity_funnel,
)


def _policy(top_n: int = 2) -> WatchlistAutoPolicy:
    return WatchlistAutoPolicy(
        selection={
            "top_n": top_n,
            "qualifying_decisions": ["STRONG_BUY", "BUY", "ACCUMULATE"],
            "min_confidence_score": 60,
        },
        exit={"investment_score_threshold": 40},
        safeguards={
            "protect_portfolio_holdings": True,
            "protect_manual_entries": True,
        },
        enabled=True,
    )


def _report(path: Path, symbols: list[str]) -> Path:
    companies = [
        {
            "symbol": symbol,
            "name": symbol,
            "sector": "Technology",
            "safeguard_passed": True,
            "investment_score": 90 - index,
            "opportunity_score": 90,
            "conviction_score": 90,
            "confidence_score": 100,
            "deal_breakers": [],
        }
        for index, symbol in enumerate(symbols)
    ]
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-22T12:00:00",
                "summary": {
                    "total_count": len(companies),
                    "universe_eligible_count": len(companies),
                    "candidate_count": len(companies),
                },
                "companies": companies,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_builds_consolidated_deduplicated_funnel(tmp_path: Path) -> None:
    broad = _report(tmp_path / "broad.json", ["AAA", "DUPE"])
    adr = _report(tmp_path / "adr.json", ["DUPE", "KGC"])

    funnel = build_opportunity_funnel(
        [("sp500", None), ("broad_market", broad), ("adr", adr)],
        watchlist_symbols=["AAA"],
        held_symbols=[],
        policy=_policy(top_n=1),
        generated_at="2026-07-22T13:00:00",
    )

    payload = funnel.to_dict()
    assert payload["contract_version"] == FUNNEL_CONTRACT_VERSION
    assert payload["summary"] == {
        "unique_safeguarded_count": 3,
        "qualified_count": 2,
        "selected_count": 1,
    }
    assert payload["selected"][0]["symbol"] == "DUPE"
    assert payload["selected"][0]["source_report"] == "broad_market"
    assert payload["sources"][0]["available"] is False
    assert payload["sources"][2]["candidate_count"] == 2


def test_writes_funnel_atomically(tmp_path: Path) -> None:
    adr = _report(tmp_path / "adr.json", ["KGC"])
    funnel = build_opportunity_funnel(
        [("adr", adr)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    output = write_opportunity_funnel(funnel, tmp_path / "nested" / "funnel.json")

    assert output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["selected"][0][
        "source_report"
    ] == "adr"

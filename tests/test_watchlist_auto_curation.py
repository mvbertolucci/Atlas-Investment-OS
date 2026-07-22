from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from watchlist.auto_curation import (
    select_auto_inclusion_candidates,
    select_auto_removal_candidates,
    run_auto_curation,
)
from watchlist.auto_policy import WatchlistAutoPolicy
from watchlist.loader import load_watchlist_csv
from watchlist.models import WatchlistEntry


def _policy(**overrides) -> WatchlistAutoPolicy:
    selection = {
        "top_n": overrides.pop("top_n", 30),
        "qualifying_decisions": overrides.pop(
            "qualifying_decisions", ["STRONG_BUY", "BUY", "ACCUMULATE"]
        ),
        "min_confidence_score": overrides.pop("min_confidence_score", 60.0),
    }
    exit_section = {
        "investment_score_threshold": overrides.pop(
            "investment_score_threshold", 40.0
        )
    }
    safeguards = {
        "protect_portfolio_holdings": overrides.pop(
            "protect_portfolio_holdings", True
        ),
        "protect_manual_entries": overrides.pop("protect_manual_entries", True),
    }
    assert not overrides, f"unrecognized overrides: {overrides}"
    return WatchlistAutoPolicy(
        selection=selection, exit=exit_section, safeguards=safeguards, enabled=True
    )


def _company(
    symbol: str,
    *,
    investment_score: float = 80.0,
    opportunity_score: float = 90.0,
    conviction_score: float = 90.0,
    confidence_score: float = 75.0,
    safeguard_passed: bool = True,
    deal_breakers: list[str] | None = None,
    sector: str = "Technology",
    candidate_rank: int = 1,
) -> dict:
    """STRONG_BUY por padrão (opportunity/conviction >= 80/85)."""
    return {
        "symbol": symbol,
        "name": f"{symbol} Inc.",
        "sector": sector,
        "safeguard_passed": safeguard_passed,
        "candidate_rank": candidate_rank,
        "investment_score": investment_score,
        "opportunity_score": opportunity_score,
        "conviction_score": conviction_score,
        "confidence_score": confidence_score,
        "deal_breakers": deal_breakers or [],
        "already_held": False,
    }


def _write_report(path: Path, companies: list[dict]) -> Path:
    path.write_text(
        json.dumps({"companies": companies}), encoding="utf-8"
    )
    return path


# --- select_auto_inclusion_candidates --------------------------------------


def test_selects_and_ranks_by_investment_score_desc(tmp_path: Path) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [
            _company("AAA", investment_score=70.0),
            _company("BBB", investment_score=95.0),
            _company("CCC", investment_score=82.0),
        ],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert [c.symbol for c in candidates] == ["BBB", "CCC", "AAA"]


def test_top_n_caps_result_count(tmp_path: Path) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [_company(f"S{i}", investment_score=float(i)) for i in range(10)],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(top_n=3),
    )
    assert len(candidates) == 3
    assert [c.symbol for c in candidates] == ["S9", "S8", "S7"]


@pytest.mark.parametrize(
    "opportunity,conviction,expected_decision",
    [
        (90.0, 90.0, "STRONG_BUY"),
        (76.0, 72.0, "BUY"),
        (66.0, 61.0, "ACCUMULATE"),
        (56.0, 51.0, "HOLD"),
        (20.0, 20.0, "AVOID"),
    ],
)
def test_decision_estimate_matches_decision_policy_thresholds(
    tmp_path: Path, opportunity: float, conviction: float, expected_decision: str
) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [
            _company(
                "AAA", opportunity_score=opportunity, conviction_score=conviction
            )
        ],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        # aceita todas as decisões para observar a classificação sem filtro
        policy=_policy(
            qualifying_decisions=[
                "STRONG_BUY", "BUY", "ACCUMULATE", "HOLD", "WATCH", "AVOID",
            ]
        ),
    )
    assert candidates[0].decision_estimate == expected_decision


def test_non_qualifying_decision_is_excluded(tmp_path: Path) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [
            _company("HOLDME", opportunity_score=56.0, conviction_score=51.0),
            _company("BUYME", opportunity_score=90.0, conviction_score=90.0),
        ],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),  # default: STRONG_BUY/BUY/ACCUMULATE only
    )
    assert [c.symbol for c in candidates] == ["BUYME"]


def test_low_confidence_score_excludes_even_qualifying_decision(
    tmp_path: Path,
) -> None:
    """Salvaguarda confirmada: decisão estimada otimista (risk_penalty=0.0)
    não basta sozinha -- confidence_score também precisa passar o piso."""
    path = _write_report(
        tmp_path / "sp500.json",
        [_company("LOWCONF", confidence_score=40.0)],  # abaixo do min 60
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(min_confidence_score=60.0),
    )
    assert candidates == ()


def test_excludes_symbols_already_watched_or_held(tmp_path: Path) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [_company("WATCHED"), _company("HELD"), _company("NEW")],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=["watched"],
        held_symbols=["held"],
        policy=_policy(),
    )
    assert [c.symbol for c in candidates] == ["NEW"]


def test_requires_safeguard_passed(tmp_path: Path) -> None:
    path = _write_report(
        tmp_path / "sp500.json",
        [_company("FAILED", safeguard_passed=False), _company("PASSED")],
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert [c.symbol for c in candidates] == ["PASSED"]


def test_dedup_across_sources_first_source_wins(tmp_path: Path) -> None:
    sp500 = _write_report(
        tmp_path / "sp500.json", [_company("DUPE", investment_score=99.0)]
    )
    broad = _write_report(
        tmp_path / "broad.json", [_company("DUPE", investment_score=1.0)]
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", sp500), ("broad_market", broad)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert len(candidates) == 1
    assert candidates[0].source_report == "sp500"
    assert candidates[0].investment_score == 99.0


def test_includes_adr_candidates_and_preserves_source(tmp_path: Path) -> None:
    adr = _write_report(
        tmp_path / "adr.json", [_company("KGC", investment_score=88.0)]
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", None), ("broad_market", None), ("adr", adr)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert [candidate.symbol for candidate in candidates] == ["KGC"]
    assert candidates[0].source_report == "adr"
    assert "Auto-inclusão (adr)" in candidates[0].note


def test_broad_market_wins_duplicate_over_adr(tmp_path: Path) -> None:
    broad = _write_report(
        tmp_path / "broad.json", [_company("DUPE", investment_score=90.0)]
    )
    adr = _write_report(
        tmp_path / "adr.json", [_company("DUPE", investment_score=99.0)]
    )
    candidates = select_auto_inclusion_candidates(
        [("sp500", None), ("broad_market", broad), ("adr", adr)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert len(candidates) == 1
    assert candidates[0].source_report == "broad_market"
    assert candidates[0].investment_score == 90.0


def test_missing_report_file_is_skipped_not_error(tmp_path: Path) -> None:
    candidates = select_auto_inclusion_candidates(
        [("sp500", tmp_path / "does_not_exist.json"), ("broad_market", None)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert candidates == ()


def test_unreadable_json_is_skipped_not_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    candidates = select_auto_inclusion_candidates(
        [("sp500", path)],
        watchlist_symbols=[],
        held_symbols=[],
        policy=_policy(),
    )
    assert candidates == ()


# --- select_auto_removal_candidates -----------------------------------------


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_removal_only_considers_source_auto(tmp_path: Path) -> None:
    entries = (
        WatchlistEntry(symbol="AUTOLOW", source="auto"),
        WatchlistEntry(symbol="MANUALLOW", source="manual"),
    )
    frame = _frame(
        [
            {"symbol": "AUTOLOW", "origin": "watchlist", "Investment Score": 10.0},
            {"symbol": "MANUALLOW", "origin": "watchlist", "Investment Score": 10.0},
        ]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy()
    )
    assert [c.symbol for c in candidates] == ["AUTOLOW"]


def test_removal_never_touches_portfolio_holding_even_when_auto_and_low_score(
    tmp_path: Path,
) -> None:
    """O teste mais importante de acertar: uma entrada source=auto que
    também é holding real, com score bem abaixo do patamar, NUNCA pode ser
    removida automaticamente."""
    entries = (WatchlistEntry(symbol="HELDLOW", source="auto"),)
    frame = _frame(
        [{"symbol": "HELDLOW", "origin": "portfolio", "Investment Score": 5.0}]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy()
    )
    assert candidates == ()


def test_removal_skips_symbol_missing_from_scored_frame(tmp_path: Path) -> None:
    entries = (WatchlistEntry(symbol="GONE", source="auto"),)
    frame = _frame(
        [{"symbol": "OTHER", "origin": "watchlist", "Investment Score": 10.0}]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy()
    )
    assert candidates == ()


def test_removal_skips_nan_investment_score(tmp_path: Path) -> None:
    entries = (WatchlistEntry(symbol="NANNED", source="auto"),)
    frame = _frame(
        [{"symbol": "NANNED", "origin": "watchlist", "Investment Score": float("nan")}]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy()
    )
    assert candidates == ()


def test_removal_respects_threshold(tmp_path: Path) -> None:
    entries = (
        WatchlistEntry(symbol="BELOW", source="auto"),
        WatchlistEntry(symbol="ABOVE", source="auto"),
    )
    frame = _frame(
        [
            {"symbol": "BELOW", "origin": "watchlist", "Investment Score": 39.9},
            {"symbol": "ABOVE", "origin": "watchlist", "Investment Score": 40.1},
        ]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy(investment_score_threshold=40.0)
    )
    assert [c.symbol for c in candidates] == ["BELOW"]


def test_protect_manual_entries_can_be_disabled_via_policy(tmp_path: Path) -> None:
    """Config explícito, não hardcoded -- com a salvaguarda desligada,
    entradas manuais também ficam elegíveis."""
    entries = (WatchlistEntry(symbol="MANUALLOW", source="manual"),)
    frame = _frame(
        [{"symbol": "MANUALLOW", "origin": "watchlist", "Investment Score": 10.0}]
    )
    candidates = select_auto_removal_candidates(
        entries, scored_frame=frame, policy=_policy(protect_manual_entries=False)
    )
    assert [c.symbol for c in candidates] == ["MANUALLOW"]


# --- run_auto_curation -------------------------------------------------------


def test_disabled_policy_does_not_touch_csv(tmp_path: Path) -> None:
    watchlist_path = tmp_path / "watchlist.csv"
    original = "symbol,name,source\nADBE,Adobe,manual\n"
    watchlist_path.write_text(original, encoding="utf-8")

    disabled = WatchlistAutoPolicy(
        selection={}, exit={}, safeguards={}, enabled=False
    )
    result = run_auto_curation(
        watchlist_path=watchlist_path,
        sp500_report_path=None,
        broad_market_report_path=None,
        adr_report_path=None,
        scored_frame=pd.DataFrame(),
        policy=disabled,
    )

    assert result.enabled is False
    assert result.included == ()
    assert result.excluded == ()
    assert watchlist_path.read_text(encoding="utf-8") == original


def test_run_auto_curation_includes_and_excludes_end_to_end(
    tmp_path: Path,
) -> None:
    watchlist_path = tmp_path / "watchlist.csv"
    watchlist_path.write_text(
        "symbol,name,source\nSTALE,Stale Co,auto\nKEPT,Kept Co,manual\n",
        encoding="utf-8",
    )
    sp500_path = _write_report(
        tmp_path / "sp500.json", [_company("FRESH", investment_score=88.0)]
    )
    frame = _frame(
        [
            {"symbol": "STALE", "origin": "watchlist", "Investment Score": 12.0},
            {"symbol": "KEPT", "origin": "watchlist", "Investment Score": 12.0},
        ]
    )

    result = run_auto_curation(
        watchlist_path=watchlist_path,
        sp500_report_path=sp500_path,
        broad_market_report_path=None,
        adr_report_path=None,
        scored_frame=frame,
        policy=_policy(),
        today=date(2026, 7, 21),
    )

    assert [c.symbol for c in result.included] == ["FRESH"]
    assert [c.symbol for c in result.excluded] == ["STALE"]

    entries = load_watchlist_csv(watchlist_path)
    by_symbol = {entry.symbol: entry for entry in entries}
    assert set(by_symbol) == {"KEPT", "FRESH"}
    assert by_symbol["FRESH"].source == "auto"
    assert by_symbol["KEPT"].source == "manual"


def test_symbol_included_this_run_is_never_also_removed(tmp_path: Path) -> None:
    """Um símbolo cuja decisão estimada agora qualifica para top-30, mas que
    já estava na watchlist com score baixo, não deve virar uma dança de
    incluir-e-remover no mesmo run -- ele já está em `watchlist_symbols`
    antes da inclusão rodar, então nunca aparece como candidato novo; do
    lado da remoção, seu `source` real (o que já tinha antes) decide."""
    watchlist_path = tmp_path / "watchlist.csv"
    watchlist_path.write_text(
        "symbol,name,source\nRECOVER,Recover Co,auto\n", encoding="utf-8"
    )
    sp500_path = _write_report(
        tmp_path / "sp500.json", [_company("RECOVER", investment_score=95.0)]
    )
    frame = _frame(
        [{"symbol": "RECOVER", "origin": "watchlist", "Investment Score": 95.0}]
    )

    result = run_auto_curation(
        watchlist_path=watchlist_path,
        sp500_report_path=sp500_path,
        broad_market_report_path=None,
        adr_report_path=None,
        scored_frame=frame,
        policy=_policy(),
    )

    # Já estava na watchlist -> não é candidato de inclusão (dedup contra
    # watchlist_symbols); score 95 >= 40 -> não é candidato de remoção.
    assert result.included == ()
    assert result.excluded == ()
    entries = load_watchlist_csv(watchlist_path)
    assert {entry.symbol for entry in entries} == {"RECOVER"}

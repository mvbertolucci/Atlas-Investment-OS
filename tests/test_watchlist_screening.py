from __future__ import annotations

from dataclasses import dataclass

from watchlist.screening import (
    derive_trigger_condition,
    propose_watchlist_candidates,
)


# --- derivação de trigger por perfil --------------------------------------


def test_low_confidence_watches_until_it_crosses_screener_floor() -> None:
    derived = derive_trigger_condition({"Confidence Score": 55.0, "Investment Score": 72.0})
    assert derived.condition == "confidence >= 70"


def test_above_consensus_target_watches_for_valuation_reopening() -> None:
    derived = derive_trigger_condition(
        {"Confidence Score": 90.0, "target_upside": -5.0, "Investment Score": 72.0}
    )
    assert derived.condition == "target_upside > 0"


def test_score_ladder_points_to_next_buy_tier() -> None:
    # confiança ok, sem problema de valuation -> escada de score
    assert derive_trigger_condition(
        {"Confidence Score": 90.0, "target_upside": 12.0, "Investment Score": 65.0}
    ).condition == "score > 70"
    assert derive_trigger_condition(
        {"Confidence Score": 90.0, "target_upside": 12.0, "Investment Score": 75.0}
    ).condition == "score > 80"
    assert derive_trigger_condition(
        {"Confidence Score": 90.0, "target_upside": 12.0, "Investment Score": 85.0}
    ).condition == "score > 90"


def test_top_tier_falls_back_to_earnings_recheck() -> None:
    derived = derive_trigger_condition(
        {"Confidence Score": 100.0, "target_upside": 30.0, "Investment Score": 93.0}
    )
    assert derived.condition == "earnings_passed"


def test_no_score_stays_passive_never_invented() -> None:
    derived = derive_trigger_condition({"name": "Sem dados"})
    assert derived.condition == ""


def test_derived_condition_field_is_in_trigger_whitelist() -> None:
    # Toda condição derivada tem que ser aceita pelo parser real de triggers
    # (mesmo whitelist), senão a sugestão seria inaplicável.
    from watchlist.triggers import parse_trigger_condition

    profiles = [
        {"Confidence Score": 55.0, "Investment Score": 72.0},
        {"Confidence Score": 90.0, "target_upside": -5.0, "Investment Score": 72.0},
        {"Confidence Score": 90.0, "target_upside": 12.0, "Investment Score": 65.0},
        {"Confidence Score": 100.0, "target_upside": 30.0, "Investment Score": 93.0},
    ]
    for profile in profiles:
        condition = derive_trigger_condition(profile).condition
        assert condition  # não vazio para estes perfis
        parse_trigger_condition(condition)  # não levanta


# --- proposta por critério ------------------------------------------------


@dataclass(frozen=True)
class _FakeCompany:
    symbol: str
    sector: str
    safeguard_passed: bool
    candidate_rank: int | None
    investment_score: float | None
    confidence_score: float | None
    already_held: bool = False


@dataclass(frozen=True)
class _FakeRanking:
    companies: tuple[_FakeCompany, ...]


def _ranking() -> _FakeRanking:
    return _FakeRanking(
        companies=(
            _FakeCompany("AAA", "Tech", True, 1, 80.0, 100.0),
            _FakeCompany("BBB", "Tech", True, 2, 78.0, 95.0),
            _FakeCompany("CCC", "Tech", True, 3, 76.0, 90.0),  # 3o Tech -> cortado
            _FakeCompany("DDD", "Health", True, 4, 74.0, 90.0),
            _FakeCompany("HELD", "Energy", True, 5, 73.0, 90.0, already_held=True),
            _FakeCompany("NOTCAND", "Energy", False, None, 40.0, 30.0),
        )
    )


def _analyzed() -> dict:
    return {
        "AAA": {"name": "Alpha", "Confidence Score": 100.0, "Investment Score": 80.0, "target_upside": 15.0},
        "BBB": {"name": "Beta", "Confidence Score": 95.0, "Investment Score": 78.0, "target_upside": -3.0},
        "DDD": {"name": "Delta", "Confidence Score": 90.0, "Investment Score": 74.0, "target_upside": 20.0},
    }


def test_proposal_respects_sector_cap_and_rank_order() -> None:
    proposals = propose_watchlist_candidates(
        _ranking(),
        analyzed_by_symbol=_analyzed(),
        watchlist_symbols=(),
        max_per_sector=2,
    )
    symbols = [p.symbol for p in proposals]
    # AAA, BBB (2 Tech, cap), DDD (Health). CCC cortado pelo cap de setor.
    assert symbols == ["AAA", "BBB", "DDD"]


def test_proposal_excludes_held_and_non_candidates() -> None:
    proposals = propose_watchlist_candidates(
        _ranking(),
        analyzed_by_symbol=_analyzed(),
        watchlist_symbols=(),
        max_per_sector=5,
    )
    symbols = {p.symbol for p in proposals}
    assert "HELD" not in symbols  # already_held
    assert "NOTCAND" not in symbols  # safeguard_passed False / sem candidate_rank


def test_proposal_excludes_already_watched() -> None:
    proposals = propose_watchlist_candidates(
        _ranking(),
        analyzed_by_symbol=_analyzed(),
        watchlist_symbols=("aaa",),  # case-insensitive
        max_per_sector=2,
    )
    assert "AAA" not in {p.symbol for p in proposals}


def test_proposal_carries_derived_condition_per_profile() -> None:
    proposals = propose_watchlist_candidates(
        _ranking(),
        analyzed_by_symbol=_analyzed(),
        watchlist_symbols=(),
        max_per_sector=2,
    )
    by_symbol = {p.symbol: p for p in proposals}
    # BBB negocia acima do alvo (target_upside -3) -> condição de valuation
    assert by_symbol["BBB"].suggested_condition == "target_upside > 0"
    # AAA: confiança 100, upside +15, score 80 -> próxima faixa (Comprar Forte)
    assert by_symbol["AAA"].suggested_condition == "score > 90"
    assert by_symbol["AAA"].name == "Alpha"


def test_limit_caps_total_proposals() -> None:
    proposals = propose_watchlist_candidates(
        _ranking(),
        analyzed_by_symbol=_analyzed(),
        watchlist_symbols=(),
        max_per_sector=5,
        limit=1,
    )
    assert len(proposals) == 1
    assert proposals[0].symbol == "AAA"

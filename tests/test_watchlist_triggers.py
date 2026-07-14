from __future__ import annotations

import pandas as pd
import pytest

from watchlist.models import WatchlistEntry
from watchlist.triggers import (
    FIELD_ALIASES,
    InvalidTriggerConditionError,
    evaluate_watchlist_triggers,
    normalize_current_row,
    parse_trigger_condition,
)


# --- parser ---------------------------------------------------------------


def test_parse_valid_comparison_conditions() -> None:
    condition = parse_trigger_condition("score > 75")
    assert condition.kind == "comparison"
    assert condition.field == "investment_score"
    assert condition.comparator == ">"
    assert condition.threshold == 75.0

    condition = parse_trigger_condition("f_score >= 7")
    assert condition.field == "f_score_annual"
    assert condition.comparator == ">="
    assert condition.threshold == 7.0


def test_parse_earnings_passed_literal() -> None:
    condition = parse_trigger_condition("earnings_passed")
    assert condition.kind == "earnings_passed"
    assert condition.field is None


def test_parse_rejects_invalid_syntax() -> None:
    with pytest.raises(InvalidTriggerConditionError):
        parse_trigger_condition("score >>> 75")
    with pytest.raises(InvalidTriggerConditionError):
        parse_trigger_condition("")
    with pytest.raises(InvalidTriggerConditionError):
        parse_trigger_condition("just some text")


def test_parse_rejects_unknown_field() -> None:
    with pytest.raises(InvalidTriggerConditionError):
        parse_trigger_condition("unknown_field > 10")


def test_no_price_field_exists_in_whitelist() -> None:
    """
    Teste negativo pedido pela spec: alertas de preço ficam fora do escopo
    do Atlas (a corretora já cobre em tempo real). Nenhum campo de preço
    pode entrar no whitelist sem uma decisão consciente que reescreva este
    teste.
    """
    forbidden = {
        "price",
        "current_price",
        "target_price",
        "target_high_price",
        "target_low_price",
        "previous_close",
        "year_high",
        "year_low",
        "sma_50",
        "sma_200",
    }
    assert forbidden.isdisjoint(FIELD_ALIASES.keys())
    assert forbidden.isdisjoint(FIELD_ALIASES.values())

    for forbidden_field in forbidden:
        with pytest.raises(InvalidTriggerConditionError):
            parse_trigger_condition(f"{forbidden_field} > 100")


# --- normalize_current_row -------------------------------------------------


def test_normalize_current_row_aliases_title_case_scores() -> None:
    row = {
        "symbol": "AAA",
        "Investment Score": 80.0,
        "Confidence Score": 90.0,
        "altman_z": 3.5,
    }
    normalized = normalize_current_row(row)
    assert normalized["investment_score"] == 80.0
    assert normalized["confidence_score"] == 90.0
    assert normalized["altman_z"] == 3.5
    assert normalized["score_coverage"] == 90.0


# --- evaluate_watchlist_triggers: transição --------------------------------


def test_true_to_true_does_not_refire() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="score > 75"),)
    current = {"AAA": {"investment_score": 80.0}}
    previous = {"AAA": {"investment_score": 78.0}}

    results = evaluate_watchlist_triggers(
        entries,
        current,
        previous_by_symbol=previous,
        baseline_status="comparable",
    )
    assert results[0].status == "clear"


def test_false_to_true_fires() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="score > 75"),)
    current = {"AAA": {"investment_score": 80.0}}
    previous = {"AAA": {"investment_score": 60.0}}

    results = evaluate_watchlist_triggers(
        entries,
        current,
        previous_by_symbol=previous,
        baseline_status="comparable",
    )
    assert results[0].status == "triggered"


@pytest.mark.parametrize("status", ["first_run", "model_version_changed"])
def test_no_comparable_baseline_never_fires(status: str) -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="score > 75"),)
    current = {"AAA": {"investment_score": 80.0}}

    results = evaluate_watchlist_triggers(
        entries,
        current,
        previous_by_symbol={},
        baseline_status=status,
    )
    assert results[0].status == "not_evaluated"
    assert results[0].triggered_this_run is False


def test_passive_entry_without_condition_is_never_triggered() -> None:
    entries = (WatchlistEntry(symbol="AAA"),)
    results = evaluate_watchlist_triggers(entries, {"AAA": {"investment_score": 999}})
    assert results[0].status == "no_condition"


def test_invalid_condition_in_csv_is_reported_not_silent() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="not a condition"),)
    results = evaluate_watchlist_triggers(entries, {"AAA": {}})
    assert results[0].status == "invalid_condition"
    assert "inválida" in results[0].message


def test_missing_current_data_is_not_evaluated() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="score > 75"),)
    results = evaluate_watchlist_triggers(
        entries,
        {},
        previous_by_symbol={"AAA": {"investment_score": 60.0}},
        baseline_status="comparable",
    )
    assert results[0].status == "not_evaluated"


# --- earnings_passed --------------------------------------------------------


def test_earnings_passed_fires_only_inside_window() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="earnings_passed"),)
    current = {"AAA": {"earnings_date": "2026-07-10"}}

    fires = evaluate_watchlist_triggers(
        entries,
        current,
        previous_run_at=pd.Timestamp("2026-07-01"),
        current_run_at=pd.Timestamp("2026-07-14"),
    )
    assert fires[0].status == "triggered"

    no_fire = evaluate_watchlist_triggers(
        entries,
        {"AAA": {"earnings_date": "2026-06-01"}},
        previous_run_at=pd.Timestamp("2026-07-01"),
        current_run_at=pd.Timestamp("2026-07-14"),
    )
    assert no_fire[0].status == "clear"


def test_earnings_passed_not_evaluated_without_previous_run() -> None:
    entries = (WatchlistEntry(symbol="AAA", trigger_condition="earnings_passed"),)
    results = evaluate_watchlist_triggers(
        entries, {"AAA": {"earnings_date": "2026-07-10"}}
    )
    assert results[0].status == "not_evaluated"

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.sell_rules import (
    RULE_NAMES,
    SellRuleContext,
    SellRulesPolicy,
    evaluate_sell_rules,
    load_sell_rules_policy,
    score_percentiles,
)


def _ctx(
    *,
    sector: str = "Consumer Cyclical",
    industry: str = "Retail - Apparel",
    baseline_status: str = "first_run",
    previous: dict | None = None,
    score_percentile: float | None = None,
    universe_size: int = 0,
    universe_scope: str = "reduced",
    earnings_since_last_run: bool | None = None,
    confidence_score: float = 90.0,
    score_coverage: float = 90.0,
    **current_overrides,
) -> SellRuleContext:
    """
    Contexto com confiança/cobertura acima do gate por padrão, para isolar o
    comportamento de cada regra sem o gating de confiança mascarar o action.
    Setor/indústria neutros (não batem nenhuma isenção de distress).
    """
    current = {
        "confidence_score": confidence_score,
        "score_coverage": score_coverage,
        **current_overrides,
    }
    return SellRuleContext(
        symbol="TEST",
        sector=sector,
        industry=industry,
        current=current,
        previous=previous,
        baseline_status=baseline_status,
        score_percentile=score_percentile,
        universe_size=universe_size,
        universe_scope=universe_scope,
        earnings_since_last_run=earnings_since_last_run,
    )


@pytest.fixture(scope="module")
def policy() -> SellRulesPolicy:
    return load_sell_rules_policy(Path("config/sell_rules.yaml"))


def _evaluation(decision, name: str):
    return next(item for item in decision.evaluations if item.name == name)


def test_canonical_sell_rules_policy_is_pinned(policy: SellRulesPolicy) -> None:
    """
    Trava os thresholds/isenções confirmados: 1.8 (não 4.35) para altman_z,
    calibrado à fórmula clássica que analytics/fundamentals.py de fato
    computa; Utilities reincluída na isenção de solvência.
    """
    assert policy.distress["altman_z_threshold"] == 1.8
    assert policy.distress["altman_z_exempt_sectors"] == [
        "Utilities",
        "Financial Services",
        "Banks",
        "Insurance",
        "Biotechnology",
    ]
    assert policy.distress["interest_coverage_threshold"] == 2.5
    assert policy.distress["net_debt_ebitda_threshold"] == 4.0
    assert policy.distress["net_debt_ebitda_exempt_sectors"] == [
        "Biotechnology"
    ]
    assert policy.distress["current_ratio_threshold"] == 1.0
    assert policy.distress["current_ratio_exempt_sectors"] == [
        "Software",
        "Tobacco",
    ]
    assert policy.distress["short_float_threshold"] == 20.0
    assert policy.distress["f_score_floor"] == 4
    assert policy.distress["f_score_exempt_sectors"] == ["Biotechnology"]
    assert policy.trim_at == 1
    assert policy.sell_at == 2
    assert policy.distress_review_at == 1
    assert policy.distress_sell_at == 2
    assert policy.distress_overrides_escalation is True
    assert policy.relative_decay_review_only is True


# --- distress: as 6 condições, cada uma isolada com epsilon no limite -----


def test_distress_altman_z_triggers_below_threshold(policy: SellRulesPolicy) -> None:
    triggered = evaluate_sell_rules(_ctx(altman_z=1.79), policy)
    clear = evaluate_sell_rules(_ctx(altman_z=1.81), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


def test_distress_interest_coverage_triggers_below_threshold(
    policy: SellRulesPolicy,
) -> None:
    triggered = evaluate_sell_rules(_ctx(interest_coverage=2.49), policy)
    clear = evaluate_sell_rules(_ctx(interest_coverage=2.51), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


def test_distress_net_debt_ebitda_triggers_above_threshold(
    policy: SellRulesPolicy,
) -> None:
    triggered = evaluate_sell_rules(_ctx(net_debt_ebitda=4.01), policy)
    clear = evaluate_sell_rules(_ctx(net_debt_ebitda=3.99), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


def test_distress_current_ratio_triggers_below_threshold(
    policy: SellRulesPolicy,
) -> None:
    triggered = evaluate_sell_rules(_ctx(current_liquidity=0.99), policy)
    clear = evaluate_sell_rules(_ctx(current_liquidity=1.01), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


def test_distress_short_float_triggers_above_threshold(
    policy: SellRulesPolicy,
) -> None:
    triggered = evaluate_sell_rules(_ctx(short_float=20.01), policy)
    clear = evaluate_sell_rules(_ctx(short_float=19.99), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


def test_distress_f_score_floor_triggers_below_threshold(
    policy: SellRulesPolicy,
) -> None:
    triggered = evaluate_sell_rules(_ctx(f_score_annual=3), policy)
    # f_score_annual == floor (4) não é "abaixo do piso" -- não dispara.
    clear = evaluate_sell_rules(_ctx(f_score_annual=4), policy)
    assert _evaluation(triggered, "distress").triggered is True
    assert _evaluation(clear, "distress").triggered is False


# --- distress: isenção por condição, não isenção geral ---------------------


def test_distress_financial_services_exempt_from_solvency_only(
    policy: SellRulesPolicy,
) -> None:
    """
    Financial Services isenta altman_z/interest_coverage (mesma família de
    solvência), mas NÃO isenta net_debt_ebitda/current_ratio/short_float/
    f_score -- isenção é por condição, não um bloqueio geral da regra.
    """
    exempt = evaluate_sell_rules(
        _ctx(sector="Financial Services", industry="Banks", altman_z=0.5),
        policy,
    )
    assert _evaluation(exempt, "distress").triggered is False

    still_triggers = evaluate_sell_rules(
        _ctx(
            sector="Financial Services",
            industry="Banks",
            altman_z=0.5,
            short_float=25.0,
        ),
        policy,
    )
    assert _evaluation(still_triggers, "distress").triggered is True
    assert "short_float" in _evaluation(still_triggers, "distress").message


def test_distress_utilities_reincluded_in_solvency_exemption(
    policy: SellRulesPolicy,
) -> None:
    exempt = evaluate_sell_rules(
        _ctx(
            sector="Utilities",
            industry="Utilities - Regulated Electric",
            altman_z=0.1,
            interest_coverage=0.1,
        ),
        policy,
    )
    assert _evaluation(exempt, "distress").triggered is False


def test_distress_software_exempt_only_from_liquidity(
    policy: SellRulesPolicy,
) -> None:
    exempt = evaluate_sell_rules(
        _ctx(
            sector="Technology",
            industry="Software - Application",
            current_liquidity=0.2,
        ),
        policy,
    )
    assert _evaluation(exempt, "distress").triggered is False

    still_triggers = evaluate_sell_rules(
        _ctx(
            sector="Technology",
            industry="Software - Application",
            current_liquidity=0.2,
            altman_z=0.5,
        ),
        policy,
    )
    assert _evaluation(still_triggers, "distress").triggered is True


def test_distress_biotechnology_exempts_non_meaningful_profit_metrics(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            sector="Healthcare",
            industry="Biotechnology",
            altman_z=-5.0,
            interest_coverage=-20.0,
            net_debt_ebitda=50.0,
            f_score_annual=1,
        ),
        policy,
    )
    assert _evaluation(result, "distress").triggered is False


def test_distress_tobacco_exempt_from_current_ratio_only(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            sector="Consumer Defensive",
            industry="Tobacco",
            current_liquidity=0.5,
        ),
        policy,
    )
    assert _evaluation(result, "distress").triggered is False


def test_distress_not_evaluated_when_all_exempt_or_missing(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(sector="Financial Services", industry="Banks"),
        policy,
    )
    evaluation = _evaluation(result, "distress")
    assert evaluation.status == "not_evaluated"
    assert evaluation.triggered is False


def test_distress_disabled_by_config() -> None:
    policy = load_sell_rules_policy(Path("config/sell_rules.yaml"))
    disabled = SellRulesPolicy(
        confidence_gate=policy.confidence_gate,
        distress={**policy.distress, "enabled": False},
        valuation_stretch=policy.valuation_stretch,
        fundamental_decay=policy.fundamental_decay,
        relative_decay=policy.relative_decay,
        escalation=policy.escalation,
    )
    result = evaluate_sell_rules(_ctx(altman_z=0.1), disabled)
    evaluation = _evaluation(result, "distress")
    assert evaluation.status == "disabled"
    assert evaluation.triggered is False


# --- valuation_stretch -------------------------------------------------


def test_valuation_stretch_triggers_below_threshold(policy: SellRulesPolicy) -> None:
    # threshold default -0.10 (fração); target_upside vem em pontos percentuais.
    triggered = evaluate_sell_rules(_ctx(target_upside=-11.0), policy)
    clear = evaluate_sell_rules(_ctx(target_upside=-9.0), policy)
    assert _evaluation(triggered, "valuation_stretch").triggered is True
    assert _evaluation(clear, "valuation_stretch").triggered is False


def test_valuation_stretch_not_evaluated_when_missing(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(_ctx(), policy)
    evaluation = _evaluation(result, "valuation_stretch")
    assert evaluation.status == "not_evaluated"


# --- fundamental_decay --------------------------------------------------


def test_fundamental_decay_not_evaluated_without_comparable_baseline(
    policy: SellRulesPolicy,
) -> None:
    for status in ("first_run", "model_version_changed"):
        result = evaluate_sell_rules(
            _ctx(
                baseline_status=status,
                f_score_annual=2,
                previous={"f_score_annual": 9},
            ),
            policy,
        )
        evaluation = _evaluation(result, "fundamental_decay")
        assert evaluation.status == "not_evaluated"
        assert evaluation.triggered is False


def test_fundamental_decay_triggers_on_f_score_drop(policy: SellRulesPolicy) -> None:
    result = evaluate_sell_rules(
        _ctx(
            baseline_status="comparable",
            f_score_annual=5,
            previous={"f_score_annual": 8},
        ),
        policy,
    )
    assert _evaluation(result, "fundamental_decay").triggered is True


def test_fundamental_decay_triggers_on_roic_relative_drop(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            baseline_status="comparable",
            roic=0.07,
            previous={"roic": 0.10},
        ),
        policy,
    )
    assert _evaluation(result, "fundamental_decay").triggered is True


def test_fundamental_decay_clear_on_small_change(policy: SellRulesPolicy) -> None:
    result = evaluate_sell_rules(
        _ctx(
            baseline_status="comparable",
            f_score_annual=8,
            previous={"f_score_annual": 8},
        ),
        policy,
    )
    assert _evaluation(result, "fundamental_decay").triggered is False


# --- relative_decay ------------------------------------------------------


def test_relative_decay_triggers_below_percentile(policy: SellRulesPolicy) -> None:
    triggered = evaluate_sell_rules(
        _ctx(score_percentile=39.0, universe_size=100, universe_scope="broad"),
        policy,
    )
    clear = evaluate_sell_rules(
        _ctx(score_percentile=41.0, universe_size=100, universe_scope="broad"),
        policy,
    )
    assert _evaluation(triggered, "relative_decay").triggered is True
    assert _evaluation(clear, "relative_decay").triggered is False


def test_relative_decay_message_reflects_reduced_scope(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(score_percentile=10.0, universe_size=20, universe_scope="reduced"),
        policy,
    )
    evaluation = _evaluation(result, "relative_decay")
    assert "reduzido" in evaluation.message
    assert "N=20" in evaluation.message


def test_relative_decay_not_evaluated_without_percentile(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(_ctx(), policy)
    evaluation = _evaluation(result, "relative_decay")
    assert evaluation.status == "not_evaluated"


# --- escalação HOLD -> TRIM -> SELL --------------------------------------


def test_escalation_two_actionable_non_distress_rules_sell(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            target_upside=-15.0,
            baseline_status="comparable",
            f_score_annual=5,
            previous={"f_score_annual": 8},
        ),
        policy,
    )
    non_distress_triggered = [
        name for name in result.triggered_rules if name != "distress"
    ]
    assert len(non_distress_triggered) >= 2
    assert result.action == "SELL"


def test_escalation_one_non_distress_rule_trims(policy: SellRulesPolicy) -> None:
    result = evaluate_sell_rules(_ctx(target_upside=-15.0), policy)
    assert result.triggered_rules == ("valuation_stretch",)
    assert result.action == "TRIM"


def test_distress_single_evidence_requires_review(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(_ctx(altman_z=0.5), policy)
    assert result.triggered_rules == ("distress",)
    assert _evaluation(result, "distress").evidence_count == 1
    assert result.action == "REVISAR"


def test_distress_two_independent_evidence_groups_sell(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(altman_z=0.5, net_debt_ebitda=5.0),
        policy,
    )
    assert result.triggered_rules == ("distress",)
    assert _evaluation(result, "distress").evidence_count == 2
    assert result.action == "SELL"


def test_distress_correlated_solvency_metrics_count_once(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(altman_z=0.5, interest_coverage=1.0),
        policy,
    )
    assert _evaluation(result, "distress").evidence_count == 1
    assert result.action == "REVISAR"


def test_distress_review_remains_conservative_when_override_disabled(
    policy: SellRulesPolicy,
) -> None:
    no_override = SellRulesPolicy(
        confidence_gate=policy.confidence_gate,
        distress=policy.distress,
        valuation_stretch=policy.valuation_stretch,
        fundamental_decay=policy.fundamental_decay,
        relative_decay=policy.relative_decay,
        escalation={**policy.escalation, "distress_overrides_escalation": False},
    )
    result = evaluate_sell_rules(_ctx(altman_z=0.5), no_override)
    assert result.triggered_rules == ("distress",)
    assert result.action == "REVISAR"


def test_relative_decay_alone_is_informational_not_a_review_request(
    policy: SellRulesPolicy,
) -> None:
    """relative_decay is a comparative signal, never company deterioration
    -- alone, it must never inflate the REVISAR ("needs your decision")
    surface. ACOMPANHAR keeps it visible without asking for action."""
    result = evaluate_sell_rules(
        _ctx(score_percentile=10.0, universe_size=50, universe_scope="reduced"),
        policy,
    )
    assert result.triggered_rules == ("relative_decay",)
    assert result.action == "ACOMPANHAR"


def test_relative_decay_does_not_escalate_an_actionable_rule(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            target_upside=-15.0,
            score_percentile=10.0,
            universe_size=50,
            universe_scope="reduced",
        ),
        policy,
    )
    assert result.triggered_rules == ("valuation_stretch", "relative_decay")
    assert result.action == "TRIM"


def test_no_rules_triggered_holds(policy: SellRulesPolicy) -> None:
    result = evaluate_sell_rules(_ctx(), policy)
    assert result.triggered_rules == ()
    assert result.action == "HOLD"


# --- gating de confiança sobrepõe qualquer contagem de regras ------------


def test_low_score_coverage_gates_to_revisar_even_with_rules_triggered(
    policy: SellRulesPolicy,
) -> None:
    result = evaluate_sell_rules(
        _ctx(
            altman_z=0.1,
            target_upside=-20.0,
            score_coverage=10.0,
        ),
        policy,
    )
    assert result.action == "REVISAR"
    assert len(result.triggered_rules) >= 2


def test_low_confidence_gates_to_revisar(policy: SellRulesPolicy) -> None:
    result = evaluate_sell_rules(_ctx(altman_z=0.1, confidence_score=10.0), policy)
    assert result.action == "REVISAR"


def test_missing_coverage_or_confidence_gates_to_revisar(
    policy: SellRulesPolicy,
) -> None:
    ctx = SellRuleContext(
        symbol="TEST",
        sector="Consumer Cyclical",
        current={},
    )
    result = evaluate_sell_rules(ctx, policy)
    assert result.action == "REVISAR"


def test_all_rule_names_are_covered() -> None:
    assert set(RULE_NAMES) == {
        "distress",
        "valuation_stretch",
        "fundamental_decay",
        "relative_decay",
    }


# --- score_percentiles: escopo reduzido vs. amplo -------------------------


def test_score_percentiles_broad_scope_when_universe_origin_present() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "Investment Score": [90, 50, 10],
            "Score Coverage": [90, 90, 90],
            "Confidence Score": [90, 90, 90],
            "origin": ["portfolio", "watchlist", "universe"],
        }
    )
    policy = load_sell_rules_policy(Path("config/sell_rules.yaml"))
    percentiles, size, scope = score_percentiles(frame, policy)
    assert scope == "broad"
    assert size == 3
    assert percentiles["AAA"] > percentiles["CCC"]


def test_score_percentiles_reduced_scope_without_universe_origin() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Investment Score": [90, 50],
            "Score Coverage": [90, 90],
            "Confidence Score": [90, 90],
            "origin": ["portfolio", "watchlist"],
        }
    )
    policy = load_sell_rules_policy(Path("config/sell_rules.yaml"))
    _, _, scope = score_percentiles(frame, policy)
    assert scope == "reduced"


def test_score_percentiles_excludes_rows_below_confidence_gate() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Investment Score": [90, 50],
            "Score Coverage": [90, 10],
            "Confidence Score": [90, 10],
            "origin": ["portfolio", "portfolio"],
        }
    )
    policy = load_sell_rules_policy(Path("config/sell_rules.yaml"))
    percentiles, size, _ = score_percentiles(frame, policy)
    assert size == 1
    assert "BBB" not in percentiles

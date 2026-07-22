"""
Governance guard for financially material configuration.

The Constitution (Article 5 — configuration governance, Article 6 — regression
discipline) and AGENTS.md forbid silently changing scoring weights, thresholds
or Deal Breakers. Until now no test pinned the *actual* values shipped in
`config/`, so any edit to a governed file passed CI unnoticed.

This test locks the current governed values. If a weight or threshold changes,
this test fails on purpose: the change must be deliberate, explained and
re-baselined here in the same commit, exactly as the Constitution requires.

It asserts current behaviour only — it does not endorse the values as correct.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"


def _load_json(name: str) -> dict:
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def test_model_yaml_factor_weights_are_pinned() -> None:
    """factor_weights in model.yaml is the weight vector the pipeline uses."""
    model = _load_yaml("model.yaml")
    weights = model["factor_weights"]

    assert weights == {
        "business": 0.35,
        "valuation": 0.30,
        "financial": 0.15,
        "timing": 0.20,
    }
    assert sum(weights.values()) == pytest.approx(1.0)
    assert model["confidence"] == {"missing_required_cap": 59}


def test_data_quality_policy_is_pinned() -> None:
    policy = _load_yaml("data_quality.yaml")
    assert policy == {
        "version": "1",
        "source_quality": {
            "missing_score": 0,
            "unknown_score": 50,
            "patterns": {
                "SEC EDGAR": 95,
                "Yahoo Finance": 80,
                "yahoo": 80,
            },
        },
        "freshness": {
            "fresh_days": 7,
            "acceptable_days": 35,
            "fresh_score": 100,
            "acceptable_score": 70,
            "stale_score": 0,
        },
        "not_applicable_by_sector": {
            "Financial Services": [
                "altman_z", "current_ratio", "current_liquidity"
            ],
            "Banks": ["altman_z", "current_ratio", "current_liquidity"],
            "Insurance": ["altman_z", "current_ratio", "current_liquidity"],
            "Utilities": ["altman_z"],
            "Biotechnology": [
                "altman_z", "f_score_annual", "net_debt_ebitda"
            ],
            "Software": ["current_ratio", "current_liquidity"],
            "Tobacco": ["current_ratio", "current_liquidity"],
        },
    }


def test_provider_operational_policy_is_pinned() -> None:
    settings = _load_json("settings.json")
    assert settings["provider_timeout_seconds"] == 30
    assert settings["provider_max_retries"] == 2
    assert settings["provider_backoff_seconds"] == pytest.approx(0.5)
    assert settings["provider_rate_limit_per_second"] == pytest.approx(2)
    assert settings["provider_critical_fields"] == [
        "total_debt",
        "total_cash",
        "ebitda",
        "free_cashflow",
        "current_ratio",
        "roe",
    ]
    assert settings["raw_snapshot_path"] == "data/raw_snapshots"
    assert settings["sec_secondary_enabled"] is True
    assert settings["sec_public_float_alignment_days"] == 45
    assert settings["sec_public_float_rate_limit_per_second"] == 2
    assert settings["sec_public_float_audit_report_path"].endswith(
        "sec_public_float_audit.json"
    )
    assert settings["massive_secondary_enabled"] is True
    assert settings["massive_ticker_details_cache_path"].endswith(
        "massive_ticker_details.json"
    )
    assert settings["massive_ticker_details_cache_days"] == 7
    assert settings["massive_prefetch_batch_size"] == 5
    assert settings["massive_prefetch_rate_limit_per_second"] == pytest.approx(
        0.075
    )
    assert settings["massive_request_limit_per_minute"] == 5
    assert settings["massive_float_cache_path"].endswith("massive_float.json")
    assert settings["massive_float_cache_days"] == 7
    assert settings["massive_float_page_limit"] == 1000
    assert settings["massive_float_max_pages_per_run"] == 100
    assert settings["massive_prefetch_universe_path"].endswith(
        "research_universe_report_market.json"
    )
    assert settings["fmp_secondary_enabled"] is True
    assert settings["fmp_automatic_prefetch_enabled"] is False
    assert settings["fmp_daily_call_limit"] == 250
    assert settings["fmp_prefetch_reserve_calls"] == 25
    assert settings["fmp_prefetch_threshold"] == 100
    assert settings["fmp_prefetch_universe_path"].endswith(
        "research_universe_report_market.json"
    )
    assert settings["fmp_market_batch_size"] == 100
    assert settings["fmp_float_page_size"] == 1000
    assert settings["fmp_float_max_pages"] == 100
    assert settings["provider_secrets_path"] == "config/provider_secrets.json"


def test_deal_breakers_thresholds_are_pinned() -> None:
    """
    Isenções setoriais reconciliadas com config/sell_rules.yaml (motor de
    venda): mesmas listas de setor nos dois motores, para uma holding não
    receber Risk Penalty no score e ficar isenta de distress no motor de
    venda por critérios que deveriam ser o mesmo julgamento de risco.
    Biotechnology (P&D pré-receita: EBITDA/F-Score não representam a
    empresa) e Tobacco (conversão de caixa alta, capital de giro negativo
    estrutural) foram adicionados aos dois motores na mesma sessão.
    """
    rules = _load_json("deal_breakers.json")

    assert rules["f_score_annual_min"] == 4
    assert rules["altman_z_min"] == pytest.approx(1.8)
    assert rules["net_debt_ebitda_max"] == pytest.approx(4.0)
    assert rules["current_liquidity_min"] == pytest.approx(1.0)
    assert rules["short_float_max"] == pytest.approx(20.0)
    assert rules["altman_z_exempt_sectors"] == [
        "Utilities",
        "Financial Services",
        "Banks",
        "Insurance",
        "Biotechnology",
    ]
    assert rules["current_liquidity_exempt_sectors"] == ["Software", "Tobacco"]
    assert rules["net_debt_ebitda_exempt_sectors"] == ["Biotechnology"]
    assert rules["f_score_exempt_sectors"] == ["Biotechnology"]


def test_feature_store_factor_weight_blocks_sum_to_one() -> None:
    """Each factor's per-feature weights must form a proper convex blend."""
    features = _load_yaml("features.yaml")

    for factor in ("business", "valuation", "financial", "timing"):
        block = features[factor]
        total = sum(float(cfg["weight"]) for cfg in block.values())
        assert total == pytest.approx(1.0), f"{factor} weights sum to {total}"


def test_feature_store_percentile_scopes_are_governed() -> None:
    features = _load_yaml("features.yaml")
    sector_features = {
        "business": {
            "roic", "roe", "gross_margin", "operating_margin", "net_margin",
            "debt_to_equity", "current_ratio", "interest_coverage",
        },
        "valuation": set(features["valuation"]),
        "financial": set(features["financial"]),
    }
    for factor, names in sector_features.items():
        for name in names:
            assert features[factor][name]["percentile_scope"] == "sector"
    assert features["business"]["f_score_annual"].get(
        "percentile_scope", "market"
    ) == "market"
    assert all(
        config.get("percentile_scope", "market") == "market"
        for config in features["timing"].values()
    )


def test_model_portfolio_constraints_are_pinned() -> None:
    policy = _load_yaml("model_portfolio.yaml")
    assert policy == {
        "name": "Atlas Equal-Weight Research Portfolio",
        "target_positions": 20,
        "weighting_method": "equal",
        "max_position_weight": 0.05,
        "max_sector_weight": 0.20,
        "cash_weight": 0.0,
        "max_initial_turnover": 1.0,
    }


def test_exempt_sectors_match_between_deal_breakers_and_sell_rules() -> None:
    """scoring/investment.py (deal_breakers.json) and portfolio/sell_rules.py
    (sell_rules.yaml) maintain two independent, hand-edited exempt-sector
    lists for the same underlying risk checks -- STATUS.md documents this as
    a known drift risk with no automatic equivalence guard. This test is
    that guard: it fails if either governed file's exempt-sector list is
    edited without updating its counterpart.

    Key-name mapping (the two surfaces name the same concept differently):
    altman_z <-> altman_z, interest_coverage -> altman_z (sell_rules folds
    both solvency checks into the same exemption), net_debt_ebitda <->
    net_debt_ebitda, current_liquidity <-> current_ratio, f_score <-> f_score.
    """
    deal_breakers = _load_json("deal_breakers.json")
    sell_rules = _load_yaml("sell_rules.yaml")["distress"]

    assert (
        deal_breakers["altman_z_exempt_sectors"]
        == sell_rules["altman_z_exempt_sectors"]
        == sell_rules["interest_coverage_exempt_sectors"]
    )
    assert (
        deal_breakers["current_liquidity_exempt_sectors"]
        == sell_rules["current_ratio_exempt_sectors"]
    )
    assert (
        deal_breakers["net_debt_ebitda_exempt_sectors"]
        == sell_rules["net_debt_ebitda_exempt_sectors"]
    )
    assert (
        deal_breakers["f_score_exempt_sectors"]
        == sell_rules["f_score_exempt_sectors"]
    )


def test_sell_rules_python_defaults_match_deal_breakers() -> None:
    """portfolio/sell_rules.py's DEFAULT_* fallbacks only apply when
    sell_rules.yaml omits a key -- today it never does, so a stale default
    (found and fixed alongside this test: DEFAULT_SOLVENCY_EXEMPT_SECTORS
    was missing "Biotechnology", DEFAULT_LIQUIDITY_EXEMPT_SECTORS was
    missing "Tobacco") silently does nothing until the day someone trims
    sell_rules.yaml and the fallback quietly diverges from
    deal_breakers.json. This locks the fallback to the governed source.
    """
    from portfolio.sell_rules import (
        DEFAULT_F_SCORE_EXEMPT_SECTORS,
        DEFAULT_LIQUIDITY_EXEMPT_SECTORS,
        DEFAULT_NET_DEBT_EBITDA_EXEMPT_SECTORS,
        DEFAULT_SOLVENCY_EXEMPT_SECTORS,
    )

    deal_breakers = _load_json("deal_breakers.json")

    assert (
        list(DEFAULT_SOLVENCY_EXEMPT_SECTORS)
        == deal_breakers["altman_z_exempt_sectors"]
    )
    assert (
        list(DEFAULT_LIQUIDITY_EXEMPT_SECTORS)
        == deal_breakers["current_liquidity_exempt_sectors"]
    )
    assert (
        list(DEFAULT_NET_DEBT_EBITDA_EXEMPT_SECTORS)
        == deal_breakers["net_debt_ebitda_exempt_sectors"]
    )
    assert (
        list(DEFAULT_F_SCORE_EXEMPT_SECTORS)
        == deal_breakers["f_score_exempt_sectors"]
    )

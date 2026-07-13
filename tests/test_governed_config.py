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


def test_deal_breakers_thresholds_are_pinned() -> None:
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
    ]
    assert rules["current_liquidity_exempt_sectors"] == ["Software"]


def test_feature_store_factor_weight_blocks_sum_to_one() -> None:
    """Each factor's per-feature weights must form a proper convex blend."""
    features = _load_yaml("features.yaml")

    for factor in ("business", "valuation", "financial", "timing"):
        block = features[factor]
        total = sum(float(cfg["weight"]) for cfg in block.values())
        assert total == pytest.approx(1.0), f"{factor} weights sum to {total}"

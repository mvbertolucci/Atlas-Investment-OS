from __future__ import annotations

from pathlib import Path

import pandas as pd

from reports.atlas_report.ticker_detail import anchor_id, build_ticker_detail


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "gross_margin": 60,
                "roic": 0.25,
                "pe": 15,
                "debt_to_equity": 0.3,
                "rsi_14": 80,
            },
            {
                "symbol": "BBB",
                "gross_margin": 20,
                "roic": 0.05,
                "pe": 40,
                "debt_to_equity": 2.0,
                "rsi_14": 50,
            },
            {
                "symbol": "CCC",
                "gross_margin": 40,
                "roic": 0.15,
                "pe": 25,
                "debt_to_equity": 1.0,
                "rsi_14": 30,
            },
        ]
    )


def _build(**overrides):
    defaults = dict(
        symbol="AAA",
        name="Alpha",
        sector="Tech",
        origin="portfolio",
        action="HOLD",
        action_engine="portfolio.sell_rules",
        action_reason="ok",
        score=80.0,
        score_delta=1.0,
        coverage=90.0,
        current={"roic": 0.25},
        df=_df(),
        rule_results=(),
        holding=None,
        score_history=pd.DataFrame(),
        features_path=Path("config/features.yaml"),
        model_path=Path("config/model.yaml"),
        as_of=pd.Timestamp("2026-07-14"),
    )
    defaults.update(overrides)
    return build_ticker_detail(**defaults)


def test_anchor_id_matches_symbol() -> None:
    assert anchor_id("aaa") == "ticker-AAA"


def test_feature_details_carry_formula_and_no_external_link_fields() -> None:
    detail = _build()
    assert detail.positive_features or detail.negative_features
    for item in (*detail.positive_features, *detail.negative_features):
        assert item.formula
        assert not hasattr(item, "quote_url")
        assert not hasattr(item, "financials_url")


def test_unknown_column_formula_is_pending_not_invented() -> None:
    detail = _build()
    known_columns = {"roic", "gross_margin", "pe", "debt_to_equity", "rsi_14"}
    for item in (*detail.positive_features, *detail.negative_features):
        if item.column not in known_columns:
            assert item.formula == "fórmula: pendente"


def test_sell_rules_available_only_when_rule_results_present() -> None:
    without = _build(rule_results=())
    assert without.sell_rules_available is False

    with_rules = _build(
        rule_results=(
            {"name": "distress", "status": "triggered", "message": "Altman Z baixo"},
        )
    )
    assert with_rules.sell_rules_available is True
    assert with_rules.sell_rules[0].name == "distress"
    assert with_rules.sell_rules[0].status_label == "disparou"
    assert "sell_rules.py::_distress" in with_rules.sell_rules[0].definition


def test_thesis_absent_when_holding_has_no_thesis() -> None:
    detail = _build(holding={"symbol": "AAA", "thesis": ""})
    assert detail.thesis is None


def test_thesis_present_with_age_and_attention_from_fundamental_decay() -> None:
    detail = _build(
        holding={
            "symbol": "AAA",
            "thesis": "Tese de longo prazo em software.",
            "entry_date": "2025-01-14",
            "thesis_updated_at": "2025-01-14",
        },
        rule_results=(
            {
                "name": "fundamental_decay",
                "status": "triggered",
                "message": "F-Score caiu 3 pontos.",
            },
        ),
    )
    assert detail.thesis is not None
    assert detail.thesis.text == "Tese de longo prazo em software."
    assert detail.thesis.age_months is not None
    assert detail.thesis.age_months > 0
    assert detail.thesis.attention == "F-Score caiu 3 pontos."


def test_history_marks_unavailable_columns_without_inventing_data() -> None:
    """
    rsi_14/gross_margin nunca foram gravados no schema de snapshots
    (STATUS.md secao 4) -- mesmo aparecendo como contribuição do score,
    o histórico deles tem que ficar marcado indisponível, nunca inventado.
    """
    detail = _build(
        score_history=pd.DataFrame(
            {
                "snapshot_date": ["2026-06-01"],
                "symbol": ["AAA"],
                "investment_score": [70.0],
            }
        )
    )
    by_column = {history.column: history for history in detail.histories}
    assert by_column["investment_score"].available is True
    assert by_column["investment_score"].points == (("2026-06-01", 70.0),)
    for schema_unavailable in ("rsi_14", "gross_margin"):
        if schema_unavailable in by_column:
            assert by_column[schema_unavailable].available is False
            assert by_column[schema_unavailable].points == ()

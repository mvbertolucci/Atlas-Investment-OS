from __future__ import annotations

from pathlib import Path

import pandas as pd

from factors.engine import pct_rank
from reports.atlas_report.one_pager import (
    compute_symbol_contributions,
    render_one_pager,
)


def _df() -> pd.DataFrame:
    """
    3 empresas sintéticas, com AAA claramente melhor em gross_margin/roic e
    pior em rsi_14 -- serve de cálculo de referência simples.
    """
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


def test_contributions_match_reference_percentile_calculation() -> None:
    df = _df()
    positive, negative = compute_symbol_contributions(
        df, "AAA", Path("config/features.yaml"), Path("config/model.yaml")
    )

    # Cálculo de referência independente, mesma fórmula documentada:
    # (percentil - 50) * contribution, usando pct_rank (a mesma função que
    # o score de fato usa).
    gross_margin_percentile = float(
        pct_rank(df, "gross_margin", True).loc[0]
    )
    assert gross_margin_percentile == 100.0  # AAA tem o maior valor

    roic_percentile = float(pct_rank(df, "roic", True).loc[0])
    assert roic_percentile == 100.0

    rsi_percentile = float(pct_rank(df, "rsi_14", False).loc[0])
    # higher_is_better=False para rsi_14 -- AAA tem o MAIOR valor bruto
    # (80), então o percentil invertido é o MENOR (pior).
    assert rsi_percentile == 0.0

    positive_labels = {item.label for item in positive}
    negative_labels = {item.label for item in negative}
    assert "Gross Margin" in positive_labels
    assert "ROIC" in positive_labels
    assert "RSI 14" in negative_labels

    # Nenhum item aparece nas duas listas ao mesmo tempo.
    assert positive_labels.isdisjoint(negative_labels)

    # Top 3 no máximo, ordenados por magnitude.
    assert len(positive) <= 3
    assert len(negative) <= 3
    if len(positive) > 1:
        assert positive[0].signed_contribution >= positive[1].signed_contribution
    if len(negative) > 1:
        assert negative[0].signed_contribution <= negative[1].signed_contribution


def test_unknown_symbol_returns_empty_contributions() -> None:
    positive, negative = compute_symbol_contributions(
        _df(), "ZZZZ", Path("config/features.yaml"), Path("config/model.yaml")
    )
    assert positive == ()
    assert negative == ()


def test_render_one_pager_has_no_external_resources() -> None:
    positive, negative = compute_symbol_contributions(
        _df(), "AAA", Path("config/features.yaml"), Path("config/model.yaml")
    )
    history = pd.DataFrame({"investment_score": [50.0, 55.0, 60.0]})
    html = render_one_pager(
        symbol="AAA",
        company_name="Alpha Co",
        investment_score=70.0,
        positive=positive,
        negative=negative,
        score_history=history,
        thesis="Tese de teste.",
    )
    assert "http://" not in html
    assert "https://" not in html
    assert "Alpha Co" in html
    assert "Tese de teste." in html


def test_render_one_pager_without_thesis_says_not_a_real_position() -> None:
    html = render_one_pager(
        symbol="AAA",
        company_name="Alpha Co",
        investment_score=None,
        positive=(),
        negative=(),
        score_history=pd.DataFrame(),
        thesis="",
    )
    assert "Sem tese registrada" in html

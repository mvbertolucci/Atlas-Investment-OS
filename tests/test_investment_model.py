from __future__ import annotations

import pandas as pd
import pytest

from models.investment_model import apply_recommendation, classify


def test_score_band_is_descriptive_not_a_buy_verdict() -> None:
    # Nenhuma faixa usa estrela ou verbo de compra/hold -- só descreve o
    # nível do Investment Score. O veredicto de compra é do `Decision`.
    labels = [classify(s) for s in (95, 85, 75, 65, 40)]
    assert labels == [
        "Elite (≥90)",
        "Alto (80–89)",
        "Bom (70–79)",
        "Médio (60–69)",
        "Baixo (<60)",
    ]
    for label in labels:
        assert "★" not in label
        for verb in ("Comprar", "Acumular", "Manter", "Evitar"):
            assert verb not in label


def test_boundaries_match_score_tiers() -> None:
    assert classify(90) == "Elite (≥90)"
    assert classify(89.9) == "Alto (80–89)"
    assert classify(70) == "Bom (70–79)"
    assert classify(59.9) == "Baixo (<60)"


def test_apply_recommendation_creates_score_band_column() -> None:
    df = pd.DataFrame({"symbol": ["AAA", "BBB"], "Investment Score": [82.0, 55.0]})
    result = apply_recommendation(df)
    assert "Score Band" in result.columns
    assert "Recommendation" not in result.columns  # coluna de compra aposentada
    assert result.loc[0, "Score Band"] == "Alto (80–89)"
    assert result.loc[1, "Score Band"] == "Baixo (<60)"


def test_apply_recommendation_requires_investment_score() -> None:
    with pytest.raises(ValueError):
        apply_recommendation(pd.DataFrame({"symbol": ["AAA"]}))

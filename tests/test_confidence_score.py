"""
Trava a fonte unica do Confidence Score (PR-017.6).

Ate o PR-017.5, analytics/validator.py::add_confidence_score computava um
"Confidence Score" (% de CORE_METRICS disponiveis) ANTES do scoring, que era
sempre sobrescrito por "Model Confidence" (media das confidences dos fatores)
em factors/engine.py. Codigo morto + dupla definicao confusa. Removido.

Estes testes garantem que o factor engine e a fonte autoritativa do
Confidence Score e que ele independe de qualquer valor pre-existente.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.mapper import normalize_columns
from scoring.investment import score_dataframe


CONFIG = Path(__file__).resolve().parent.parent / "config"

RAW_COLUMNS = [
    "pe", "forward_pe", "ev_ebitda", "ev_ebit", "peg", "pb", "roe", "roa",
    "gross_margin", "operating_margin", "net_margin", "debt_to_equity",
    "current_ratio", "net_debt_ebitda", "rsi_14", "momentum_3m", "momentum_6m",
    "momentum_12m", "distance_52w_high", "target_upside", "shareholder_yield",
    "fcf_yield", "roic", "f_score_annual", "altman_z", "interest_coverage",
    "short_float", "price", "market_cap", "enterprise_value", "ebit",
    "total_debt", "total_cash", "ebitda",
]


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    df = pd.DataFrame({c: rng.uniform(1, 50, 6) for c in RAW_COLUMNS})
    df["symbol"] = [f"S{i}" for i in range(6)]
    # disponibilidade parcial -> Model Confidence nao trivial
    df.loc[0, ["roe", "roa", "f_score_annual", "altman_z"]] = np.nan
    df.loc[2, ["momentum_12m", "rsi_14"]] = np.nan
    return normalize_columns(df)


def _score(df: pd.DataFrame) -> pd.DataFrame:
    return score_dataframe(df, CONFIG / "model.yaml", CONFIG / "deal_breakers.json")


def test_confidence_score_equals_model_confidence() -> None:
    """O Confidence Score final e exatamente o Model Confidence do engine."""

    scored = _score(_frame())
    assert (scored["Confidence Score"] == scored["Model Confidence"]).all()


def test_confidence_score_ignores_preexisting_value() -> None:
    """
    Um Confidence Score pre-existente (ex.: de uma etapa anterior) e
    sobrescrito pelo engine -- prova que nao ha mais dupla definicao com
    ordem de execucao decidindo o vencedor.
    """

    clean = _score(_frame())

    polluted_input = _frame()
    polluted_input["Confidence Score"] = 12.34  # valor absurdo pre-scoring
    polluted = _score(polluted_input)

    assert np.allclose(
        clean.sort_values("symbol")["Confidence Score"].to_numpy(),
        polluted.sort_values("symbol")["Confidence Score"].to_numpy(),
    )
    assert not (polluted["Confidence Score"] == 12.34).any()

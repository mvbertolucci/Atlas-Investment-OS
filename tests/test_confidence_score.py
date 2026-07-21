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
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from analytics.mapper import normalize_columns
from scoring.investment import score_dataframe
from factors.engine import score_all_factors


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


def test_data_coverage_uses_effective_factor_contribution(
    tmp_path: Path,
) -> None:
    features = tmp_path / "features.yaml"
    features.write_text(
        "business:\n"
        "  roe: {weight: 1.0, higher_is_better: true, required: false}\n"
        "timing:\n"
        "  momentum_3m: {weight: 1.0, higher_is_better: true, required: true}\n",
        encoding="utf-8",
    )
    model = tmp_path / "model.yaml"
    model.write_text(
        "factor_weights: {business: 0.75, timing: 0.25}\n"
        "confidence: {missing_required_cap: 59}\n",
        encoding="utf-8",
    )
    scored = score_all_factors(
        pd.DataFrame([{"symbol": "AAA", "roe": 20.0}]),
        features,
        model,
    )

    assert scored.loc[0, "Data Coverage"] == 75.0
    assert scored.loc[0, "Score Coverage"] == 75.0
    assert scored.loc[0, "Missing Required Features"] == "timing:momentum_3m"
    assert scored.loc[0, "Required Features Complete"] == False  # noqa: E712
    assert scored.loc[0, "Model Confidence"] == 59.0
    assert scored.loc[0, "Confidence Score"] == 59.0


def test_source_quality_and_freshness_are_independent_metrics() -> None:
    frame = _frame().iloc[:3].copy()
    frame["source"] = ["Yahoo Finance", "Unknown Vendor", None]
    frame["as_of"] = [
        "2026-07-16T00:00:00Z",
        "2026-06-25T00:00:00Z",
        None,
    ]
    scored = score_dataframe(
        frame,
        CONFIG / "model.yaml",
        CONFIG / "deal_breakers.json",
        quality_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )

    by_symbol = scored.set_index("symbol")
    assert by_symbol["Source Quality"].to_dict() == {
        "S0": 80.0,
        "S1": 50.0,
        "S2": 0.0,
    }
    assert by_symbol["Data Freshness"].to_dict() == {
        "S0": 100.0,
        "S1": 70.0,
        "S2": 0.0,
    }
    assert not scored["Source Quality"].equals(scored["Data Coverage"])
    assert not scored["Data Freshness"].equals(scored["Model Confidence"])


def test_not_applicable_feature_leaves_coverage_denominator_and_required_gate(
    tmp_path: Path,
) -> None:
    features = tmp_path / "features.yaml"
    features.write_text(
        "business:\n"
        "  roe: {weight: 0.5, higher_is_better: true, required: true}\n"
        "  altman_z: {weight: 0.5, higher_is_better: true, required: true}\n",
        encoding="utf-8",
    )
    model = tmp_path / "model.yaml"
    model.write_text("factor_weights: {business: 1.0}\n", encoding="utf-8")
    frame = pd.DataFrame(
        [
            {
                "symbol": "BANK",
                "roe": 12.0,
                "altman_z": None,
                "field_evidence": {
                    "roe": {"status": "present"},
                    "altman_z": {"status": "not_applicable"},
                },
            }
        ]
    )

    scored = score_all_factors(frame, features, model)

    assert scored.loc[0, "Data Coverage"] == 100.0
    assert scored.loc[0, "Required Features Complete"] == True  # noqa: E712
    assert scored.loc[0, "Missing Required Features"] == "Nenhum"


def test_stale_required_feature_does_not_cap_confidence(
    tmp_path: Path,
) -> None:
    """
    Um valor `stale` (mais velho que a janela de frescor) e uma observacao
    real, so desatualizada -- diferente de `missing`/`unavailable`/`invalid`,
    que sao ausencia genuina. Antes desta correcao, `metric_available` tratava
    os dois casos como identicos no gate de required-feature, travando Model
    Confidence em 59 (abaixo do confidence_gate de 60 em sell_rules.yaml)
    sempre que um required ficasse so desatualizado -- achado real rodando a
    carteira em 2026-07-20: ROE/Net Margin do Yahoo (fiscal-year-end, so
    atualiza a cada trimestre) ficam `stale` na maior parte de cada janela de
    35 dias, o que travava toda decisao de venda/compra em REVISAR.
    """
    features = tmp_path / "features.yaml"
    features.write_text(
        "business:\n"
        "  roe: {weight: 1.0, higher_is_better: true, required: true}\n"
        "timing:\n"
        "  momentum_3m: {weight: 1.0, higher_is_better: true, required: true}\n",
        encoding="utf-8",
    )
    model = tmp_path / "model.yaml"
    model.write_text(
        "factor_weights: {business: 0.75, timing: 0.25}\n"
        "confidence: {missing_required_cap: 59}\n",
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "roe": 20.0,
                "momentum_3m": 5.0,
                "field_evidence": {
                    "roe": {"status": "stale"},
                    "momentum_3m": {"status": "present"},
                },
            }
        ]
    )

    scored = score_all_factors(frame, features, model)

    # Cobertura continua descontando o campo desatualizado (inalterado).
    assert scored.loc[0, "Data Coverage"] == 25.0
    # Mas o required-gate nao trata "stale" como "ausente": nao ha cap.
    assert scored.loc[0, "Missing Required Features"] == "Nenhum"
    assert scored.loc[0, "Required Features Complete"] == True  # noqa: E712
    assert scored.loc[0, "Model Confidence"] == 25.0
    assert scored.loc[0, "Confidence Score"] == 25.0


def test_missing_required_feature_still_caps_confidence(
    tmp_path: Path,
) -> None:
    """Regressao: uma feature genuinamente ausente (nunca chegou nenhum
    valor, sem field_evidence) continua travando Model Confidence em 59,
    mesmo quando a cobertura sem o cap seria bem maior -- a correcao acima
    so exclui `stale`, nao `missing`/`unavailable`."""
    features = tmp_path / "features.yaml"
    features.write_text(
        "business:\n"
        "  roe: {weight: 1.0, higher_is_better: true, required: false}\n"
        "timing:\n"
        "  momentum_3m: {weight: 1.0, higher_is_better: true, required: true}\n",
        encoding="utf-8",
    )
    model = tmp_path / "model.yaml"
    model.write_text(
        "factor_weights: {business: 0.75, timing: 0.25}\n"
        "confidence: {missing_required_cap: 59}\n",
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        [{"symbol": "AAA", "roe": 20.0, "momentum_3m": None}]
    )

    scored = score_all_factors(frame, features, model)

    # Sem o cap, a cobertura seria 75 (so o business 0.75 disponivel) --
    # prova que o cap de fato reduz o numero, nao so coincide com ele.
    assert scored.loc[0, "Data Coverage"] == 75.0
    assert scored.loc[0, "Missing Required Features"] == "timing:momentum_3m"
    assert scored.loc[0, "Required Features Complete"] == False  # noqa: E712
    assert scored.loc[0, "Model Confidence"] == 59.0

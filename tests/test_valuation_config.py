"""
Trava a unificacao do fator valuation (PR-017.3): config/features.yaml e a
fonte da verdade, e o dict hardcoded VALUATION_FEATURES e apenas fallback.

Antes do PR-017.3 a secao `valuation` do features.yaml era ignorada -- o
scoring vinha de um dict hardcoded com pesos divergentes. Estes testes
impedem a regressao para aquele estado.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from factors.valuation import (
    VALUATION_FEATURES,
    resolve_valuation_features,
    score_valuation,
)


CONFIG = Path(__file__).resolve().parent.parent / "config"
VALUATION_COLUMNS = [
    "pe", "forward_pe", "ev_ebitda", "ev_ebit",
    "peg", "pb", "shareholder_yield", "fcf_yield",
]


def _load_features() -> dict:
    return yaml.safe_load((CONFIG / "features.yaml").read_text(encoding="utf-8"))


def _sample_frame(rows: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {column: rng.uniform(1, 50, rows) for column in VALUATION_COLUMNS}
    )


def test_features_yaml_mirrors_hardcoded_fallback() -> None:
    """
    O fallback hardcoded deve espelhar exatamente a secao valuation do
    features.yaml -- se alguem editar um sem o outro, este teste quebra.
    """

    yaml_cfg = resolve_valuation_features(_load_features())
    fallback = resolve_valuation_features(None)

    assert set(yaml_cfg) == set(fallback), (
        "Features de valuation divergem entre features.yaml e o fallback: "
        f"{set(yaml_cfg) ^ set(fallback)}"
    )
    for name in fallback:
        assert yaml_cfg[name]["weight"] == pytest.approx(fallback[name]["weight"]), (
            f"Peso de '{name}' diverge entre features.yaml e fallback."
        )
        assert yaml_cfg[name]["higher"] == fallback[name]["higher"], (
            f"Direcao (higher) de '{name}' diverge entre features.yaml e fallback."
        )


def test_features_yaml_actually_drives_scoring() -> None:
    """
    Editar um peso no features.yaml precisa mudar o score de valuation --
    prova que o config e a fonte da verdade, nao mais o dict hardcoded.
    """

    df = _sample_frame()

    base_score, _, _ = score_valuation(df, _load_features())

    tuned = _load_features()
    # Zera todos os pesos menos pe -> valuation vira o ranking puro de pe.
    for name, cfg in tuned["valuation"].items():
        cfg["weight"] = 1.0 if name == "pe" else 0.0

    tuned_score, _, _ = score_valuation(df, tuned)

    assert not np.allclose(base_score.to_numpy(), tuned_score.to_numpy()), (
        "Mudar os pesos em features.yaml nao alterou o score de valuation: "
        "o config nao esta dirigindo o fator."
    )


def test_fallback_used_when_yaml_section_absent() -> None:
    """Sem a secao valuation, score_valuation cai para o fallback (nao quebra)."""

    df = _sample_frame()

    from_fallback, _, _ = score_valuation(df, {"business": {}})
    from_none, _, _ = score_valuation(df, None)

    assert np.allclose(from_fallback.to_numpy(), from_none.to_numpy())


def test_resolve_accepts_both_higher_keys() -> None:
    """Aceita `higher` (dict legado) e `higher_is_better` (features.yaml)."""

    legacy = resolve_valuation_features(
        {"valuation": {"pe": {"weight": 1.0, "higher": False}}}
    )
    yaml_style = resolve_valuation_features(
        {"valuation": {"pe": {"weight": 1.0, "higher_is_better": False}}}
    )

    assert legacy["pe"]["higher"] is False
    assert yaml_style["pe"]["higher"] is False

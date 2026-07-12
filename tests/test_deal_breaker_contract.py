"""
Contrato da camada de deal breakers.

Fecha a classe de bug que apareceu duas vezes na linha PR-017.x:
- chave no deal_breakers.json que o codigo nao le (PR-017.1: min_f_score /
  min_current_ratio liam nomes inexistentes);
- regra cuja coluna nunca e produzida (altman_z sem bloco antes do 017.1);
- escala errada, threshold nunca dispara (PR-017.4: short_float em fracao
  vs. threshold em pontos percentuais).

Cada regra do config precisa: (a) ser reconhecida aqui, (b) resolver para
uma coluna que o pipeline produz, e (c) DISPARAR de fato quando violada e
NAO disparar quando cumprida -- exercitando a escala real via
normalize_columns.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analytics.feature_audit import PRODUCIBLE_COLUMNS
from analytics.mapper import normalize_columns
from scoring.investment import apply_deal_breakers


CONFIG = Path(__file__).resolve().parent.parent / "config"
DEAL_BREAKERS_PATH = CONFIG / "deal_breakers.json"


# Para cada chave do deal_breakers.json: a coluna consumida, um valor que
# VIOLA a regra e um que a CUMPRE. Os valores estao na escala CRUA do
# provider (ex.: short_float como fracao), porque o teste passa por
# normalize_columns antes do scoring -- e assim que a escala real e checada.
RULES = {
    "net_debt_ebitda_max": {
        "column": "net_debt_ebitda", "raw": True,
        "breach": {"net_debt_ebitda": 10.0},
        "ok": {"net_debt_ebitda": 1.0},
    },
    "current_liquidity_min": {
        "column": "current_liquidity", "raw": True,
        "breach": {"current_liquidity": 0.3},
        "ok": {"current_liquidity": 2.0},
    },
    "f_score_annual_min": {
        "column": "f_score_annual", "raw": True,
        "breach": {"f_score_annual": 1.0},
        "ok": {"f_score_annual": 8.0},
    },
    "altman_z_min": {
        "column": "altman_z", "raw": True,
        "breach": {"altman_z": 0.5},
        "ok": {"altman_z": 5.0},
    },
    "short_float_max": {
        # short_float entra como fracao (0.40 = 40%) e o mapper converte
        # para percentual; o threshold (20) esta em pontos percentuais.
        "column": "short_float", "raw": False,
        "breach": {"short_float": 0.40},
        "ok": {"short_float": 0.02},
    },
}


def _config_keys() -> set[str]:
    return set(json.loads(DEAL_BREAKERS_PATH.read_text(encoding="utf-8")))


def test_every_config_key_is_covered() -> None:
    """Nenhuma chave do deal_breakers.json pode ficar sem regra mapeada aqui."""

    # Chaves de isencao setorial (PR-017.5) modificam regras existentes, nao
    # sao regras proprias: sufixo _exempt_sectors.
    keys = {k for k in _config_keys() if not k.endswith("_exempt_sectors")}
    unknown = keys - set(RULES)
    assert not unknown, (
        f"Chaves em deal_breakers.json sem contrato/bloco conhecido: {sorted(unknown)}. "
        "Ou o codigo nao le a chave, ou o contrato ficou desatualizado."
    )


@pytest.mark.parametrize("rule_key", list(RULES))
def test_rule_column_is_producible(rule_key: str) -> None:
    """A coluna que cada regra consome precisa ser produzivel pelo pipeline."""

    column = RULES[rule_key]["column"]
    assert column in PRODUCIBLE_COLUMNS, (
        f"Deal breaker '{rule_key}' consome '{column}', que o pipeline nao produz "
        "(regra morta)."
    )


def _score(row: dict) -> pd.DataFrame:
    df = pd.DataFrame([{"Investment Score": 80.0, **row}])
    df = normalize_columns(df)
    return apply_deal_breakers(df, DEAL_BREAKERS_PATH)


@pytest.mark.parametrize("rule_key", list(RULES))
def test_rule_fires_on_breach_and_is_silent_when_ok(rule_key: str) -> None:
    """
    Uma empresa que viola a regra recebe penalidade > 0; uma que a cumpre
    nao recebe penalidade por essa regra. Exercita a escala real ao passar
    por normalize_columns.
    """

    spec = RULES[rule_key]

    breached = _score(spec["breach"])
    assert breached["Risk Penalty"].iloc[0] > 0, (
        f"Deal breaker '{rule_key}' NAO disparou com valor violador "
        f"{spec['breach']} (escala/threshold provavelmente errados)."
    )
    assert breached["Deal Breakers"].iloc[0] != "Nenhum"

    compliant = _score(spec["ok"])
    assert compliant["Risk Penalty"].iloc[0] == 0, (
        f"Deal breaker '{rule_key}' disparou indevidamente com valor OK "
        f"{spec['ok']}."
    )


def test_altman_z_exempt_for_utilities() -> None:
    """
    Utility com Altman Z estruturalmente baixo NAO e punida (isencao setorial
    PR-017.5); uma empresa nao-isenta com o mesmo Z e punida.
    """

    utility = _score({"altman_z": 0.5, "sector": "Utilities", "industry": "Utilities - Regulated Gas"})
    assert "Altman Z" not in utility["Deal Breakers"].iloc[0]

    industrial = _score({"altman_z": 0.5, "sector": "Industrials", "industry": "Railroads"})
    assert "Altman Z" in industrial["Deal Breakers"].iloc[0]


def test_current_liquidity_exempt_for_software() -> None:
    """
    SaaS com current ratio < 1 (deferred revenue) NAO e punido; hardware com
    o mesmo ratio e punido.
    """

    saas = _score({"current_liquidity": 0.7, "sector": "Technology", "industry": "Software - Application"})
    assert "Liquidez" not in saas["Deal Breakers"].iloc[0]

    hardware = _score({"current_liquidity": 0.7, "sector": "Technology", "industry": "Consumer Electronics"})
    assert "Liquidez" in hardware["Deal Breakers"].iloc[0]


def test_exemption_matches_sector_or_industry() -> None:
    """A isencao casa tanto contra sector quanto contra industry (substring)."""

    # 'Financial Services' esta na lista de isencao de altman_z como sector.
    bank = _score({"altman_z": 0.5, "sector": "Financial Services", "industry": "Banks - Regional"})
    assert "Altman Z" not in bank["Deal Breakers"].iloc[0]


def test_short_float_scale_is_percent_after_mapper() -> None:
    """
    Regressao direta do bug PR-017.4: short_float cru (fracao) vira
    percentual no mapper, para o threshold em pontos percentuais funcionar.
    """

    out = normalize_columns(pd.DataFrame([{"short_float": 0.2449}]))
    assert out["short_float"].iloc[0] == pytest.approx(24.49)

"""
Testes de contrato entre a coleta de dados e o modelo de scoring.

Diferente dos demais testes (que exercitam a mecânica com DataFrames
sintéticos já contendo as colunas), estes verificam o contrato real:
provider Yahoo -> enrich_technicals -> compute_fundamentals ->
normalize_columns -> features.

Sem rede: o schema do provider é reproduzido a partir de
providers/yahoo.py::fetch_symbol. Se aquele dicionário mudar, atualize
RAW_PROVIDER_COLUMNS, TECHNICAL_COLUMNS e FUNDAMENTAL_COLUMNS aqui.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analytics.feature_audit import (
    PRODUCIBLE_COLUMNS,
    audit_coverage,
    collect_model_features,
    phantom_weight_summary,
)
from analytics.mapper import normalize_columns


CONFIG = Path(__file__).resolve().parent.parent / "config"
FEATURES_PATH = CONFIG / "features.yaml"
MODEL_PATH = CONFIG / "model.yaml"


# Chaves emitidas por providers/yahoo.py::fetch_symbol (menos "history",
# que run_all descarta antes do scoring).
RAW_PROVIDER_COLUMNS = [
    "symbol", "name", "exchange", "country", "currency", "sector",
    "industry", "as_of", "price", "previous_close", "change_pct", "volume",
    "market_cap", "enterprise_value", "year_high", "year_low", "beta",
    "pe", "forward_pe", "peg", "pb", "ps", "ev_to_ebitda", "ev_to_revenue",
    "roe", "roa", "gross_margin", "operating_margin", "ebitda_margin",
    "net_margin", "debt_to_equity", "current_ratio", "quick_ratio",
    "total_debt", "total_cash", "ebitda", "free_cashflow",
    "operating_cashflow", "dividend_yield", "dividend_rate", "target_price",
    "target_high_price", "target_low_price", "analyst_count", "rating",
    "short_float", "insider_own", "inst_own", "source",
]

# Colunas adicionadas por analytics/indicators.py::enrich_technicals.
TECHNICAL_COLUMNS = [
    "rsi_14", "momentum_3m", "momentum_6m", "momentum_12m",
    "distance_52w_high", "distance_52w_low",
]

# Colunas adicionadas por analytics/fundamentals.py::compute_fundamentals
# (derivadas dos financials brutos do Yahoo; "ev_ebit" nasce depois disso
# no mapper, a partir de "enterprise_value" + "ebit").
FUNDAMENTAL_COLUMNS = [
    "ebit", "roic", "f_score_annual", "altman_z", "interest_coverage",
    "buyback",
]

# PR-017.0 encontrou 5 features fantasmas (roic, f_score_annual,
# interest_coverage x2, ev_ebit). PR-017.1 derivou todos a partir dos
# financials do Yahoo (analytics/fundamentals.py) e do EBIT no mapper, então
# não há mais fantasmas conhecidos. Se um novo feature entrar no config sem
# coluna produzível, adicione aqui e o xfail estrito vai flagar.
KNOWN_PHANTOM_FEATURES: set[tuple[str, str]] = set()

# Estado atual conhecido do peso fantasma. Trava contra regressão: se um
# novo feature sem coluna entrar no modelo, este número sobe e o teste
# quebra.
EXPECTED_PHANTOM_INVESTMENT_SHARE = 0.0
EXPECTED_DEAD_WEIGHT_BY_FACTOR = {
    "business": 0.0,
    "financial": 0.0,
    "valuation": 0.0,
}


def _sample_frame(rows: int = 3) -> pd.DataFrame:
    """
    Simula a saída de coleta+enrich, com todas as colunas produzíveis
    populadas numericamente (cenário de dados completos).
    """

    columns = RAW_PROVIDER_COLUMNS + TECHNICAL_COLUMNS + FUNDAMENTAL_COLUMNS
    records = []
    for index in range(rows):
        record = {column: float(index + 1) for column in columns}
        record["symbol"] = f"SYM{index}"
        record["name"] = f"Company {index}"
        record["sector"] = "Technology"
        record["source"] = "Yahoo Finance"
        record["rating"] = "buy"
        records.append(record)

    return pd.DataFrame(records)


@pytest.fixture
def normalized_frame() -> pd.DataFrame:
    return normalize_columns(_sample_frame())


def test_producible_columns_is_honest(normalized_frame: pd.DataFrame) -> None:
    """
    Toda coluna que o pipeline realmente produz precisa constar em
    PRODUCIBLE_COLUMNS. Protege o contrato de ficar desatualizado quando
    o mapper passar a derivar uma coluna nova.
    """

    produced = set(normalized_frame.columns)
    missing_from_contract = produced - PRODUCIBLE_COLUMNS

    assert not missing_from_contract, (
        "Colunas produzidas pelo pipeline ausentes do contrato "
        f"PRODUCIBLE_COLUMNS: {sorted(missing_from_contract)}"
    )


def _binding_ids() -> list[str]:
    bindings = collect_model_features(FEATURES_PATH, MODEL_PATH)
    return [f"{b.factor}:{b.name}" for b in bindings]


@pytest.mark.parametrize(
    "binding",
    collect_model_features(FEATURES_PATH, MODEL_PATH),
    ids=_binding_ids(),
)
def test_feature_resolves_to_producible_column(
    binding,
    normalized_frame: pd.DataFrame,
) -> None:
    """
    Cada feature ponderado deve consumir uma coluna que o pipeline
    consegue produzir. Features fantasmas conhecidos ficam em xfail
    estrito até serem derivados ou removidos.
    """

    if (binding.factor, binding.name) in KNOWN_PHANTOM_FEATURES:
        pytest.xfail(
            f"Feature fantasma conhecido: {binding.factor}:{binding.name} "
            f"(coluna '{binding.column}' nunca é populada). "
            "Derivar no mapper ou remover do config."
        )

    assert binding.column in normalized_frame.columns, (
        f"Feature {binding.factor}:{binding.name} (peso {binding.weight}) "
        f"consome a coluna '{binding.column}', que o pipeline não produz."
    )


def test_phantom_weight_is_locked(normalized_frame: pd.DataFrame) -> None:
    """
    Trava o peso fantasma atual. Um novo feature sem coluna faria este
    número subir e o teste quebrar antes de o problema chegar em produção.
    """

    coverage = audit_coverage(normalized_frame, FEATURES_PATH, MODEL_PATH)
    summary = phantom_weight_summary(coverage)

    assert summary["phantom_investment_share"] == pytest.approx(
        EXPECTED_PHANTOM_INVESTMENT_SHARE
    ), (
        "Peso fantasma no Investment Score mudou: "
        f"{summary['phantom_investment_share']}% "
        f"(esperado {EXPECTED_PHANTOM_INVESTMENT_SHARE}%)."
    )

    for factor, expected in EXPECTED_DEAD_WEIGHT_BY_FACTOR.items():
        actual = summary["by_factor"].get(factor, {}).get("dead_weight_share", 0.0)
        assert actual == pytest.approx(expected), (
            f"Peso morto do fator '{factor}' mudou: {actual}% "
            f"(esperado {expected}%)."
        )

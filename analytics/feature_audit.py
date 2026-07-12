from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from factors.engine import DEFAULT_FACTORS, get_factor_features, load_yaml
from factors.valuation import VALUATION_FEATURES


# Colunas que o pipeline consegue de fato produzir de ponta a ponta:
# provider Yahoo -> enrich_technicals -> compute_fundamentals ->
# normalize_columns (mapper). Serve como "contrato" de schema para
# detectar features órfãos sem depender de rede. Mantenha em sincronia
# com providers/yahoo.py, analytics/indicators.py,
# analytics/fundamentals.py e analytics/mapper.py.
PRODUCIBLE_COLUMNS: frozenset[str] = frozenset(
    {
        # --- Provider bruto (providers/yahoo.py::fetch_symbol) ---
        "symbol", "name", "exchange", "country", "currency",
        "sector", "industry", "as_of", "price", "previous_close",
        "change_pct", "volume", "market_cap", "enterprise_value",
        "year_high", "year_low", "beta", "pe", "forward_pe", "peg",
        "pb", "ps", "ev_to_ebitda", "ev_to_revenue", "roe", "roa",
        "gross_margin", "operating_margin", "ebitda_margin", "net_margin",
        "debt_to_equity", "current_ratio", "quick_ratio", "total_debt",
        "total_cash", "ebitda", "free_cashflow", "operating_cashflow",
        "dividend_yield", "target_price", "target_high_price",
        "target_low_price", "analyst_count", "rating", "short_float",
        "insider_own", "inst_own", "source",
        # --- Técnicos (analytics/indicators.py::enrich_technicals) ---
        "rsi_14", "momentum_3m", "momentum_6m", "momentum_12m",
        "distance_52w_high", "distance_52w_low",
        # --- Fundamentalistas (analytics/fundamentals.py::compute_fundamentals) ---
        "ebit", "roic", "f_score_annual", "altman_z", "interest_coverage",
        # --- Derivados (analytics/mapper.py::normalize_columns) ---
        "ev_ebitda", "ev_ebit", "net_debt_total_equity", "current_liquidity",
        "consensus_target", "operating_margin_proxy", "net_debt",
        "net_debt_ebitda", "fcf_yield", "shareholder_yield", "target_upside",
    }
)


@dataclass(frozen=True)
class FeatureBinding:
    """
    Liga um feature do modelo à coluna concreta que ele consome.

    factor_weight  : peso do fator no Investment Score (model.yaml).
    weight         : peso do feature dentro do fator.
    contribution   : parcela efetiva do feature no Investment Score,
                     já normalizada (factor_weight * weight / soma dos
                     pesos do fator).
    """

    factor: str
    name: str
    label: str
    column: str
    weight: float
    factor_weight: float
    contribution: float


def _valuation_bindings(factor_weight: float) -> list[FeatureBinding]:
    total = sum(float(v["weight"]) for v in VALUATION_FEATURES.values()) or 1.0

    bindings: list[FeatureBinding] = []
    for column, cfg in VALUATION_FEATURES.items():
        weight = float(cfg.get("weight", 1.0))
        bindings.append(
            FeatureBinding(
                factor="valuation",
                name=column,
                label=str(cfg.get("label", column)),
                column=column,
                weight=weight,
                factor_weight=factor_weight,
                contribution=factor_weight * weight / total,
            )
        )
    return bindings


def _generic_bindings(
    features: dict[str, Any],
    factor: str,
    factor_weight: float,
) -> list[FeatureBinding]:
    selected = get_factor_features(features, factor)
    total = sum(
        float(cfg.get("weight", 1.0))
        for cfg in selected.values()
        if isinstance(cfg, dict)
    ) or 1.0

    bindings: list[FeatureBinding] = []
    for name, cfg in selected.items():
        if not isinstance(cfg, dict):
            continue
        weight = float(cfg.get("weight", 1.0))
        column = str(cfg.get("column") or name)
        bindings.append(
            FeatureBinding(
                factor=factor,
                name=name,
                label=str(cfg.get("label") or name),
                column=column,
                weight=weight,
                factor_weight=factor_weight,
                contribution=factor_weight * weight / total,
            )
        )
    return bindings


def collect_model_features(
    features_path: Path,
    model_path: Path | None = None,
) -> list[FeatureBinding]:
    """
    Enumera todos os features que o modelo pondera, resolvendo cada um
    até a coluna que ele realmente consome.

    Espelha o roteamento de factors/engine.py: valuation vem de
    factors/valuation.py (hardcoded), os demais fatores vêm de
    features.yaml.
    """

    features = load_yaml(features_path)
    model = load_yaml(model_path) if model_path else {}

    factor_weights = model.get("factor_weights", DEFAULT_FACTORS)
    total_factor_weight = sum(float(w) for w in factor_weights.values()) or 1.0

    bindings: list[FeatureBinding] = []
    for factor, raw_weight in factor_weights.items():
        factor = str(factor).lower()
        factor_weight = float(raw_weight) / total_factor_weight

        if factor == "valuation":
            bindings.extend(_valuation_bindings(factor_weight))
        else:
            bindings.extend(
                _generic_bindings(features, factor, factor_weight)
            )

    return bindings


def _coverage_for_column(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0
    if len(df) == 0:
        return 0.0
    values = pd.to_numeric(df[column], errors="coerce")
    return float(values.notna().mean() * 100.0)


def audit_coverage(
    df: pd.DataFrame,
    features_path: Path,
    model_path: Path | None = None,
) -> pd.DataFrame:
    """
    Para cada feature ponderado do modelo, mede a % de linhas em que a
    coluna existe e tem valor numérico. Features com 0% viram score
    neutro (50) via pct_rank, ou seja: peso alocado a uma constante.
    """

    bindings = collect_model_features(features_path, model_path)

    rows: list[dict[str, Any]] = []
    for binding in bindings:
        coverage = _coverage_for_column(df, binding.column)
        producible = binding.column in PRODUCIBLE_COLUMNS

        if coverage <= 0.0:
            status = "PHANTOM" if not producible else "AUSENTE"
        elif coverage < 100.0:
            status = "PARCIAL"
        else:
            status = "OK"

        rows.append(
            {
                "factor": binding.factor,
                "feature": binding.name,
                "label": binding.label,
                "column": binding.column,
                "weight_in_factor": round(binding.weight, 4),
                "contribution": round(binding.contribution, 4),
                "coverage_pct": round(coverage, 1),
                "producible": producible,
                "status": status,
            }
        )

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(
            ["status", "contribution"],
            ascending=[True, False],
        ).reset_index(drop=True)

    return result


def phantom_weight_summary(coverage: pd.DataFrame) -> dict[str, Any]:
    """
    Consolida o peso preso em colunas ausentes (coverage 0%), por fator
    e no total do Investment Score.
    """

    if coverage.empty:
        return {
            "by_factor": {},
            "phantom_investment_share": 0.0,
            "phantom_features": [],
        }

    dead = coverage["coverage_pct"] <= 0.0

    by_factor: dict[str, dict[str, float]] = {}
    for factor, group in coverage.groupby("factor"):
        factor_total = float(group["weight_in_factor"].sum()) or 1.0
        dead_group = group[group["coverage_pct"] <= 0.0]
        dead_weight = float(dead_group["weight_in_factor"].sum())
        by_factor[str(factor)] = {
            "dead_weight_share": round(dead_weight / factor_total * 100.0, 1),
            "dead_features": int(len(dead_group)),
            "total_features": int(len(group)),
        }

    phantom_investment = float(coverage.loc[dead, "contribution"].sum())

    phantom_features = (
        coverage.loc[dead, ["factor", "feature", "column", "contribution"]]
        .to_dict("records")
    )

    return {
        "by_factor": by_factor,
        "phantom_investment_share": round(phantom_investment * 100.0, 1),
        "phantom_features": phantom_features,
    }


def format_coverage_report(
    coverage: pd.DataFrame,
    summary: dict[str, Any] | None = None,
) -> str:
    if coverage.empty:
        return "[FEATURE AUDIT] Nenhum feature de modelo encontrado."

    if summary is None:
        summary = phantom_weight_summary(coverage)

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("AUDITORIA DE COBERTURA DE FEATURES")
    lines.append("=" * 70)

    header = f"{'FATOR':<11}{'FEATURE':<20}{'COLUNA':<24}{'COBERT.':>8}  STATUS"
    lines.append(header)
    lines.append("-" * 70)

    for _, row in coverage.iterrows():
        lines.append(
            f"{row['factor']:<11}"
            f"{str(row['feature'])[:19]:<20}"
            f"{str(row['column'])[:23]:<24}"
            f"{row['coverage_pct']:>7.1f}%  "
            f"{row['status']}"
        )

    lines.append("-" * 70)
    lines.append("PESO MORTO POR FATOR (colunas com 0% de cobertura):")
    for factor, info in summary["by_factor"].items():
        if info["dead_weight_share"] <= 0:
            continue
        lines.append(
            f"  {factor:<11} "
            f"{info['dead_weight_share']:>5.1f}% do peso do fator "
            f"({info['dead_features']}/{info['total_features']} features)"
        )

    lines.append(
        "PESO FANTASMA NO INVESTMENT SCORE: "
        f"{summary['phantom_investment_share']:.1f}% "
        "(alocado a features que sempre valem 50 neutro)"
    )
    lines.append("=" * 70)

    return "\n".join(lines)

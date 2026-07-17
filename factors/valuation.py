from __future__ import annotations

from typing import Any

import pandas as pd

from scoring.reference import ScoringReference, percentile_rank


# Fallback usado quando config/features.yaml nao traz a secao `valuation`
# (ou quando score_valuation e chamado sem `features`). A fonte da verdade
# desde o PR-017.3 e o features.yaml; este dict espelha aquele default e so
# entra em cena para nao deixar o fator sem definicao. Mantenha em sincronia
# com config/features.yaml::valuation (test_valuation_config trava isso).
VALUATION_FEATURES = {
    "pe": {"label": "PE", "weight": 0.20, "higher": False},
    "forward_pe": {"label": "Forward PE", "weight": 0.15, "higher": False},
    "ev_ebitda": {"label": "EV EBITDA", "weight": 0.20, "higher": False},
    "ev_ebit": {"label": "EV EBIT", "weight": 0.15, "higher": False},
    "peg": {"label": "PEG", "weight": 0.10, "higher": False},
    "pb": {"label": "Price Book", "weight": 0.10, "higher": False},
    "shareholder_yield": {"label": "Shareholder Yield", "weight": 0.05, "higher": True},
    "fcf_yield": {"label": "FCF Yield", "weight": 0.05, "higher": True},
}


def resolve_valuation_features(
    features: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Resolve a config do fator valuation, normalizando cada feature para o
    formato interno {label, weight, higher, column}.

    Prioriza a secao `valuation` de config/features.yaml (fonte da verdade);
    cai para VALUATION_FEATURES quando ela nao existe. Aceita tanto a chave
    `higher` (formato legado do dict) quanto `higher_is_better` (features.yaml).
    """

    raw = None
    if features:
        section = features.get("valuation")
        if isinstance(section, dict) and section:
            raw = section

    if raw is None:
        raw = VALUATION_FEATURES

    resolved: dict[str, dict[str, Any]] = {}
    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        higher = cfg.get("higher", cfg.get("higher_is_better", True))
        resolved[name] = {
            "label": str(cfg.get("label") or name),
            "weight": float(cfg.get("weight", 1.0)),
            "higher": bool(higher),
            "column": str(cfg.get("column") or name),
            "percentile_scope": str(
                cfg.get("percentile_scope", "market")
            ).strip().lower(),
        }
    return resolved


def metric_available(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)

    return pd.to_numeric(df[column], errors="coerce").notna()


def score_valuation(
    df: pd.DataFrame,
    features: dict[str, Any] | None = None,
    reference: ScoringReference | None = None,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    valuation_features = resolve_valuation_features(features)

    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight = pd.Series(0.0, index=df.index)
    total_weight = sum(v["weight"] for v in valuation_features.values()) or 1.0

    details = pd.DataFrame(index=df.index)

    for name, cfg in valuation_features.items():
        column = cfg["column"]
        score = percentile_rank(
            df,
            column,
            higher_is_better=cfg["higher"],
            reference=reference,
            scope=cfg["percentile_scope"],
        )
        available = metric_available(df, column)

        weighted_sum += score * cfg["weight"]
        available_weight += available.astype(float) * cfg["weight"]

        safe_label = cfg["label"].replace(" ", "_").replace("/", "_")
        details[f"valuation_{safe_label}_score"] = score.round(1)
        details[f"valuation_{safe_label}_available"] = available

    factor_score = (weighted_sum / total_weight).round(1)
    confidence = (available_weight / total_weight * 100).clip(0, 100).round(1)

    return factor_score, confidence, details

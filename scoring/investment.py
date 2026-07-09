from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from factors.engine import score_all_factors
from models.investment_model import apply_recommendation
from models.opportunity_model import apply_opportunity


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def apply_deal_breakers(
    df: pd.DataFrame,
    deal_breakers_path: Path,
) -> pd.DataFrame:
    result = df.copy()

    rules = load_yaml(deal_breakers_path)

    if not rules:
        return result

    score = pd.to_numeric(
        result.get("Investment Score"),
        errors="coerce",
    ).fillna(50.0)

    penalties = pd.Series(0.0, index=result.index)
    notes = pd.Series("", index=result.index, dtype="object")

    def add_penalty(
        condition: pd.Series,
        penalty: float,
        label: str,
    ) -> None:
        nonlocal penalties, notes

        condition = condition.fillna(False)

        penalties += condition.astype(float) * penalty

        notes = notes.where(
            ~condition,
            notes + label + "; ",
        )

    max_net_debt_ebitda = rules.get(
        "net_debt_ebitda_max",
        rules.get("max_net_debt_ebitda", 4),
    )

    min_current_ratio = rules.get(
        "current_ratio_min",
        rules.get("min_current_ratio", 1),
    )

    min_f_score = rules.get(
        "piotroski_min",
        rules.get("min_piotroski", 4),
    )

    max_short_float = rules.get(
        "short_float_max",
        rules.get("max_short_float", 20),
    )

    if "net_debt_ebitda" in result.columns:
        s = pd.to_numeric(result["net_debt_ebitda"], errors="coerce")
        add_penalty(
            s > float(max_net_debt_ebitda),
            15,
            "Net Debt/EBITDA alto",
        )

    if "current_ratio" in result.columns:
        s = pd.to_numeric(result["current_ratio"], errors="coerce")
        add_penalty(
            s < float(min_current_ratio),
            10,
            "Liquidez corrente baixa",
        )

    if "f_score_annual" in result.columns:
        s = pd.to_numeric(result["f_score_annual"], errors="coerce")
        add_penalty(
            s < float(min_f_score),
            15,
            "Piotroski baixo",
        )

    if "short_float" in result.columns:
        s = pd.to_numeric(result["short_float"], errors="coerce")
        add_penalty(
            s > float(max_short_float),
            10,
            "Short float alto",
        )

    result["Risk Penalty"] = penalties.round(1)

    result["Deal Breakers"] = (
        notes.str.strip("; ")
        .replace("", "Nenhum")
    )

    result["Investment Score"] = (
        score - penalties
    ).clip(
        lower=0,
        upper=100,
    ).round(1)

    return result


def score_dataframe(
    df: pd.DataFrame,
    weights_path: Path,
    deal_breakers_path: Path,
) -> pd.DataFrame:
    """
    Pipeline principal de scoring do Atlas.
    """

    config_dir = weights_path.parent

    features_path = config_dir / "features.yaml"
    model_path = config_dir / "model.yaml"

    if not model_path.exists():
        model_path = weights_path

    result = score_all_factors(
        df,
        features_path=features_path,
        model_path=model_path,
    )

    result = apply_deal_breakers(
        result,
        deal_breakers_path,
    )

    result = apply_opportunity(result)

    result = apply_recommendation(result)

    # Mantemos o ranking principal por Investment Score.
    # Opportunity Score é um modelo complementar nesta versão.
    result = result.sort_values(
        "Investment Score",
        ascending=False,
    ).reset_index(drop=True)

    return result
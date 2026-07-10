from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from decision.engine import apply_decision
from decision.thesis import apply_investment_thesis
from factors.engine import score_all_factors
from models.conviction_model import apply_conviction
from models.investment_model import apply_recommendation
from models.opportunity_model import apply_opportunity


def load_yaml(path: Path) -> dict[str, Any]:
    """
    Carrega um arquivo YAML.

    Retorna um dicionário vazio quando o arquivo não existe
    ou não contém configuração.
    """

    if not path.exists():
        return {}

    data = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    return data or {}


def apply_deal_breakers(
    df: pd.DataFrame,
    deal_breakers_path: Path,
) -> pd.DataFrame:
    """
    Aplica penalidades de risco ao Investment Score.

    As regras são carregadas de deal_breakers.json/YAML.
    """

    result = df.copy()
    rules = load_yaml(deal_breakers_path)

    score = pd.to_numeric(
        result.get(
            "Investment Score",
            pd.Series(50.0, index=result.index),
        ),
        errors="coerce",
    ).fillna(50.0)

    penalties = pd.Series(
        0.0,
        index=result.index,
        dtype="float64",
    )

    notes = pd.Series(
        "",
        index=result.index,
        dtype="object",
    )

    def add_penalty(
        condition: pd.Series,
        penalty: float,
        label: str,
    ) -> None:
        nonlocal penalties, notes

        condition = condition.fillna(False)

        penalties += (
            condition.astype(float)
            * float(penalty)
        )

        notes = notes.where(
            ~condition,
            notes + label + "; ",
        )

    max_net_debt_ebitda = rules.get(
        "net_debt_ebitda_max",
        rules.get(
            "max_net_debt_ebitda",
            4,
        ),
    )

    min_current_ratio = rules.get(
        "current_ratio_min",
        rules.get(
            "min_current_ratio",
            1,
        ),
    )

    min_f_score = rules.get(
        "piotroski_min",
        rules.get(
            "min_piotroski",
            4,
        ),
    )

    max_short_float = rules.get(
        "short_float_max",
        rules.get(
            "max_short_float",
            20,
        ),
    )

    if "net_debt_ebitda" in result.columns:
        values = pd.to_numeric(
            result["net_debt_ebitda"],
            errors="coerce",
        )

        add_penalty(
            values > float(max_net_debt_ebitda),
            15,
            "Net Debt/EBITDA alto",
        )

    liquidity_column = None

    if "current_ratio" in result.columns:
        liquidity_column = "current_ratio"
    elif "current_liquidity" in result.columns:
        liquidity_column = "current_liquidity"

    if liquidity_column is not None:
        values = pd.to_numeric(
            result[liquidity_column],
            errors="coerce",
        )

        add_penalty(
            values < float(min_current_ratio),
            10,
            "Liquidez corrente baixa",
        )

    if "f_score_annual" in result.columns:
        values = pd.to_numeric(
            result["f_score_annual"],
            errors="coerce",
        )

        add_penalty(
            values < float(min_f_score),
            15,
            "Piotroski baixo",
        )

    if "short_float" in result.columns:
        values = pd.to_numeric(
            result["short_float"],
            errors="coerce",
        )

        add_penalty(
            values > float(max_short_float),
            10,
            "Short float alto",
        )

    result["Risk Penalty"] = penalties.round(1)

    result["Deal Breakers"] = (
        notes
        .str.strip("; ")
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
    Executa o pipeline de decisão do Atlas.

    Ordem:

    1. Factor Engine
    2. Deal Breakers
    3. Opportunity Engine
    4. Conviction Engine
    5. Decision Engine
    6. Investment Thesis Engine
    7. Recommendation legada
    8. Ordenação final
    """

    config_dir = weights_path.parent

    features_path = config_dir / "features.yaml"
    model_path = config_dir / "model.yaml"

    if not features_path.exists():
        raise FileNotFoundError(
            f"Feature Store não encontrada: {features_path}"
        )

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
    result = apply_conviction(result)
    result = apply_decision(result)
    result = apply_investment_thesis(result)

    # Mantida por compatibilidade com relatórios e integrações existentes.
    result = apply_recommendation(result)

    sort_columns = [
        column
        for column in [
            "Decision Priority",
            "Opportunity Score",
            "Conviction Score",
            "Investment Score",
        ]
        if column in result.columns
    ]

    if sort_columns:
        ascending = [
            True if column == "Decision Priority" else False
            for column in sort_columns
        ]

        result = result.sort_values(
            sort_columns,
            ascending=ascending,
            na_position="last",
        )

    return result.reset_index(drop=True)

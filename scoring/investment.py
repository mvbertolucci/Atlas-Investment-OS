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
from scoring.reference import (
    ScoringReference,
    attach_reference_metadata,
)


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

    def exemption_mask(terms: Any) -> pd.Series:
        """
        True nas linhas isentas de uma regra: quando algum termo casa (como
        substring, case-insensitive) com o `sector` OU o `industry` da empresa.

        Cobre casos onde a metrica e estruturalmente enganosa por setor --
        Altman Z para utilities/financeiras, current ratio para SaaS (que
        carrega deferred revenue como passivo circulante).
        """

        mask = pd.Series(False, index=result.index)
        if not terms:
            return mask

        haystack = pd.Series("", index=result.index, dtype="object")
        for column in ("sector", "industry"):
            if column in result.columns:
                haystack = haystack.str.cat(
                    result[column].fillna("").astype(str),
                    sep=" | ",
                )
        haystack = haystack.str.lower()

        for term in terms:
            term = str(term).strip().lower()
            if term:
                mask = mask | haystack.str.contains(term, regex=False)

        return mask.fillna(False)

    max_net_debt_ebitda = rules.get(
        "net_debt_ebitda_max",
        rules.get(
            "max_net_debt_ebitda",
            4,
        ),
    )

    min_current_ratio = rules.get(
        "current_liquidity_min",
        rules.get(
            "current_ratio_min",
            rules.get(
                "min_current_ratio",
                1,
            ),
        ),
    )

    min_f_score = rules.get(
        "f_score_annual_min",
        rules.get(
            "piotroski_min",
            rules.get(
                "min_piotroski",
                4,
            ),
        ),
    )

    min_altman_z = rules.get(
        "altman_z_min",
        1.8,
    )

    altman_z_exempt = exemption_mask(rules.get("altman_z_exempt_sectors"))
    current_liquidity_exempt = exemption_mask(
        rules.get("current_liquidity_exempt_sectors")
    )
    net_debt_ebitda_exempt = exemption_mask(
        rules.get("net_debt_ebitda_exempt_sectors")
    )
    f_score_exempt = exemption_mask(rules.get("f_score_exempt_sectors"))

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
            (values > float(max_net_debt_ebitda)) & ~net_debt_ebitda_exempt,
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
            (values < float(min_current_ratio)) & ~current_liquidity_exempt,
            10,
            "Liquidez corrente baixa",
        )

    if "f_score_annual" in result.columns:
        values = pd.to_numeric(
            result["f_score_annual"],
            errors="coerce",
        )

        add_penalty(
            (values < float(min_f_score)) & ~f_score_exempt,
            15,
            "Piotroski baixo",
        )

    if "altman_z" in result.columns:
        values = pd.to_numeric(
            result["altman_z"],
            errors="coerce",
        )

        add_penalty(
            (values < float(min_altman_z)) & ~altman_z_exempt,
            15,
            "Altman Z baixo (risco de insolvencia)",
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
    config_path: Path,
    deal_breakers_path: Path,
    scoring_reference: ScoringReference | None = None,
) -> pd.DataFrame:
    """
    Executa o pipeline de decisão do Atlas.

    Ordem:

    1. Factor Engine
    2. Deal Breakers
    3. Opportunity Engine
    4. Conviction Engine
    5. Decision Engine (voz única de compra)
    6. Investment Thesis Engine
    7. Score Band (faixa descritiva do Investment Score, não é veredicto)
    8. Ordenação final
    """

    # config_path aponta para o arquivo de configuração do modelo
    # (config/model.yaml); as demais configs vivem no mesmo diretório.
    config_dir = config_path.parent

    features_path = config_dir / "features.yaml"
    model_path = config_dir / "model.yaml"

    if not features_path.exists():
        raise FileNotFoundError(
            f"Feature Store não encontrada: {features_path}"
        )

    result = score_all_factors(
        df,
        features_path=features_path,
        model_path=model_path if model_path.exists() else None,
        reference=scoring_reference,
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
    result = attach_reference_metadata(result, scoring_reference)

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

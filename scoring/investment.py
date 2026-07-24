from __future__ import annotations

from datetime import datetime
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

    observed_penalties = pd.Series(
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
        nonlocal observed_penalties, notes

        condition = condition.fillna(False)

        observed_penalties += (
            condition.astype(float)
            * float(penalty)
        )

        notes = notes.where(
            ~condition,
            notes + label + "; ",
        )

    missing_evidence: list[list[str]] = [
        [] for _ in range(len(result))
    ]

    def record_missing(
        values: pd.Series,
        exempt: pd.Series,
        label: str,
        field_name: str | None = None,
    ) -> None:
        evidence_field = field_name or label
        not_applicable = pd.Series(False, index=result.index)
        if "field_evidence" in result.columns:
            not_applicable = result["field_evidence"].map(
                lambda evidence: (
                    isinstance(evidence, dict)
                    and str(
                        (evidence.get(evidence_field) or {}).get("status", "")
                    ) == "not_applicable"
                )
            )
        missing = values.isna() & ~exempt.fillna(False) & ~not_applicable
        for position, active in enumerate(missing.tolist()):
            if active:
                missing_evidence[position].append(label)

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

    net_debt_values = pd.to_numeric(
        result.get(
            "net_debt_ebitda",
            pd.Series(None, index=result.index),
        ),
        errors="coerce",
    )
    # Lacuna provadamente inócua (ADR-051). `net_debt = total_debt -
    # total_cash`, e caixa nunca é negativo, então `net_debt <= total_debt`.
    # Com `ebitda > 0`, isso dá um teto: `net_debt_ebitda <=
    # total_debt/ebitda`. Se o TETO já está abaixo do limiar, nenhum valor de
    # caixa faz o deal breaker disparar -- a lacuna não pode mudar a decisão,
    # e cobrar penalidade de incerteza por ela é punir o desconhecido onde o
    # conhecido já responde. Medido em 2026-07-24: CVX (teto 1,198), HIG
    # (0,783) e CALM (0,000) contra limiar de 4,0, todos pagando 3,0 pontos.
    #
    # A guarda de `ebitda > 0` não é formalidade: com EBITDA negativo a
    # divisão inverte o sentido da desigualdade e o teto deixa de ser teto.
    net_debt_ebitda_harmless = _gap_cannot_breach_ceiling(
        result,
        numerator_ceiling="total_debt",
        denominator="ebitda",
        threshold=float(max_net_debt_ebitda),
    )
    record_missing(
        net_debt_values,
        net_debt_ebitda_exempt | net_debt_ebitda_harmless,
        "net_debt_ebitda",
    )
    add_penalty(
        (net_debt_values > float(max_net_debt_ebitda))
        & ~net_debt_ebitda_exempt,
        15,
        "Net Debt/EBITDA alto",
    )

    liquidity_column = None

    if "current_ratio" in result.columns:
        liquidity_column = "current_ratio"
    elif "current_liquidity" in result.columns:
        liquidity_column = "current_liquidity"

    liquidity_values = pd.to_numeric(
        result[liquidity_column]
        if liquidity_column is not None
        else pd.Series(None, index=result.index),
        errors="coerce",
    )
    record_missing(
        liquidity_values,
        current_liquidity_exempt,
        "current_ratio",
        liquidity_column or "current_ratio",
    )
    add_penalty(
        (liquidity_values < float(min_current_ratio))
        & ~current_liquidity_exempt,
        10,
        "Liquidez corrente baixa",
    )

    f_score_values = pd.to_numeric(
        result.get("f_score_annual", pd.Series(None, index=result.index)),
        errors="coerce",
    )
    record_missing(f_score_values, f_score_exempt, "f_score_annual")
    add_penalty(
        (f_score_values < float(min_f_score)) & ~f_score_exempt,
        15,
        "Piotroski baixo",
    )

    altman_values = pd.to_numeric(
        result.get("altman_z", pd.Series(None, index=result.index)),
        errors="coerce",
    )
    record_missing(altman_values, altman_z_exempt, "altman_z")
    add_penalty(
        (altman_values < float(min_altman_z)) & ~altman_z_exempt,
        15,
        "Altman Z baixo (risco de insolvencia)",
    )

    short_values = pd.to_numeric(
        result.get("short_float", pd.Series(None, index=result.index)),
        errors="coerce",
    )
    no_exemption = pd.Series(False, index=result.index)
    record_missing(short_values, no_exemption, "short_float")
    add_penalty(
        short_values > float(max_short_float),
        10,
        "Short float alto",
    )

    missing_policy = rules.get("missing_data") or {}
    penalty_each = float(missing_policy.get("penalty_each", 0.0))
    penalty_cap = float(missing_policy.get("penalty_cap", 0.0))
    uncertainty_penalty = pd.Series(
        [
            min(len(items) * penalty_each, penalty_cap)
            for items in missing_evidence
        ],
        index=result.index,
        dtype="float64",
    )
    total_penalty = observed_penalties + uncertainty_penalty
    result["Observed Risk Penalty"] = observed_penalties.round(1)
    result["Risk Uncertainty Penalty"] = uncertainty_penalty.round(1)
    result["Risk Penalty"] = total_penalty.round(1)
    result["Risk Evidence Missing"] = [
        "; ".join(items) if items else "Nenhum"
        for items in missing_evidence
    ]
    result["Risk Assessment Complete"] = [
        not items for items in missing_evidence
    ]

    result["Deal Breakers"] = (
        notes
        .str.strip("; ")
        .replace("", "Nenhum")
    )

    result["Investment Score"] = (
        score - total_penalty
    ).clip(
        lower=0,
        upper=100,
    ).round(1)

    return result


def _gap_cannot_breach_ceiling(
    frame: pd.DataFrame,
    *,
    numerator_ceiling: str,
    denominator: str,
    threshold: float,
) -> pd.Series:
    """Linhas onde o valor ausente NÃO pode cruzar o limiar, por limites.

    Uma razão cujo numerador tem teto conhecido e denominador positivo tem
    teto conhecido. Se esse teto já está abaixo do limiar, o valor real --
    seja ele qual for -- também está. Não é estimativa nem heurística: é o
    conhecido respondendo pelo desconhecido.

    Retorna False (conservador) sempre que os insumos não sustentam a
    conclusão: numerador ou denominador ausente, ou denominador <= 0, onde a
    divisão inverte a desigualdade e o teto deixa de valer.
    """
    ceiling = pd.to_numeric(
        frame.get(numerator_ceiling, pd.Series(None, index=frame.index)),
        errors="coerce",
    )
    base = pd.to_numeric(
        frame.get(denominator, pd.Series(None, index=frame.index)),
        errors="coerce",
    )
    usable = ceiling.notna() & base.notna() & (base > 0)
    bound = (ceiling / base.where(base > 0)).where(usable)
    return (bound < threshold).fillna(False)


def score_dataframe(
    df: pd.DataFrame,
    config_path: Path,
    deal_breakers_path: Path,
    scoring_reference: ScoringReference | None = None,
    quality_at: datetime | None = None,
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
    data_quality_path = config_dir / "data_quality.yaml"

    if not features_path.exists():
        raise FileNotFoundError(
            f"Feature Store não encontrada: {features_path}"
        )

    result = score_all_factors(
        df,
        features_path=features_path,
        model_path=model_path if model_path.exists() else None,
        reference=scoring_reference,
        quality_policy=(
            load_yaml(data_quality_path) if data_quality_path.exists() else None
        ),
        quality_at=quality_at,
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

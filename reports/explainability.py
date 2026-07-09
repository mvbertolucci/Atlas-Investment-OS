from __future__ import annotations

import pandas as pd


def _label(feature: str) -> tuple[str, str]:
    """
    Converte:

        business_roic
        valuation_PE
        financial_net_margin

    em

        ("Business", "ROIC")
        ("Valuation", "PE")
        ("Financial", "Net Margin")
    """

    parts = feature.split("_", 1)

    if len(parts) == 1:
        return "Other", feature.title()

    factor = parts[0].title()

    metric = (
        parts[1]
        .replace("_", " ")
        .replace("Ebitda", "EBITDA")
        .replace("Ebit", "EBIT")
        .replace("Pe", "PE")
        .replace("Peg", "PEG")
        .replace("Roe", "ROE")
        .replace("Roic", "ROIC")
        .replace("Rsi", "RSI")
        .title()
    )

    metric = (
        metric
        .replace("Pe", "PE")
        .replace("Peg", "PEG")
        .replace("Roe", "ROE")
        .replace("Roic", "ROIC")
        .replace("Rsi", "RSI")
        .replace("Ebitda", "EBITDA")
        .replace("Ebit", "EBIT")
    )

    return factor, metric


def build_explainability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Constrói uma tabela longa contendo todas as contribuições
    calculadas pelo Factor Engine.

    Retorna:

    Symbol
    Factor
    Feature
    Score
    Available
    """

    rows = []

    score_columns = sorted(
        c for c in df.columns
        if c.endswith("_score")
    )

    for _, row in df.iterrows():

        symbol = row.get("symbol", "")

        for score_col in score_columns:

            base = score_col[:-6]

            available_col = f"{base}_available"

            factor, feature = _label(base)

            rows.append(
                {
                    "Symbol": symbol,
                    "Factor": factor,
                    "Feature": feature,
                    "Score": row.get(score_col),
                    "Available": bool(row.get(available_col, False)),
                }
            )

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    result = result.sort_values(
        ["Symbol", "Factor", "Score"],
        ascending=[True, True, False],
    )

    result.reset_index(drop=True, inplace=True)

    return result
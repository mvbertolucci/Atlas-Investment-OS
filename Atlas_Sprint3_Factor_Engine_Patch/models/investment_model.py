from __future__ import annotations

import pandas as pd


def classify(score: float) -> str:
    if score >= 90:
        return "★★★★★ Comprar Forte"
    if score >= 80:
        return "★★★★ Comprar"
    if score >= 70:
        return "★★★ Acumular"
    if score >= 60:
        return "★★ Manter"
    return "★ Evitar"


def apply_recommendation(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "Investment Score" not in result.columns:
        raise ValueError("Investment Score não encontrado no DataFrame.")
    result["Recommendation"] = result["Investment Score"].apply(classify)
    return result

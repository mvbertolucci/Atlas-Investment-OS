from __future__ import annotations

import pandas as pd


def classify(score: float) -> str:
    """
    Descreve a FAIXA do Investment Score -- rótulo puramente descritivo, não
    um veredicto de compra. O classificador de compra autoritativo do Atlas é
    `decision.policy.evaluate_decision` (coluna `Decision`/`Decision Rating`),
    que pondera Opportunity, Conviction, risco e deal breakers. Esta faixa só
    posiciona o score numa banda, para leitura rápida ao lado da decisão --
    nunca deve ser lida como uma segunda recomendação de compra (era essa
    duplicidade, "★★★ Acumular" vs Decision, que gerava sinais contraditórios
    sobre o mesmo ativo).
    """
    if score >= 90:
        return "Elite (≥90)"
    if score >= 80:
        return "Alto (80–89)"
    if score >= 70:
        return "Bom (70–79)"
    if score >= 60:
        return "Médio (60–69)"
    return "Baixo (<60)"


def apply_recommendation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Anexa a coluna `Score Band` (faixa descritiva do Investment Score). Mantém
    o nome de função por compatibilidade com a cadeia de scoring; a antiga
    coluna `Recommendation` (rótulo de compra em estrelas) foi aposentada em
    favor de `Decision` como voz única de compra -- ver `classify`.
    """
    result = df.copy()
    if "Investment Score" not in result.columns:
        raise ValueError("Investment Score não encontrado no DataFrame.")
    result["Score Band"] = result["Investment Score"].apply(classify)
    return result

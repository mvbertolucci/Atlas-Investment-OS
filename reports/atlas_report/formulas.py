from __future__ import annotations

"""
Registro estático de fórmulas/inputs/interpretações por feature, usado só
para EXIBIÇÃO no one-pager -- nenhuma conta acontece aqui. Mantido em
sincronia manual com STATUS.md secao 2 (Fórmulas em produção) e com o
código que essas linhas descrevem; se um motor mudar de fórmula, esta
tabela e STATUS.md precisam mudar juntos (ver STATUS.md secao 7).

Quando uma feature não está aqui, ou um input não é encontrado no
DataFrame do run, o one-pager mostra "pendente" -- nunca inventa texto.
"""

FEATURE_FORMULAS: dict[str, str] = {
    "roic": (
        "NOPAT / Invested Capital, onde NOPAT = EBIT × (1 − alíquota efetiva; "
        "fallback 21% se pretax income/tax provision ausentes) "
        "— analytics/fundamentals.py::_compute_roic"
    ),
    "interest_coverage": (
        "EBIT / |Interest Expense| — analytics/fundamentals.py::_compute_interest_coverage"
    ),
    "f_score_annual": (
        "Piotroski F-Score: 9 critérios binários (lucro, CFO, ROA, qualidade do "
        "lucro, alavancagem, liquidez, diluição, margem bruta, giro de ativos), "
        "escala 0–9 — analytics/fundamentals.py::_compute_f_score"
    ),
    "net_debt_ebitda": (
        "(Total Debt − Total Cash) / EBITDA — analytics/mapper.py::normalize_columns"
    ),
    "net_debt_total_equity": (
        "Debt / Equity repassado pelo provider, mapeado 1:1 (mesma coluna) "
        "— analytics/mapper.py::COLUMN_MAP"
    ),
    "fcf_yield": (
        "Free Cash Flow / Market Cap — analytics/mapper.py::normalize_columns"
    ),
    "shareholder_yield": (
        "(Dividend Rate / Price) + (Buyback / Market Cap) "
        "— analytics/mapper.py::normalize_columns"
    ),
    "target_upside": (
        "(Consensus Target / Price − 1) × 100 — analytics/mapper.py::normalize_columns"
    ),
    "rsi_14": (
        "RSI de 14 períodos sobre variações diárias de fechamento "
        "— analytics/indicators.py::rsi"
    ),
    "momentum_3m": (
        "Variação percentual de preço nos últimos 63 pregões (~3 meses) "
        "— analytics/indicators.py::momentum"
    ),
    "momentum_6m": (
        "Variação percentual de preço nos últimos 126 pregões (~6 meses) "
        "— analytics/indicators.py::momentum"
    ),
    "momentum_12m": (
        "Variação percentual de preço nos últimos 252 pregões (~12 meses) "
        "— analytics/indicators.py::momentum"
    ),
    "distance_52w_high": (
        "(Preço atual / Máxima 52 semanas − 1) × 100 "
        "— analytics/indicators.py::enrich_technicals"
    ),
}

PASS_THROUGH_FORMULA = (
    "repassado diretamente pelo provider (Yahoo Finance) — não recalculado "
    "pelo Atlas nesta versão"
)

PASS_THROUGH_COLUMNS = frozenset(
    {"roe", "gross_margin", "operating_margin", "net_margin", "debt_to_equity",
     "current_ratio", "pe", "forward_pe", "ev_ebitda", "ev_ebit", "peg", "pb"}
)

# (rótulo, coluna candidata no DataFrame do run) -- procurado linha a
# linha; ausente ou NaN vira "pendente", nunca um valor inventado. Colunas
# de demonstração bruta (invested_capital, tax_provision, interest_expense
# etc.) são descartadas pelo motor logo após o cálculo
# (analytics/fundamentals.py::compute_fundamentals faz row.pop(...) das
# demonstrações), então aparecem pendentes por design -- não é um bug
# deste relatório, é o que o motor de fato retém.
FEATURE_INPUTS: dict[str, tuple[tuple[str, str], ...]] = {
    "roic": (
        ("EBIT", "ebit"),
        ("Invested Capital", "invested_capital"),
        ("Tax Provision", "tax_provision"),
        ("Pretax Income", "pretax_income"),
    ),
    "interest_coverage": (
        ("EBIT", "ebit"),
        ("Interest Expense", "interest_expense"),
    ),
    "f_score_annual": (),
    "net_debt_ebitda": (
        ("Total Debt", "total_debt"),
        ("Total Cash", "total_cash"),
        ("EBITDA", "ebitda"),
    ),
    "fcf_yield": (
        ("Free Cash Flow", "free_cashflow"),
        ("Market Cap", "market_cap"),
    ),
    "shareholder_yield": (
        ("Dividend Rate", "dividend_rate"),
        ("Price", "price"),
        ("Buyback", "buyback"),
        ("Market Cap", "market_cap"),
    ),
    "target_upside": (
        ("Consensus Target", "consensus_target"),
        ("Target Price", "target_price"),
        ("Price", "price"),
    ),
    "distance_52w_high": (
        ("Price", "price"),
        ("52W High", "year_high"),
    ),
}


def interpret_feature(column: str, value: float | None) -> str | None:
    """
    Classifica o valor numa faixa só quando existe um threshold já
    estabelecido pelo próprio motor (config/sell_rules.yaml,
    config/deal_breakers.json) -- nunca um corte inventado aqui. Retorna
    None quando não há threshold de produção para a métrica.
    """
    if value is None:
        return None
    if column == "f_score_annual":
        if value < 4:
            return f"F-Score {value:.0f} — zona fraca (< 4, piso do motor)"
        if value >= 7:
            return f"F-Score {value:.0f} — zona forte (≥ 7)"
        return f"F-Score {value:.0f} — zona neutra (4–6)"
    if column == "interest_coverage":
        threshold = 2.5
        if value < threshold:
            return f"Interest Coverage {value:.2f}× — abaixo do piso de distress ({threshold:.1f}×)"
        return f"Interest Coverage {value:.2f}× — acima do piso de distress ({threshold:.1f}×)"
    if column == "net_debt_ebitda":
        threshold = 4.0
        if value > threshold:
            return f"Net Debt/EBITDA {value:.2f}× — acima do teto de distress ({threshold:.1f}×)"
        return f"Net Debt/EBITDA {value:.2f}× — dentro do teto de distress ({threshold:.1f}×)"
    if column == "target_upside":
        threshold = -10.0
        if value < threshold:
            return f"Target Upside {value:.1f}% — abaixo do piso de valuation_stretch ({threshold:.0f}%)"
        return f"Target Upside {value:.1f}% — acima do piso de valuation_stretch ({threshold:.0f}%)"
    return None


def formula_for(column: str) -> str:
    if column in FEATURE_FORMULAS:
        return FEATURE_FORMULAS[column]
    if column in PASS_THROUGH_COLUMNS:
        return PASS_THROUGH_FORMULA
    return "fórmula: pendente"


def inputs_for(column: str) -> tuple[tuple[str, str], ...]:
    return FEATURE_INPUTS.get(column, ())


RULE_DEFINITIONS: dict[str, str] = {
    "distress": (
        "Risco de solvência/alavancagem, independente de tendência: Altman Z, "
        "Interest Coverage, Net Debt/EBITDA, Current Ratio, Short Float e piso "
        "de F-Score, cada condição com sua isenção setorial "
        "— portfolio/sell_rules.py::_distress"
    ),
    "valuation_stretch": (
        "Target Upside abaixo do piso configurado "
        "— portfolio/sell_rules.py::_valuation_stretch"
    ),
    "fundamental_decay": (
        "Queda de F-Score ou ROIC frente ao snapshot anterior comparável "
        "— portfolio/sell_rules.py::_fundamental_decay"
    ),
    "relative_decay": (
        "Percentil do Investment Score contra o universo confiável abaixo "
        "do piso configurado — portfolio/sell_rules.py::_relative_decay"
    ),
}

RULE_STATUS_LABELS: dict[str, str] = {
    "triggered": "disparou",
    "clear": "ok",
    "not_evaluated": "não avaliado",
    "disabled": "desativada",
}

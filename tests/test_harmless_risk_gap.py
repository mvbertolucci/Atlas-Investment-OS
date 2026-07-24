"""Lacuna de risco provadamente inócua não paga penalidade (ADR-051).

`net_debt = total_debt - total_cash`, e caixa nunca é negativo, então
`net_debt <= total_debt`. Com `ebitda > 0` isso dá um teto para a razão. Se o
teto já está abaixo do limiar, o caixa desconhecido não pode acionar o deal
breaker -- e cobrar incerteza por ele pune o desconhecido onde o conhecido já
responde.

Casos numéricos vindos da carteira real em 2026-07-24.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scoring.investment import _gap_cannot_breach_ceiling


def _frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols, index=[0])


def test_ceiling_below_threshold_is_provably_harmless() -> None:
    """CVX: dívida 45,43 bi sobre EBITDA 37,91 bi = teto 1,198 contra
    limiar 4,0. Nenhum valor de caixa faz isso quebrar."""
    frame = _frame(total_debt=[45_427_998_720.0], ebitda=[37_906_001_920.0])

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is True


def test_ceiling_above_threshold_is_not_harmless() -> None:
    """Se o teto cruza o limiar, o caixa desconhecido PODE ser a diferença
    entre passar e quebrar -- a penalidade de incerteza é devida."""
    frame = _frame(total_debt=[500.0], ebitda=[100.0])  # teto 5,0 > 4,0

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is False


def test_negative_ebitda_never_claims_safety() -> None:
    """Com denominador negativo a divisão inverte a desigualdade e o teto
    deixa de ser teto. A guarda não é formalidade."""
    frame = _frame(total_debt=[100.0], ebitda=[-50.0])

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is False


def test_zero_denominator_never_claims_safety() -> None:
    frame = _frame(total_debt=[100.0], ebitda=[0.0])

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is False


def test_missing_input_never_claims_safety() -> None:
    """Sem os insumos, nada é demonstrável -- o conservador é penalizar."""
    for cols in (
        {"total_debt": [None], "ebitda": [100.0]},
        {"total_debt": [100.0], "ebitda": [None]},
        {},
    ):
        frame = _frame(**cols) if cols else pd.DataFrame(index=[0])
        result = _gap_cannot_breach_ceiling(
            frame,
            numerator_ceiling="total_debt",
            denominator="ebitda",
            threshold=4.0,
        )
        assert bool(result.iloc[0]) is False, cols


def test_net_cash_company_is_harmless() -> None:
    """CALM: teto 0,0 -- dívida zero. Trivialmente inócuo."""
    frame = _frame(total_debt=[0.0], ebitda=[100.0])

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is True


def test_exactly_at_threshold_is_not_harmless() -> None:
    """Igualdade não é folga: o limiar dispara em `>`, mas afirmar
    inocuidade exige estar estritamente abaixo."""
    frame = _frame(total_debt=[400.0], ebitda=[100.0])  # teto exatamente 4,0

    result = _gap_cannot_breach_ceiling(
        frame, numerator_ceiling="total_debt", denominator="ebitda", threshold=4.0
    )

    assert bool(result.iloc[0]) is False

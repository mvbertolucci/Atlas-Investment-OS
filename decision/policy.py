from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionPolicy:
    """
    Limites usados pelo Atlas para transformar Opportunity e Conviction
    em uma decisão objetiva.

    A política é independente de pandas e do restante do pipeline,
    facilitando testes e futuras estratégias alternativas.
    """

    strong_buy_opportunity: float = 80.0
    strong_buy_conviction: float = 85.0

    buy_opportunity: float = 75.0
    buy_conviction: float = 70.0

    accumulate_opportunity: float = 65.0
    accumulate_conviction: float = 60.0

    hold_opportunity: float = 55.0
    hold_conviction: float = 50.0

    watch_opportunity: float = 45.0
    watch_conviction: float = 40.0

    maximum_risk_penalty_for_buy: float = 10.0
    maximum_risk_penalty_for_accumulate: float = 20.0


DEFAULT_POLICY = DecisionPolicy()


def normalize_score(
    value: float | int | None,
    default: float = 50.0,
) -> float:
    """
    Converte um valor em score válido entre 0 e 100.
    """

    if value is None:
        return default

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default

    if numeric != numeric:  # NaN
        return default

    return max(0.0, min(100.0, numeric))


def evaluate_decision(
    opportunity_score: float | int | None,
    conviction_score: float | int | None,
    risk_penalty: float | int | None = 0.0,
    has_deal_breaker: bool = False,
    policy: DecisionPolicy = DEFAULT_POLICY,
) -> str:
    """
    Retorna o código de decisão do Atlas.

    Códigos possíveis:

    - STRONG_BUY
    - BUY
    - ACCUMULATE
    - HOLD
    - WATCH
    - AVOID

    Deal breakers e risco elevado podem limitar decisões positivas,
    mesmo quando Opportunity e Conviction são altas.
    """

    opportunity = normalize_score(opportunity_score)
    conviction = normalize_score(conviction_score)
    risk = normalize_score(risk_penalty, default=0.0)

    if has_deal_breaker:
        if opportunity >= policy.hold_opportunity:
            return "WATCH"
        return "AVOID"

    if risk > policy.maximum_risk_penalty_for_accumulate:
        return "AVOID"

    if (
        opportunity >= policy.strong_buy_opportunity
        and conviction >= policy.strong_buy_conviction
        and risk <= policy.maximum_risk_penalty_for_buy
    ):
        return "STRONG_BUY"

    if (
        opportunity >= policy.buy_opportunity
        and conviction >= policy.buy_conviction
        and risk <= policy.maximum_risk_penalty_for_buy
    ):
        return "BUY"

    if (
        opportunity >= policy.accumulate_opportunity
        and conviction >= policy.accumulate_conviction
        and risk <= policy.maximum_risk_penalty_for_accumulate
    ):
        return "ACCUMULATE"

    if (
        opportunity >= policy.hold_opportunity
        and conviction >= policy.hold_conviction
    ):
        return "HOLD"

    if (
        opportunity >= policy.watch_opportunity
        and conviction >= policy.watch_conviction
    ):
        return "WATCH"

    return "AVOID"


def decision_priority(decision: str) -> int:
    """
    Retorna a prioridade de ordenação da decisão.

    Quanto menor o número, maior a prioridade.
    """

    priorities = {
        "STRONG_BUY": 0,
        "BUY": 1,
        "ACCUMULATE": 2,
        "HOLD": 3,
        "WATCH": 4,
        "AVOID": 5,
    }

    return priorities.get(
        str(decision).strip().upper(),
        99,
    )
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from portfolio.models import (
    Portfolio,
    RebalanceAction,
    RebalancePlan,
)
from portfolio.quality import PortfolioQualityResult


@dataclass(frozen=True)
class RebalancePolicy:
    """
    Regras consultivas do Rebalance Engine.

    Todos os pesos usam escala decimal:
    0.15 representa 15%.
    """

    tolerance: float = 0.02
    minimum_trade_value: float = 500.0
    allow_sells: bool = True
    maximum_position_weight: float = 0.20
    minimum_cash_weight: float = 0.05


DEFAULT_REBALANCE_POLICY = RebalancePolicy()


class RebalanceError(ValueError):
    """Erro de geração do plano de rebalanceamento."""


@dataclass(frozen=True)
class RebalanceContext:
    """
    Contexto opcional usado para priorizar ações.

    `target_weights` pode ser fornecido diretamente. Quando ausente,
    o engine calcula pesos-alvo a partir da qualidade individual.
    """

    target_weights: Mapping[str, float] | None = None
    available_cash: float | None = None


def _validate_policy(
    policy: RebalancePolicy,
) -> None:
    if not 0.0 <= policy.tolerance <= 1.0:
        raise RebalanceError(
            "tolerance deve estar entre 0 e 1."
        )

    if policy.minimum_trade_value < 0:
        raise RebalanceError(
            "minimum_trade_value não pode ser negativo."
        )

    if not 0.0 < policy.maximum_position_weight <= 1.0:
        raise RebalanceError(
            "maximum_position_weight deve estar entre 0 e 1."
        )

    if not 0.0 <= policy.minimum_cash_weight < 1.0:
        raise RebalanceError(
            "minimum_cash_weight deve estar entre 0 e 1."
        )


def _current_weights(
    portfolio: Portfolio,
) -> dict[str, float]:
    weighted = portfolio.with_calculated_weights()

    return {
        holding.symbol: holding.portfolio_weight or 0.0
        for holding in weighted.holdings
    }


def _quality_signal(
    holding,
) -> float:
    """
    Converte CompanyReport em sinal de alocação entre 0 e 1.
    """

    report = holding.company_report

    if report is None:
        return 0.0

    values = [
        report.investment_score,
        report.opportunity_score,
        report.conviction_score,
        report.decision_confidence,
    ]

    available = [
        float(value)
        for value in values
        if value is not None
    ]

    if not available:
        return 0.0

    base = sum(available) / len(available)

    decision_multiplier = {
        "STRONG_BUY": 1.20,
        "BUY": 1.10,
        "ACCUMULATE": 1.00,
        "HOLD": 0.80,
        "WATCH": 0.50,
        "AVOID": 0.10,
    }.get(report.decision, 0.75)

    return max(
        0.0,
        min(
            1.0,
            (base / 100.0) * decision_multiplier,
        ),
    )


def _normalize_targets(
    raw_targets: Mapping[str, float],
    *,
    investable_weight: float,
    maximum_position_weight: float,
) -> dict[str, float]:
    if not raw_targets:
        return {}

    cleaned = {
        str(symbol).strip().upper(): max(0.0, float(weight))
        for symbol, weight in raw_targets.items()
        if str(symbol).strip()
    }

    if not cleaned:
        return {}

    total = sum(cleaned.values())

    if total <= 0:
        return {
            symbol: 0.0
            for symbol in cleaned
        }

    normalized = {
        symbol: (
            value / total
        ) * investable_weight
        for symbol, value in cleaned.items()
    }

    capped = {
        symbol: min(
            weight,
            maximum_position_weight,
        )
        for symbol, weight in normalized.items()
    }

    residual = investable_weight - sum(capped.values())

    if residual > 0:
        uncapped = [
            symbol
            for symbol, weight in capped.items()
            if weight < maximum_position_weight
        ]

        while residual > 1e-9 and uncapped:
            share = residual / len(uncapped)
            next_uncapped: list[str] = []

            for symbol in uncapped:
                room = (
                    maximum_position_weight
                    - capped[symbol]
                )
                increment = min(room, share)
                capped[symbol] += increment
                residual -= increment

                if (
                    capped[symbol]
                    < maximum_position_weight - 1e-9
                ):
                    next_uncapped.append(symbol)

            if next_uncapped == uncapped:
                break

            uncapped = next_uncapped

    return {
        symbol: round(weight, 6)
        for symbol, weight in capped.items()
    }


def _automatic_targets(
    portfolio: Portfolio,
    *,
    policy: RebalancePolicy,
) -> dict[str, float]:
    raw = {
        holding.symbol: _quality_signal(holding)
        for holding in portfolio.holdings
    }

    investable_weight = 1.0 - policy.minimum_cash_weight

    return _normalize_targets(
        raw,
        investable_weight=investable_weight,
        maximum_position_weight=(
            policy.maximum_position_weight
        ),
    )


def _explicit_targets(
    context: RebalanceContext,
    *,
    policy: RebalancePolicy,
) -> dict[str, float] | None:
    if context.target_weights is None:
        return None

    return _normalize_targets(
        context.target_weights,
        investable_weight=(
            1.0 - policy.minimum_cash_weight
        ),
        maximum_position_weight=(
            policy.maximum_position_weight
        ),
    )


def _action_priority(
    action: str,
    *,
    absolute_trade_value: float,
    decision: str,
) -> int:
    base = {
        "SELL": 0,
        "BUY": 10,
        "HOLD": 50,
    }[action]

    decision_adjustment = {
        "AVOID": -5,
        "WATCH": 0,
        "HOLD": 2,
        "ACCUMULATE": -1,
        "BUY": -2,
        "STRONG_BUY": -3,
    }.get(decision, 0)

    size_adjustment = int(
        min(
            9,
            absolute_trade_value // 1000,
        )
    )

    return max(
        0,
        base + decision_adjustment - size_adjustment,
    )


def _reason(
    *,
    action: str,
    current_weight: float,
    target_weight: float,
    decision: str,
) -> str:
    delta = target_weight - current_weight

    if action == "BUY":
        return (
            f"Aumentar peso em {delta:.1%}; "
            f"decisão atual: {decision or 'N/A'}."
        )

    if action == "SELL":
        return (
            f"Reduzir peso em {abs(delta):.1%}; "
            f"decisão atual: {decision or 'N/A'}."
        )

    return (
        f"Peso dentro da tolerância de rebalanceamento; "
        f"decisão atual: {decision or 'N/A'}."
    )


def build_sell_only_plan(
    portfolio: Portfolio,
    *,
    quality: PortfolioQualityResult | None = None,
    policy: RebalancePolicy = DEFAULT_REBALANCE_POLICY,
) -> RebalancePlan:
    """
    Gera um plano consultivo apenas de venda.

    Sinaliza SELL para holdings cuja decisão atual é AVOID; todas as demais
    permanecem HOLD no peso atual -- este motor nunca sugere aumentar peso em
    uma posição já existente. O capital liberado pela venda vira caixa; a
    intenção é realocá-lo em novos papéis (via screener/ranking), fora deste
    motor, em vez de redistribuí-lo entre as posições que já existem.
    """

    if not isinstance(portfolio, Portfolio):
        raise TypeError(
            "build_sell_only_plan exige um objeto Portfolio."
        )

    if portfolio.total_value <= 0:
        raise RebalanceError(
            "A carteira precisa ter valor total positivo."
        )

    _validate_policy(policy)

    current_weights = _current_weights(portfolio)

    actions: list[RebalanceAction] = []
    released_cash = 0.0
    turnover_numerator = 0.0

    for holding in portfolio.holdings:
        current_weight = current_weights.get(
            holding.symbol,
            0.0,
        )

        report = holding.company_report
        decision = (
            report.decision
            if report is not None
            else ""
        )

        is_avoid = decision == "AVOID"
        trade_value = (
            -(current_weight * portfolio.total_value)
            if is_avoid
            else 0.0
        )

        if (
            is_avoid
            and abs(trade_value) >= policy.minimum_trade_value
        ):
            action = "SELL"
            target_weight = 0.0
            released_cash += abs(trade_value)
            reason = (
                "Decisão atual: AVOID. Vender integralmente; capital "
                "liberado destina-se a novos papéis (screener), não a "
                "realocação interna da carteira."
            )
        else:
            action = "HOLD"
            target_weight = current_weight
            trade_value = 0.0
            reason = (
                "Sem sinal de venda nesta execução; nenhuma realocação "
                f"interna é sugerida. Decisão atual: {decision or 'N/A'}."
            )

        turnover_numerator += abs(trade_value)

        actions.append(
            RebalanceAction(
                symbol=holding.symbol,
                action=action,
                current_weight=current_weight,
                target_weight=target_weight,
                target_value=target_weight * portfolio.total_value,
                trade_value=trade_value,
                reason=reason,
                priority=0 if action == "SELL" else 50,
            )
        )

    actions.sort(
        key=lambda item: (
            item.priority,
            item.symbol,
        )
    )

    warnings: list[str] = []

    missing_reports = tuple(
        holding.symbol
        for holding in portfolio.holdings
        if holding.company_report is None
    )

    if missing_reports:
        warnings.append(
            "Holdings sem CompanyReport: "
            + ", ".join(missing_reports)
        )

    if quality is not None:
        if not isinstance(
            quality,
            PortfolioQualityResult,
        ):
            raise TypeError(
                "quality deve ser um PortfolioQualityResult."
            )

        warnings.extend(quality.warnings)

    estimated_turnover = (
        turnover_numerator
        / portfolio.total_value
    )

    return RebalancePlan(
        actions=tuple(actions),
        required_cash=0.0,
        released_cash=round(released_cash, 2),
        estimated_turnover=min(
            1.0,
            round(estimated_turnover, 6),
        ),
        warnings=tuple(
            dict.fromkeys(warnings)
        ),
    )


def build_rebalance_plan(
    portfolio: Portfolio,
    *,
    quality: PortfolioQualityResult | None = None,
    policy: RebalancePolicy = DEFAULT_REBALANCE_POLICY,
    context: RebalanceContext | None = None,
) -> RebalancePlan:
    """
    Gera um plano consultivo de rebalanceamento.

    O engine nunca executa ordens. Ele apenas produz sugestões.
    """

    if not isinstance(portfolio, Portfolio):
        raise TypeError(
            "build_rebalance_plan exige um objeto Portfolio."
        )

    if portfolio.total_value <= 0:
        raise RebalanceError(
            "A carteira precisa ter valor total positivo."
        )

    _validate_policy(policy)

    context = context or RebalanceContext()

    explicit = _explicit_targets(
        context,
        policy=policy,
    )

    target_weights = (
        explicit
        if explicit is not None
        else _automatic_targets(
            portfolio,
            policy=policy,
        )
    )

    current_weights = _current_weights(portfolio)

    actions: list[RebalanceAction] = []
    required_cash = 0.0
    released_cash = 0.0
    turnover_numerator = 0.0

    for holding in portfolio.holdings:
        current_weight = current_weights.get(
            holding.symbol,
            0.0,
        )
        target_weight = target_weights.get(
            holding.symbol,
            0.0,
        )

        delta_weight = (
            target_weight - current_weight
        )
        target_value = (
            target_weight * portfolio.total_value
        )
        trade_value = (
            delta_weight * portfolio.total_value
        )

        report = holding.company_report
        decision = (
            report.decision
            if report is not None
            else ""
        )

        if abs(delta_weight) <= policy.tolerance:
            action = "HOLD"
            trade_value = 0.0

        elif trade_value > 0:
            action = "BUY"

        else:
            action = "SELL"

        if (
            action == "SELL"
            and not policy.allow_sells
        ):
            action = "HOLD"
            trade_value = 0.0

        if (
            action != "HOLD"
            and abs(trade_value)
            < policy.minimum_trade_value
        ):
            action = "HOLD"
            trade_value = 0.0

        if action == "BUY":
            required_cash += trade_value

        elif action == "SELL":
            released_cash += abs(trade_value)

        turnover_numerator += abs(trade_value)

        actions.append(
            RebalanceAction(
                symbol=holding.symbol,
                action=action,
                current_weight=current_weight,
                target_weight=target_weight,
                target_value=target_value,
                trade_value=trade_value,
                reason=_reason(
                    action=action,
                    current_weight=current_weight,
                    target_weight=target_weight,
                    decision=decision,
                ),
                priority=_action_priority(
                    action,
                    absolute_trade_value=abs(
                        trade_value
                    ),
                    decision=decision,
                ),
            )
        )

    actions.sort(
        key=lambda item: (
            item.priority,
            item.symbol,
        )
    )

    available_cash = (
        context.available_cash
        if context.available_cash is not None
        else portfolio.cash
    )

    warnings: list[str] = []

    if required_cash > (
        available_cash + released_cash
    ):
        warnings.append(
            "Caixa insuficiente para executar todas "
            "as compras sugeridas."
        )

    missing_reports = tuple(
        holding.symbol
        for holding in portfolio.holdings
        if holding.company_report is None
    )

    if missing_reports:
        warnings.append(
            "Holdings sem CompanyReport: "
            + ", ".join(missing_reports)
        )

    if quality is not None:
        if not isinstance(
            quality,
            PortfolioQualityResult,
        ):
            raise TypeError(
                "quality deve ser um PortfolioQualityResult."
            )

        warnings.extend(quality.warnings)

    estimated_turnover = (
        turnover_numerator
        / portfolio.total_value
    )

    return RebalancePlan(
        actions=tuple(actions),
        required_cash=round(required_cash, 2),
        released_cash=round(released_cash, 2),
        estimated_turnover=min(
            1.0,
            round(estimated_turnover, 6),
        ),
        warnings=tuple(
            dict.fromkeys(warnings)
        ),
    )

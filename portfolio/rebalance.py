from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import pandas as pd

from portfolio.models import (
    Portfolio,
    RebalanceAction,
    RebalancePlan,
)
from portfolio.quality import PortfolioQualityResult
from portfolio.sell_rules import (
    SellRuleContext,
    SellRulesPolicy,
    evaluate_sell_rules,
    score_percentiles,
)


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


class SellEngineBlockedError(RebalanceError):
    """
    O motor de venda stateful recusa produzir qualquer decisão (HOLD/TRIM/
    SELL/REVISAR) enquanto houver posição real (quantity > 0) sem tese
    registrada em config/portfolio.csv. Distinto de RebalanceError genérico
    para que o chamador (run_all.py) possa capturar especificamente e manter
    o resto do pipeline (screener, watchlist, ranking) funcionando -- só a
    seção de venda fica indisponível, nunca o run inteiro.
    """

    def __init__(self, missing_thesis_symbols: tuple[str, ...]) -> None:
        self.missing_thesis_symbols = missing_thesis_symbols
        super().__init__(
            "Motor de venda bloqueado: posição(ões) sem tese registrada "
            "(config/portfolio.csv, coluna 'thesis'): "
            + ", ".join(missing_thesis_symbols)
        )


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
    non_portfolio_origin: list[str] = []

    for holding in portfolio.holdings:
        # Defesa em profundidade: um Holding só existe legitimamente porque
        # veio de config/portfolio.csv, mas se `origin` foi verificado contra
        # a linha do DataFrame analisado (enrich_portfolio_from_analysis) e
        # essa verificação disser algo diferente de "portfolio", este motor
        # nunca emite SELL nem HOLD para o símbolo -- nunca age fora de uma
        # posição real, mesmo que o Portfolio tenha sido construído
        # incorretamente por um chamador.
        if holding.origin and holding.origin != "portfolio":
            non_portfolio_origin.append(holding.symbol)
            continue

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

    if non_portfolio_origin:
        warnings.append(
            "Holdings ignorados por proveniência não confirmada como "
            "'portfolio' (nenhum sinal de venda/manutenção foi emitido "
            "para eles): " + ", ".join(non_portfolio_origin)
        )

    missing_reports = tuple(
        holding.symbol
        for holding in portfolio.holdings
        if holding.company_report is None
        and holding.symbol not in non_portfolio_origin
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


def _missing_rule_data(row: Mapping[str, Any]) -> tuple[str, ...]:
    missing: list[str] = []
    for key, value in row.items():
        if str(key).endswith("_available") and not bool(value):
            missing.append(str(key)[: -len("_available")])
    for field_name in (
        "altman_z",
        "interest_coverage",
        "target_upside",
        "f_score_annual",
        "roic",
    ):
        value = row.get(field_name)
        if value is None or pd.isna(value):
            missing.append(field_name)
    return tuple(dict.fromkeys(missing))


def _quantity_increase_warning(
    symbol: str,
    current_quantity: float,
    previous_quantity: Any,
) -> str | None:
    """
    Aviso não-bloqueante quando a quantidade de uma posição existente
    aumentou desde o último run -- pede confirmação manual da tese (não
    exige nova tese automaticamente). Reduções/vendas parciais e o
    primeiro run (sem quantidade anterior) nunca disparam este aviso.
    """
    try:
        previous = float(previous_quantity)
    except (TypeError, ValueError):
        return None
    if previous != previous:
        return None
    if current_quantity > previous + 1e-9:
        return (
            f"{symbol}: quantidade aumentou de {previous:g} para "
            f"{current_quantity:g} desde o último run -- confirme a tese "
            "(atualize thesis_updated_at em config/portfolio.csv)."
        )
    return None


def _earnings_between_runs(
    value: Any,
    previous_run_at: pd.Timestamp | None,
    current_run_at: str | datetime | pd.Timestamp,
) -> bool | None:
    if value is None or pd.isna(value) or previous_run_at is None:
        return None
    earnings_at = pd.to_datetime(value, errors="coerce")
    current_at = pd.Timestamp(current_run_at)
    if pd.isna(earnings_at):
        return None
    return previous_run_at < earnings_at <= current_at


def build_stateful_sell_plan(
    portfolio: Portfolio,
    analysis_df: pd.DataFrame,
    *,
    sell_rules_policy: SellRulesPolicy,
    previous_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | datetime | pd.Timestamp | None = None,
    quality: PortfolioQualityResult | None = None,
    policy: RebalancePolicy = DEFAULT_REBALANCE_POLICY,
) -> RebalancePlan:
    """Motor sell-only stateful; produz sinais consultivos, nunca ordens."""
    if not isinstance(portfolio, Portfolio):
        raise TypeError("build_stateful_sell_plan exige Portfolio.")
    if not isinstance(analysis_df, pd.DataFrame):
        raise TypeError("analysis_df exige DataFrame.")
    if portfolio.total_value <= 0:
        raise RebalanceError("A carteira precisa ter valor total positivo.")
    if portfolio.missing_thesis_symbols:
        raise SellEngineBlockedError(portfolio.missing_thesis_symbols)
    _validate_policy(policy)

    previous_by_symbol = previous_by_symbol or {}
    current_run_at = current_run_at or datetime.now()
    rows = {
        str(row.get("symbol", "")).strip().upper(): row.to_dict()
        for _, row in analysis_df.iterrows()
        if str(row.get("symbol", "")).strip()
    }
    percentiles, universe_size, universe_scope = score_percentiles(
        analysis_df,
        sell_rules_policy,
    )
    current_weights = _current_weights(portfolio)
    actions: list[RebalanceAction] = []
    warnings: list[str] = []
    released_cash = 0.0
    turnover_numerator = 0.0
    non_portfolio_origin: list[str] = []

    for holding in portfolio.holdings:
        if holding.origin and holding.origin != "portfolio":
            non_portfolio_origin.append(holding.symbol)
            continue
        row = rows.get(holding.symbol, {})
        current = dict(row)
        current["score_coverage"] = row.get(
            "Score Coverage", row.get("Confidence Score")
        )
        current["confidence_score"] = row.get("Confidence Score")
        symbol_baseline = baseline_status
        previous = previous_by_symbol.get(holding.symbol)
        if baseline_status == "comparable" and previous is None:
            symbol_baseline = "first_run"
        if previous is not None:
            quantity_warning = _quantity_increase_warning(
                holding.symbol,
                holding.quantity,
                previous.get("quantity"),
            )
            if quantity_warning:
                warnings.append(quantity_warning)
        earnings = _earnings_between_runs(
            row.get("earnings_date"),
            previous_run_at,
            current_run_at,
        )
        context = SellRuleContext(
            symbol=holding.symbol,
            sector=holding.sector or str(row.get("sector", "")),
            industry=holding.industry or str(row.get("industry", "")),
            current=current,
            previous=previous,
            baseline_status=symbol_baseline,
            score_percentile=percentiles.get(holding.symbol),
            universe_size=universe_size,
            universe_scope=universe_scope,
            missing_data=_missing_rule_data(row),
            earnings_since_last_run=earnings,
        )
        decision = evaluate_sell_rules(context, sell_rules_policy)
        legacy_text = str(row.get("Deal Breakers", "") or "").strip()
        legacy_flagged = bool(legacy_text) and legacy_text.lower() != "nenhum"
        if legacy_flagged != (decision.action in ("SELL", "TRIM")):
            warnings.append(
                f"{holding.symbol}: diagnóstico-sombra do motor antigo "
                f"diverge da decisão nova (legado: "
                f"{'SELL' if legacy_flagged else 'HOLD'}; motor novo: "
                f"{decision.action}) -- não altera a decisão, só calibração."
            )
        current_weight = current_weights.get(holding.symbol, 0.0)
        if decision.action == "SELL":
            target_weight = 0.0
        elif decision.action == "TRIM":
            target_weight = current_weight * (1.0 - sell_rules_policy.trim_fraction)
        else:
            target_weight = current_weight
        trade_value = (target_weight - current_weight) * portfolio.total_value
        if trade_value < 0:
            released_cash += abs(trade_value)
            turnover_numerator += abs(trade_value)
        reason = decision.reason
        if earnings is True:
            reason += " Houve divulgação de resultado desde o último run."
        actions.append(
            RebalanceAction(
                symbol=holding.symbol,
                action=decision.action,
                current_weight=current_weight,
                target_weight=target_weight,
                target_value=target_weight * portfolio.total_value,
                trade_value=trade_value,
                reason=reason,
                priority={"SELL": 0, "TRIM": 10, "REVISAR": 20, "HOLD": 50}[
                    decision.action
                ],
                triggered_rules=decision.triggered_rules,
                rule_results=tuple(
                    item.to_dict() for item in decision.evaluations
                ),
                missing_data=decision.missing_data,
                baseline_status=decision.baseline_status,
                earnings_since_last_run=decision.earnings_since_last_run,
                score_coverage=decision.score_coverage,
                confidence=decision.confidence,
                legacy_flagged=legacy_flagged,
            )
        )

    if non_portfolio_origin:
        warnings.append(
            "Holdings ignorados por proveniência não confirmada como "
            "'portfolio': " + ", ".join(non_portfolio_origin)
        )
    if quality is not None:
        if not isinstance(quality, PortfolioQualityResult):
            raise TypeError("quality deve ser PortfolioQualityResult.")
        warnings.extend(quality.warnings)
    actions.sort(key=lambda item: (item.priority, item.symbol))
    return RebalancePlan(
        actions=tuple(actions),
        required_cash=0.0,
        released_cash=round(released_cash, 2),
        estimated_turnover=min(
            1.0,
            round(turnover_numerator / portfolio.total_value, 6),
        ),
        warnings=tuple(dict.fromkeys(warnings)),
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

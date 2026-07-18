from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml


RULE_NAMES = (
    "distress",
    "valuation_stretch",
    "fundamental_decay",
    "relative_decay",
)

# Isenções padrão herdadas de config/deal_breakers.json (o deal-breaker
# binário que distress substitui) -- ver docstring de _distress. Mantidas
# em sincronia manual com deal_breakers.json; tests/test_governed_config.py
# trava a equivalência para evitar que voltem a divergir silenciosamente
# (achado real: estas duas ficaram desatualizadas -- faltava "Biotechnology"
# e "Tobacco" -- sem afetar o comportamento hoje só porque
# config/sell_rules.yaml sempre especifica as chaves explicitamente).
DEFAULT_SOLVENCY_EXEMPT_SECTORS = (
    "Utilities",
    "Financial Services",
    "Banks",
    "Insurance",
    "Biotechnology",
)
DEFAULT_LIQUIDITY_EXEMPT_SECTORS = ("Software", "Tobacco")
DEFAULT_NET_DEBT_EBITDA_EXEMPT_SECTORS = ("Biotechnology",)
DEFAULT_F_SCORE_EXEMPT_SECTORS = ("Biotechnology",)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _sector_matches(sector: str, industry: str, terms: Any) -> bool:
    """
    Espelha a semântica linha-a-linha de scoring.investment.exemption_mask
    (substring case-insensitive contra sector OU industry) para o caso de um
    único símbolo -- exemption_mask é vetorizada sobre um DataFrame inteiro
    e não é reaproveitável diretamente aqui.
    """
    if not terms:
        return False
    haystack = f"{sector} | {industry}".strip().lower()
    for term in terms:
        term = str(term).strip().lower()
        if term and term in haystack:
            return True
    return False


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} deve ser um objeto YAML.")
    return value


@dataclass(frozen=True)
class SellRulesPolicy:
    confidence_gate: Mapping[str, Any]
    distress: Mapping[str, Any]
    valuation_stretch: Mapping[str, Any]
    fundamental_decay: Mapping[str, Any]
    relative_decay: Mapping[str, Any]
    escalation: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in (
            "confidence_gate",
            *RULE_NAMES,
            "escalation",
        ):
            object.__setattr__(
                self,
                field_name,
                dict(_mapping(getattr(self, field_name), field_name)),
            )

        score_gate = self.score_coverage_threshold
        confidence_gate = self.confidence_threshold
        percentile = self.relative_percentile_threshold
        if not 0 <= score_gate <= 100 or not 0 <= confidence_gate <= 100:
            raise ValueError("Thresholds de confiança devem estar entre 0 e 100.")
        if not 0 <= percentile <= 100:
            raise ValueError("percentile_threshold deve estar entre 0 e 100.")
        if self.trim_at < 0 or self.sell_at < self.trim_at:
            raise ValueError("Escalação exige 0 <= trim_at <= sell_at.")
        if (
            self.distress_review_at < 1
            or self.distress_sell_at < self.distress_review_at
        ):
            raise ValueError(
                "Distress exige 1 <= distress_review_at <= distress_sell_at."
            )
        if not 0 < self.trim_fraction < 1:
            raise ValueError("trim_fraction deve estar entre 0 e 1.")

    @property
    def score_coverage_threshold(self) -> float:
        return float(self.confidence_gate.get("score_coverage_threshold", 60.0))

    @property
    def confidence_threshold(self) -> float:
        return float(self.confidence_gate.get("confidence_threshold", 60.0))

    @property
    def relative_percentile_threshold(self) -> float:
        return float(self.relative_decay.get("percentile_threshold", 40.0))

    @property
    def trim_at(self) -> int:
        return int(self.escalation.get("trim_at", 1))

    @property
    def sell_at(self) -> int:
        return int(self.escalation.get("sell_at", 2))

    @property
    def trim_fraction(self) -> float:
        return float(self.escalation.get("trim_fraction", 0.50))

    @property
    def distress_review_at(self) -> int:
        return int(self.escalation.get("distress_review_at", 1))

    @property
    def distress_sell_at(self) -> int:
        return int(self.escalation.get("distress_sell_at", 2))

    @property
    def distress_overrides_escalation(self) -> bool:
        return bool(self.escalation.get("distress_overrides_escalation", True))

    @property
    def relative_decay_review_only(self) -> bool:
        return bool(self.relative_decay.get("review_only", True))


def load_sell_rules_policy(path: str | Path) -> SellRulesPolicy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise TypeError("sell_rules.yaml deve conter um objeto.")
    return SellRulesPolicy(
        confidence_gate=_mapping(data.get("confidence_gate", {}), "confidence_gate"),
        distress=_mapping(data.get("distress", {}), "distress"),
        valuation_stretch=_mapping(
            data.get("valuation_stretch", {}), "valuation_stretch"
        ),
        fundamental_decay=_mapping(
            data.get("fundamental_decay", {}), "fundamental_decay"
        ),
        relative_decay=_mapping(data.get("relative_decay", {}), "relative_decay"),
        escalation=_mapping(data.get("escalation", {}), "escalation"),
    )


@dataclass(frozen=True)
class RuleEvaluation:
    name: str
    status: str
    message: str
    evidence_count: int | None = None

    def __post_init__(self) -> None:
        if self.name not in RULE_NAMES:
            raise ValueError(f"Regra desconhecida: {self.name}.")
        if self.status not in {"triggered", "clear", "not_evaluated", "disabled"}:
            raise ValueError(f"Status de regra inválido: {self.status}.")
        if self.evidence_count is None:
            object.__setattr__(
                self,
                "evidence_count",
                1 if self.status == "triggered" else 0,
            )
        elif self.evidence_count < 0:
            raise ValueError("evidence_count não pode ser negativo.")

    @property
    def triggered(self) -> bool:
        return self.status == "triggered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "triggered": self.triggered,
            "message": self.message,
            "evidence_count": self.evidence_count,
        }


@dataclass(frozen=True)
class SellRuleContext:
    symbol: str
    sector: str
    industry: str = ""
    current: Mapping[str, Any] = field(default_factory=dict)
    previous: Mapping[str, Any] | None = None
    baseline_status: str = "first_run"
    score_percentile: float | None = None
    universe_size: int = 0
    universe_scope: str = "reduced"
    missing_data: tuple[str, ...] = field(default_factory=tuple)
    earnings_since_last_run: bool | None = None


@dataclass(frozen=True)
class SellRuleDecision:
    action: str
    evaluations: tuple[RuleEvaluation, ...]
    triggered_rules: tuple[str, ...]
    reason: str
    missing_data: tuple[str, ...]
    score_coverage: float | None
    confidence: float | None
    baseline_status: str
    earnings_since_last_run: bool | None


def _disabled(name: str) -> RuleEvaluation:
    return RuleEvaluation(name, "disabled", f"{name}: desativada por configuração")


def _distress(context: SellRuleContext, policy: SellRulesPolicy) -> RuleEvaluation:
    """
    Risco de solvência/alavancagem -- independente de tendência (ao contrário
    de fundamental_decay). Absorve as 5 condições do deal-breaker binário que
    esta regra substitui (config/deal_breakers.json::apply_deal_breakers) mais
    um piso absoluto de F-Score, cada uma com sua própria isenção setorial
    herdada do sistema antigo; nenhuma condição depende de outra.
    """
    name = "distress"
    config = policy.distress
    if not bool(config.get("enabled", True)):
        return _disabled(name)

    reasons: list[str] = []
    evidence_groups: set[str] = set()
    evaluated_any = False

    altman_exempt = _sector_matches(
        context.sector,
        context.industry,
        config.get("altman_z_exempt_sectors", DEFAULT_SOLVENCY_EXEMPT_SECTORS),
    )
    if not altman_exempt:
        altman = _number(context.current.get("altman_z"))
        if altman is not None:
            evaluated_any = True
            threshold = float(config.get("altman_z_threshold", 1.8))
            if altman < threshold:
                reasons.append(f"altman_z {altman:.2f} < {threshold:.2f}")
                evidence_groups.add("solvency")

    coverage_exempt = _sector_matches(
        context.sector,
        context.industry,
        config.get(
            "interest_coverage_exempt_sectors", DEFAULT_SOLVENCY_EXEMPT_SECTORS
        ),
    )
    if not coverage_exempt:
        coverage = _number(context.current.get("interest_coverage"))
        if coverage is not None:
            evaluated_any = True
            threshold = float(config.get("interest_coverage_threshold", 2.5))
            if coverage < threshold:
                reasons.append(
                    f"interest_coverage {coverage:.2f} < {threshold:.2f}x"
                )
                evidence_groups.add("solvency")

    leverage_exempt = _sector_matches(
        context.sector,
        context.industry,
        config.get(
            "net_debt_ebitda_exempt_sectors",
            DEFAULT_NET_DEBT_EBITDA_EXEMPT_SECTORS,
        ),
    )
    if not leverage_exempt:
        net_debt_ebitda = _number(context.current.get("net_debt_ebitda"))
        if net_debt_ebitda is not None:
            evaluated_any = True
            threshold = float(config.get("net_debt_ebitda_threshold", 4.0))
            if net_debt_ebitda > threshold:
                reasons.append(
                    f"net_debt_ebitda {net_debt_ebitda:.2f} > {threshold:.2f}"
                )
                evidence_groups.add("leverage")

    liquidity_exempt = _sector_matches(
        context.sector,
        context.industry,
        config.get("current_ratio_exempt_sectors", DEFAULT_LIQUIDITY_EXEMPT_SECTORS),
    )
    if not liquidity_exempt:
        current_ratio = _number(
            context.current.get(
                "current_liquidity", context.current.get("current_ratio")
            )
        )
        if current_ratio is not None:
            evaluated_any = True
            threshold = float(config.get("current_ratio_threshold", 1.0))
            if current_ratio < threshold:
                reasons.append(
                    f"current_ratio {current_ratio:.2f} < {threshold:.2f}"
                )
                evidence_groups.add("liquidity")

    short_float = _number(context.current.get("short_float"))
    if short_float is not None:
        evaluated_any = True
        threshold = float(config.get("short_float_threshold", 20.0))
        if short_float > threshold:
            reasons.append(f"short_float {short_float:.1f}% > {threshold:.1f}%")
            evidence_groups.add("market_stress")

    f_score_exempt = _sector_matches(
        context.sector,
        context.industry,
        config.get("f_score_exempt_sectors", DEFAULT_F_SCORE_EXEMPT_SECTORS),
    )
    if not f_score_exempt:
        f_score = _number(
            context.current.get(
                "f_score_annual", context.current.get("piotroski_f")
            )
        )
        if f_score is not None:
            evaluated_any = True
            floor = float(config.get("f_score_floor", 4))
            if f_score < floor:
                reasons.append(f"f_score_annual {f_score:.0f} < piso {floor:.0f}")
                evidence_groups.add("operating_quality")

    if reasons:
        return RuleEvaluation(
            name,
            "triggered",
            "distress: "
            + "; ".join(reasons)
            + f"; evidências independentes={len(evidence_groups)}",
            evidence_count=len(evidence_groups),
        )
    if not evaluated_any:
        return RuleEvaluation(
            name,
            "not_evaluated",
            "distress: não avaliado (todas as condições isentas ou sem dado)",
        )
    return RuleEvaluation(
        name, "clear", "distress: dentro dos limites de solvência/alavancagem"
    )


def _valuation_stretch(
    context: SellRuleContext,
    policy: SellRulesPolicy,
) -> RuleEvaluation:
    name = "valuation_stretch"
    config = policy.valuation_stretch
    if not bool(config.get("enabled", True)):
        return _disabled(name)
    upside_points = _number(context.current.get("target_upside"))
    if upside_points is None:
        return RuleEvaluation(
            name,
            "not_evaluated",
            "valuation_stretch: não avaliado (target_upside ausente)",
        )
    upside_fraction = upside_points / 100.0
    threshold = float(config.get("target_upside_threshold", -0.10))
    if upside_fraction < threshold:
        return RuleEvaluation(
            name,
            "triggered",
            "valuation_stretch: target_upside "
            f"{upside_fraction:.1%} < {threshold:.1%}",
        )
    return RuleEvaluation(
        name,
        "clear",
        f"valuation_stretch: target_upside {upside_fraction:.1%}",
    )


def _fundamental_decay(
    context: SellRuleContext,
    policy: SellRulesPolicy,
) -> RuleEvaluation:
    name = "fundamental_decay"
    config = policy.fundamental_decay
    if not bool(config.get("enabled", True)):
        return _disabled(name)
    if context.baseline_status != "comparable" or context.previous is None:
        label = (
            "model_version diferente; baseline reiniciada"
            if context.baseline_status == "model_version_changed"
            else "sem snapshot anterior comparável"
        )
        return RuleEvaluation(name, "not_evaluated", f"fundamental_decay: {label}")

    current_f = _number(
        context.current.get("f_score_annual", context.current.get("piotroski_f"))
    )
    previous_f = _number(
        context.previous.get("f_score_annual", context.previous.get("piotroski_f"))
    )
    current_roic = _number(context.current.get("roic"))
    previous_roic = _number(context.previous.get("roic"))
    reasons: list[str] = []
    f_threshold = float(config.get("f_score_drop_threshold", 2.0))
    if current_f is not None and previous_f is not None:
        drop = previous_f - current_f
        if drop >= f_threshold:
            reasons.append(f"F-Score caiu {drop:.1f} ponto(s)")
    roic_threshold = float(config.get("roic_drop_pct_threshold", 0.20))
    if (
        current_roic is not None
        and previous_roic is not None
        and previous_roic != 0
    ):
        relative_drop = (previous_roic - current_roic) / abs(previous_roic)
        if relative_drop >= roic_threshold:
            reasons.append(f"ROIC caiu {relative_drop:.1%} em termos relativos")
    if current_f is None and previous_f is None and (
        current_roic is None or previous_roic is None
    ):
        return RuleEvaluation(
            name,
            "not_evaluated",
            "fundamental_decay: não avaliado (F-Score/ROIC sem par comparável)",
        )
    if reasons:
        return RuleEvaluation(
            name, "triggered", "fundamental_decay: " + "; ".join(reasons)
        )
    return RuleEvaluation(name, "clear", "fundamental_decay: sem queda acima do limite")


def _relative_decay(context: SellRuleContext, policy: SellRulesPolicy) -> RuleEvaluation:
    name = "relative_decay"
    config = policy.relative_decay
    if not bool(config.get("enabled", True)):
        return _disabled(name)
    percentile = context.score_percentile
    if percentile is None or context.universe_size <= 0:
        return RuleEvaluation(
            name,
            "not_evaluated",
            "relative_decay: não avaliado (universo confiável vazio)",
        )
    threshold = float(config.get("percentile_threshold", 40.0))
    scope = (
        f"universo reduzido (N={context.universe_size})"
        if context.universe_scope == "reduced"
        else f"universo amplo (N={context.universe_size})"
    )
    if percentile < threshold:
        return RuleEvaluation(
            name,
            "triggered",
            "relative_decay: score no percentil "
            f"{percentile:.1f} de {scope}; oportunidade relativa, não "
            "deterioração da empresa",
        )
    return RuleEvaluation(
        name,
        "clear",
        f"relative_decay: percentil {percentile:.1f} contra {scope}",
    )


def evaluate_sell_rules(
    context: SellRuleContext,
    policy: SellRulesPolicy,
) -> SellRuleDecision:
    score_coverage = _number(
        context.current.get(
            "score_coverage",
            context.current.get("Score Coverage"),
        )
    )
    confidence = _number(
        context.current.get(
            "confidence_score",
            context.current.get("Confidence Score"),
        )
    )
    gated = (
        score_coverage is None
        or confidence is None
        or score_coverage < policy.score_coverage_threshold
        or confidence < policy.confidence_threshold
    )
    evaluations = (
        _distress(context, policy),
        _valuation_stretch(context, policy),
        _fundamental_decay(context, policy),
        _relative_decay(context, policy),
    )
    triggered = tuple(item.name for item in evaluations if item.triggered)
    distress_evaluation = evaluations[0]
    distress_evidence = (
        int(distress_evaluation.evidence_count or 0)
        if distress_evaluation.triggered
        else 0
    )
    review_only_rules = (
        {"relative_decay"} if policy.relative_decay_review_only else set()
    )
    actionable_non_distress = tuple(
        name
        for name in triggered
        if name != "distress" and name not in review_only_rules
    )

    if gated:
        missing = list(context.missing_data)
        if score_coverage is None:
            missing.append("score_coverage")
        if confidence is None:
            missing.append("confidence_score")
        details = ", ".join(dict.fromkeys(missing)) or "cobertura/confiança baixa"
        action = "REVISAR"
        reason = (
            "Gating de confiança: REVISAR antes de qualquer venda; faltando/"
            f"insuficiente: {details}."
        )
    elif (
        distress_evidence >= policy.distress_sell_at
        and policy.distress_overrides_escalation
    ):
        action = "SELL"
        reason = (
            f"distress confirmado por {distress_evidence} evidências "
            "independentes e sobrepõe a escalação configurada."
        )
    elif len(actionable_non_distress) >= policy.sell_at:
        action = "SELL"
        reason = (
            f"{len(actionable_non_distress)} regras acionáveis dispararam: "
            f"{', '.join(actionable_non_distress)}."
        )
    elif distress_evidence >= policy.distress_review_at:
        action = "REVISAR"
        reason = (
            f"Distress preliminar com {distress_evidence} evidência(s) "
            "independente(s); requer confirmação antes de reduzir ou vender."
        )
    elif len(actionable_non_distress) >= policy.trim_at:
        action = "TRIM"
        reason = (
            f"{len(actionable_non_distress)} regra acionável disparou: "
            f"{', '.join(actionable_non_distress)}."
        )
    elif triggered:
        action = "REVISAR"
        reason = (
            "Sinal exclusivamente relativo/informativo; revisar sem redução "
            "automática da posição."
        )
    else:
        action = "HOLD"
        reason = "Nenhuma regra de venda disparou nesta execução."

    return SellRuleDecision(
        action=action,
        evaluations=evaluations,
        triggered_rules=triggered,
        reason=reason,
        missing_data=tuple(dict.fromkeys(context.missing_data)),
        score_coverage=score_coverage,
        confidence=confidence,
        baseline_status=context.baseline_status,
        earnings_since_last_run=context.earnings_since_last_run,
    )


def score_percentiles(
    frame: pd.DataFrame,
    policy: SellRulesPolicy,
) -> tuple[dict[str, float], int, str]:
    if frame.empty or "symbol" not in frame.columns or "Investment Score" not in frame.columns:
        return {}, 0, "reduced"
    coverage_col = "Score Coverage" if "Score Coverage" in frame.columns else "Confidence Score"
    confidence_col = "Confidence Score"
    if coverage_col not in frame.columns or confidence_col not in frame.columns:
        return {}, 0, "reduced"
    scores = pd.to_numeric(frame["Investment Score"], errors="coerce")
    coverage = pd.to_numeric(frame[coverage_col], errors="coerce")
    confidence = pd.to_numeric(frame[confidence_col], errors="coerce")
    mask = (
        scores.notna()
        & coverage.ge(policy.score_coverage_threshold)
        & confidence.ge(policy.confidence_threshold)
    )
    eligible = frame.loc[mask, ["symbol"]].copy()
    eligible["score"] = scores.loc[mask]
    if eligible.empty:
        return {}, 0, "reduced"
    eligible["percentile"] = eligible["score"].rank(method="average", pct=True) * 100
    result = {
        str(row.symbol).strip().upper(): round(float(row.percentile), 1)
        for row in eligible.itertuples()
    }
    origins = set(frame.get("origin", pd.Series(dtype=str)).astype(str).str.lower())
    scope = "broad" if "universe" in origins else "reduced"
    return result, len(eligible), scope

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from analytics.history import earnings_between_runs
from watchlist.models import WatchlistEntry, WatchlistTriggerResult

EARNINGS_PASSED = "earnings_passed"

# Whitelist deliberada: só campos já persistidos na tabela `snapshots`
# (storage/history_db.py), logo sempre comparáveis run-a-run. Preço
# (price/current_price/target_price/...) fica de fora de propósito -- é
# escopo da corretora, não do Atlas (ver contexto do PR-021). Um teste
# negativo trava isso.
FIELD_ALIASES: dict[str, str] = {
    "score": "investment_score",
    "investment_score": "investment_score",
    "opportunity": "opportunity_score",
    "opportunity_score": "opportunity_score",
    "confidence": "confidence_score",
    "confidence_score": "confidence_score",
    "business": "business_score",
    "business_score": "business_score",
    "valuation": "valuation_score",
    "valuation_score": "valuation_score",
    "financial": "financial_score",
    "financial_score": "financial_score",
    "timing": "timing_score",
    "timing_score": "timing_score",
    "f_score": "f_score_annual",
    "f_score_annual": "f_score_annual",
    "roic": "roic",
    "altman_z": "altman_z",
    "interest_coverage": "interest_coverage",
    "target_upside": "target_upside",
    "score_coverage": "score_coverage",
}

_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}

_CONDITION_PATTERN = re.compile(
    r"^\s*([a-zA-Z_]+)\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$"
)


class InvalidTriggerConditionError(ValueError):
    """Condição de trigger com sintaxe inválida ou campo fora do whitelist."""


@dataclass(frozen=True)
class TriggerCondition:
    raw_text: str
    kind: str  # "comparison" | "earnings_passed"
    field: str | None = None
    comparator: str | None = None
    threshold: float | None = None


def parse_trigger_condition(text: str) -> TriggerCondition:
    """
    Analisa `<campo> <operador> <valor>` (ex.: "score > 75", "f_score >= 7")
    ou o literal `earnings_passed`. Nunca usa eval() -- só regex + whitelist.
    Levanta InvalidTriggerConditionError com a sintaxe inválida ou o campo
    desconhecido, nunca falha silenciosamente.
    """
    stripped = text.strip()
    if not stripped:
        raise InvalidTriggerConditionError("condição vazia.")

    if stripped.lower() == EARNINGS_PASSED:
        return TriggerCondition(raw_text=stripped, kind="earnings_passed")

    match = _CONDITION_PATTERN.match(stripped)
    if not match:
        raise InvalidTriggerConditionError(
            f"sintaxe inválida: {text!r}. Use '<campo> <operador> <valor>' "
            f"(operadores: {', '.join(_COMPARATORS)}) ou '{EARNINGS_PASSED}'."
        )

    field_token, comparator, value_text = match.groups()
    canonical_field = FIELD_ALIASES.get(field_token.strip().lower())
    if canonical_field is None:
        raise InvalidTriggerConditionError(
            f"campo desconhecido: {field_token!r}. Campos aceitos: "
            + ", ".join(sorted(set(FIELD_ALIASES.values())))
        )

    return TriggerCondition(
        raw_text=stripped,
        kind="comparison",
        field=canonical_field,
        comparator=comparator,
        threshold=float(value_text),
    )


_SCORE_DISPLAY_TO_SNAKE = {
    "Investment Score": "investment_score",
    "Opportunity Score": "opportunity_score",
    "Confidence Score": "confidence_score",
    "Business Score": "business_score",
    "Valuation Score": "valuation_score",
    "Financial Score": "financial_score",
    "Timing Score": "timing_score",
}


def normalize_current_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Alia as colunas Title Case do DataFrame analisado ("Investment Score",
    ...) para os mesmos nomes snake_case usados pela tabela `snapshots`
    (investment_score, ...) -- necessário para comparar o valor deste run
    com o valor persistido do run anterior sob o MESMO nome de campo.
    Colunas já snake_case (altman_z, roic, f_score_annual, ...) vêm direto
    do provider/fundamentals e passam sem alteração.
    """
    normalized = dict(row)
    for display_name, snake_name in _SCORE_DISPLAY_TO_SNAKE.items():
        if display_name in row:
            normalized[snake_name] = row[display_name]
    normalized.setdefault(
        "score_coverage",
        row.get("Score Coverage", row.get("Confidence Score")),
    )
    return normalized


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _evaluate_comparison(
    condition: TriggerCondition,
    row: Mapping[str, Any] | None,
) -> bool | None:
    if row is None:
        return None
    value = _number(row.get(condition.field))
    if value is None:
        return None
    return _COMPARATORS[condition.comparator](value, condition.threshold)


def evaluate_watchlist_triggers(
    entries: Iterable[WatchlistEntry],
    current_by_symbol: Mapping[str, Mapping[str, Any]],
    *,
    previous_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | datetime | pd.Timestamp | None = None,
) -> tuple[WatchlistTriggerResult, ...]:
    """
    Avalia cada entrada da watchlist neste run. Dispara ("triggered") só na
    TRANSIÇÃO -- condição falsa no run anterior e verdadeira neste. Sem
    baseline comparável para o símbolo (primeiro run ou model_version
    diferente), nunca dispara -- não sabemos se já era verdade antes, então
    tratar como disparo seria um falso positivo. Não popula aging (idade/
    last_triggered_at/cleanup_suggested) -- isso é responsabilidade de
    watchlist.aging.attach_aging, numa segunda passada.
    """
    previous_by_symbol = previous_by_symbol or {}
    results: list[WatchlistTriggerResult] = []

    for entry in entries:
        condition_text = entry.trigger_condition
        if not condition_text:
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition="",
                    status="no_condition",
                    message="Acompanhamento passivo -- sem condição definida.",
                )
            )
            continue

        try:
            condition = parse_trigger_condition(condition_text)
        except InvalidTriggerConditionError as exc:
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition=condition_text,
                    status="invalid_condition",
                    message=f"Condição inválida: {exc}",
                )
            )
            continue

        current_row = current_by_symbol.get(entry.symbol)
        previous_row = previous_by_symbol.get(entry.symbol)
        symbol_baseline = baseline_status
        if baseline_status == "comparable" and previous_row is None:
            symbol_baseline = "first_run"

        if condition.kind == "earnings_passed":
            currently_true = earnings_between_runs(
                (current_row or {}).get("earnings_date"),
                previous_run_at,
                current_run_at,
            )
            if currently_true is None:
                results.append(
                    WatchlistTriggerResult(
                        symbol=entry.symbol,
                        trigger_condition=condition_text,
                        status="not_evaluated",
                        message=(
                            "earnings_passed: não avaliado (sem data de "
                            "earnings ou sem run anterior)."
                        ),
                    )
                )
            elif currently_true:
                results.append(
                    WatchlistTriggerResult(
                        symbol=entry.symbol,
                        trigger_condition=condition_text,
                        status="triggered",
                        message=(
                            "earnings_passed: houve divulgação de resultado "
                            "desde o último run."
                        ),
                    )
                )
            else:
                results.append(
                    WatchlistTriggerResult(
                        symbol=entry.symbol,
                        trigger_condition=condition_text,
                        status="clear",
                        message="earnings_passed: nenhuma divulgação nova.",
                    )
                )
            continue

        if symbol_baseline != "comparable":
            label = (
                "model_version diferente; baseline reiniciada"
                if symbol_baseline == "model_version_changed"
                else "sem run anterior comparável"
            )
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition=condition_text,
                    status="not_evaluated",
                    message=f"{condition.raw_text}: {label}.",
                )
            )
            continue

        currently_true = _evaluate_comparison(condition, current_row)
        previously_true = _evaluate_comparison(condition, previous_row)

        if currently_true is None:
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition=condition_text,
                    status="not_evaluated",
                    message=f"{condition.raw_text}: dado ausente neste run.",
                )
            )
        elif currently_true and not previously_true:
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition=condition_text,
                    status="triggered",
                    message=f"{condition.raw_text}: passou a valer neste run.",
                )
            )
        else:
            results.append(
                WatchlistTriggerResult(
                    symbol=entry.symbol,
                    trigger_condition=condition_text,
                    status="clear",
                    message=f"{condition.raw_text}: não disparado.",
                )
            )

    return tuple(results)

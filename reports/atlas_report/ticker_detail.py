from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from analytics.history import build_metric_history
from reports.atlas_report.formulas import (
    RULE_DEFINITIONS,
    RULE_STATUS_LABELS,
    formula_for,
    interpret_feature,
    inputs_for,
)
from reports.atlas_report.one_pager import compute_symbol_contributions
from reports.atlas_report.svg import sparkline_svg

# Colunas do snapshot que o histórico consegue de fato servir hoje --
# espelha storage/history_db.py::_create_tables (tabela snapshots) e
# STATUS.md secao 4. Fora desta lista, "histórico pendente: schema de
# snapshot" (PR-020 não gravou a coluna).
_HISTORY_AVAILABLE_COLUMNS = frozenset(
    {
        "investment_score", "business_score", "valuation_score",
        "financial_score", "timing_score", "opportunity_score",
        "confidence_score", "altman_z", "interest_coverage",
        "target_upside", "f_score_annual", "roic", "score_coverage",
    }
)

_HISTORY_LABELS = {
    "investment_score": "Investment Score",
    "roic": "ROIC",
    "f_score_annual": "F-Score",
    "interest_coverage": "Interest Coverage",
    "target_upside": "Target Upside",
    "altman_z": "Altman Z",
    "score_coverage": "Score Coverage",
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


@dataclass(frozen=True)
class FeatureDetail:
    label: str
    factor: str
    column: str
    value: float
    percentile: float
    contribution: float
    formula: str
    inputs: tuple[tuple[str, str], ...]
    interpretation: str | None


@dataclass(frozen=True)
class SellRuleDetail:
    name: str
    status: str
    status_label: str
    message: str
    definition: str


@dataclass(frozen=True)
class MetricHistory:
    column: str
    label: str
    available: bool
    points: tuple[tuple[str, float], ...]
    sparkline: str


@dataclass(frozen=True)
class ThesisDetail:
    text: str
    entry_date: str | None
    thesis_updated_at: str | None
    age_months: float | None
    attention: str | None


@dataclass(frozen=True)
class TickerDetail:
    symbol: str
    name: str
    sector: str
    origin: str
    anchor_id: str
    action: str
    action_engine: str
    action_reason: str
    score: float | None
    score_delta: float | None
    coverage: float | None
    average_price: float | None
    current_price: float | None
    unrealized_return: float | None
    positive_features: tuple[FeatureDetail, ...] = field(default_factory=tuple)
    negative_features: tuple[FeatureDetail, ...] = field(default_factory=tuple)
    sell_rules_available: bool = False
    sell_rules: tuple[SellRuleDetail, ...] = field(default_factory=tuple)
    histories: tuple[MetricHistory, ...] = field(default_factory=tuple)
    thesis: ThesisDetail | None = None


def anchor_id(symbol: str) -> str:
    return f"ticker-{symbol.strip().upper()}"


def _resolved_inputs(
    column: str,
    row: Mapping[str, Any],
) -> tuple[tuple[str, str], ...]:
    resolved = []
    for label, candidate_column in inputs_for(column):
        raw = row.get(candidate_column) if isinstance(row, Mapping) else None
        value = _number(raw)
        resolved.append((label, f"{value:,.4g}" if value is not None else "pendente"))
    return tuple(resolved)


def _build_feature_details(
    contributions: tuple[Any, ...],
    current: Mapping[str, Any],
) -> tuple[FeatureDetail, ...]:
    details = []
    for item in contributions:
        details.append(
            FeatureDetail(
                label=item.label,
                factor=item.factor,
                column=item.column,
                value=item.value,
                percentile=item.percentile,
                contribution=item.signed_contribution,
                formula=formula_for(item.column),
                inputs=_resolved_inputs(item.column, current),
                interpretation=interpret_feature(item.column, item.value),
            )
        )
    return tuple(details)


def _build_sell_rules(rule_results: tuple[Mapping[str, Any], ...]) -> tuple[SellRuleDetail, ...]:
    details = []
    for item in rule_results:
        name = str(item.get("name", ""))
        status = str(item.get("status", ""))
        details.append(
            SellRuleDetail(
                name=name,
                status=status,
                status_label=RULE_STATUS_LABELS.get(status, status or "pendente"),
                message=str(item.get("message", "") or "razão: motor pendente"),
                definition=RULE_DEFINITIONS.get(name, "definição: pendente"),
            )
        )
    return tuple(details)


def _build_histories(
    score_history: pd.DataFrame,
    symbol: str,
    columns: tuple[str, ...],
) -> tuple[MetricHistory, ...]:
    histories = []
    for column in columns:
        label = _HISTORY_LABELS.get(column, column)
        available = column in _HISTORY_AVAILABLE_COLUMNS
        points: tuple[tuple[str, float], ...] = ()
        spark = ""
        if available:
            metric_history = build_metric_history(score_history, symbol, column)
            if not metric_history.empty:
                points = tuple(
                    (str(row["snapshot_date"])[:10], round(float(row[column]), 4))
                    for _, row in metric_history.iterrows()
                )
                spark = sparkline_svg([value for _, value in points])
        histories.append(
            MetricHistory(
                column=column,
                label=label,
                available=available,
                points=points,
                sparkline=spark,
            )
        )
    return tuple(histories)


def _age_months(date_value: str | None, as_of: pd.Timestamp) -> float | None:
    if not date_value:
        return None
    parsed = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(parsed):
        return None
    delta_days = (as_of - parsed).days
    if delta_days < 0:
        return None
    return round(delta_days / 30.44, 1)


def _build_thesis(
    holding: Mapping[str, Any] | None,
    sell_rules: tuple[SellRuleDetail, ...],
    as_of: pd.Timestamp,
) -> ThesisDetail | None:
    if not holding:
        return None
    text = str(holding.get("thesis") or "").strip()
    if not text:
        return None
    thesis_updated_at = holding.get("thesis_updated_at")
    entry_date = holding.get("entry_date")
    reference_date = thesis_updated_at or entry_date
    attention = None
    for rule in sell_rules:
        if rule.name == "fundamental_decay" and rule.status == "triggered":
            attention = rule.message
            break
    return ThesisDetail(
        text=text,
        entry_date=str(entry_date) if entry_date else None,
        thesis_updated_at=str(thesis_updated_at) if thesis_updated_at else None,
        age_months=_age_months(
            str(reference_date) if reference_date else None, as_of
        ),
        attention=attention,
    )


def build_ticker_detail(
    *,
    symbol: str,
    name: str,
    sector: str,
    origin: str,
    action: str,
    action_engine: str,
    action_reason: str,
    score: float | None,
    score_delta: float | None,
    coverage: float | None,
    current: Mapping[str, Any],
    df: pd.DataFrame,
    rule_results: tuple[Mapping[str, Any], ...],
    holding: Mapping[str, Any] | None,
    score_history: pd.DataFrame,
    features_path: Path,
    model_path: Path | None,
    as_of: pd.Timestamp,
) -> TickerDetail:
    positive, negative = compute_symbol_contributions(df, symbol, features_path, model_path)
    positive_details = _build_feature_details(positive, current)
    negative_details = _build_feature_details(negative, current)
    sell_rules = _build_sell_rules(rule_results)

    history_columns = ("investment_score",) + tuple(
        dict.fromkeys(
            item.column
            for item in (*positive, *negative)
        )
    )
    histories = _build_histories(score_history, symbol, history_columns)

    average_price = _number(holding.get("average_price")) if holding else None
    current_price = _number(holding.get("current_price")) if holding else None
    unrealized_return = _number(holding.get("unrealized_return")) if holding else None

    return TickerDetail(
        symbol=symbol,
        name=name,
        sector=sector,
        origin=origin,
        anchor_id=anchor_id(symbol),
        action=action,
        action_engine=action_engine,
        action_reason=action_reason,
        score=score,
        score_delta=score_delta,
        coverage=coverage,
        average_price=average_price,
        current_price=current_price,
        unrealized_return=unrealized_return,
        positive_features=positive_details,
        negative_features=negative_details,
        sell_rules_available=bool(rule_results),
        sell_rules=sell_rules,
        histories=histories,
        thesis=_build_thesis(holding, sell_rules, as_of),
    )

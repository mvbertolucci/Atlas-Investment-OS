from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.feature_audit import FeatureBinding, collect_model_features
from analytics.history import build_metric_history
from factors.engine import get_factor_features, load_yaml, pct_rank
from factors.valuation import resolve_valuation_features


@dataclass(frozen=True)
class FeatureContribution:
    label: str
    factor: str
    column: str
    value: float
    percentile: float
    signed_contribution: float


def _higher_is_better(
    binding: FeatureBinding,
    raw_features: dict[str, Any],
) -> bool:
    if binding.factor == "valuation":
        resolved = resolve_valuation_features(raw_features)
        cfg = resolved.get(binding.name, {})
        return bool(cfg.get("higher", True))
    cfg = get_factor_features(raw_features, binding.factor).get(binding.name, {})
    if not isinstance(cfg, dict):
        return True
    return bool(cfg.get("higher_is_better", True))


def compute_symbol_contributions(
    df: pd.DataFrame,
    symbol: str,
    features_path: Path,
    model_path: Path | None = None,
) -> tuple[tuple[FeatureContribution, ...], tuple[FeatureContribution, ...]]:
    """
    Decompõe o Investment Score de um símbolo nas 3 maiores contribuições
    positivas e negativas nomeadas. Reaproveita EXATAMENTE o percentil que o
    score de fato usa (factors.engine.pct_rank + config/features.yaml::
    higher_is_better) combinado com o peso estrutural já existente
    (FeatureBinding.contribution) -- nenhuma fórmula nova, só recombinação.

    signed_contribution = (percentil - 50) * contribution, em pontos do
    score 0-100: um feature no percentil 90 com contribution 0.05 empurra a
    ação +2.0 pontos; no percentil 10, -2.0 pontos.
    """
    bindings = collect_model_features(features_path, model_path)
    raw_features = load_yaml(features_path)
    normalized_symbol = symbol.strip().upper()
    symbols = df["symbol"].astype(str).str.strip().str.upper()
    matches = df.index[symbols == normalized_symbol]
    if len(matches) == 0:
        return (), ()
    position = matches[0]

    contributions: list[FeatureContribution] = []
    for binding in bindings:
        if binding.column not in df.columns:
            continue
        raw_value = df.loc[position, binding.column]
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value != value:
            continue

        higher = _higher_is_better(binding, raw_features)
        percentile = float(pct_rank(df, binding.column, higher).loc[position])
        signed = round((percentile - 50.0) * binding.contribution, 4)

        contributions.append(
            FeatureContribution(
                label=binding.label,
                factor=binding.factor,
                column=binding.column,
                value=value,
                percentile=round(percentile, 1),
                signed_contribution=signed,
            )
        )

    positive = tuple(
        sorted(
            (item for item in contributions if item.signed_contribution > 0),
            key=lambda item: item.signed_contribution,
            reverse=True,
        )[:3]
    )
    negative = tuple(
        sorted(
            (item for item in contributions if item.signed_contribution < 0),
            key=lambda item: item.signed_contribution,
        )[:3]
    )
    return positive, negative


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""))


def _sparkline_svg(values: list[float], *, width: int = 220, height: int = 40) -> str:
    """SVG inline simples -- sem JS, sem dependência externa."""
    if len(values) < 2:
        return '<p class="section-empty">Histórico insuficiente para gráfico.</p>'
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{index * step:.1f},{height - ((value - low) / span * height):.1f}"
        for index, value in enumerate(values)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'role="img" aria-label="Histórico de score">'
        f'<polyline points="{points}" fill="none" stroke="currentColor" '
        'stroke-width="2" /></svg>'
    )


def render_one_pager(
    *,
    symbol: str,
    company_name: str,
    investment_score: float | None,
    positive: tuple[FeatureContribution, ...],
    negative: tuple[FeatureContribution, ...],
    score_history: pd.DataFrame,
    thesis: str = "",
) -> str:
    def _rows(items: tuple[FeatureContribution, ...]) -> str:
        if not items:
            return '<tr><td colspan="3" class="section-empty">Nenhuma.</td></tr>'
        return "\n".join(
            f"<tr><td>{_e(item.label)}</td><td>{item.value:.2f}</td>"
            f"<td>{item.signed_contribution:+.2f}</td></tr>"
            for item in items
        )

    history_values = (
        pd.to_numeric(
            score_history["investment_score"], errors="coerce"
        )
        .dropna()
        .tolist()
        if not score_history.empty and "investment_score" in score_history.columns
        else []
    )
    sparkline = _sparkline_svg(history_values)

    thesis_html = (
        f'<div class="card"><strong>Tese registrada</strong><br>{_e(thesis)}</div>'
        if thesis
        else '<p class="section-empty">Sem tese registrada (não é uma posição real).</p>'
    )

    score_text = f"{investment_score:.1f}" if investment_score is not None else "—"

    body = f"""
<h1>{_e(symbol)} — {_e(company_name)}</h1>
<p class="meta">Investment Score: {score_text}</p>

<h2>Maiores contribuições positivas</h2>
<div class="table-scroll"><table>
<thead><tr><th>Feature</th><th>Valor</th><th>Contribuição</th></tr></thead>
<tbody>{_rows(positive)}</tbody>
</table></div>

<h2>Maiores contribuições negativas</h2>
<div class="table-scroll"><table>
<thead><tr><th>Feature</th><th>Valor</th><th>Contribuição</th></tr></thead>
<tbody>{_rows(negative)}</tbody>
</table></div>

<h2>Histórico de score</h2>
{sparkline}

<h2>Tese</h2>
{thesis_html}
"""
    return body

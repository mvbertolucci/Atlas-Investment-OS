from __future__ import annotations

from html import escape

from reports.atlas_report.broad_screener import BroadScreenerSummary
from reports.atlas_report.context import ReportContext
from reports.atlas_report.ticker_detail import FeatureDetail, SellRuleDetail, TickerDetail

_STYLE = """
:root {
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #6b7280;
  --border: #e5e7eb;
  --card-bg: #f9fafb;
  --hold: #16a34a;
  --hold-bg: #dcfce7;
  --revisar: #a16207;
  --revisar-bg: #fef9c3;
  --sell: #b91c1c;
  --sell-bg: #fee2e2;
  --acompanhar: #1d4ed8;
  --acompanhar-bg: #dbeafe;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111827;
    --fg: #f3f4f6;
    --muted: #9ca3af;
    --border: #374151;
    --card-bg: #1f2937;
    --hold-bg: #14532d;
    --revisar-bg: #713f12;
    --sell-bg: #7f1d1d;
    --acompanhar-bg: #1e3a8a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 1rem;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.45;
}
h1 { font-size: 1.3rem; margin: 0 0 0.25rem; }
h2 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
.meta { color: var(--muted); font-size: 0.85rem; }
.section-empty { color: var(--muted); font-style: italic; }
.table-scroll { overflow-x: auto; max-width: 100%; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 0.85rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); overflow-wrap: break-word; }
th { color: var(--muted); font-weight: 600; }
.pill { display: inline-block; padding: 0.1rem 0.6rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.pill-hold { color: var(--hold); background: var(--hold-bg); }
.pill-revisar { color: var(--revisar); background: var(--revisar-bg); }
.pill-trim, .pill-sell { color: var(--sell); background: var(--sell-bg); }
.pill-acompanhar { color: var(--acompanhar); background: var(--acompanhar-bg); }
.informational-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.5rem 0.8rem; margin-bottom: 0.4rem; font-size: 0.85rem; }
.informational-card .features { color: var(--muted); font-size: 0.8rem; margin-top: 0.2rem; }
.delta-up { color: var(--hold); }
.delta-down { color: var(--sell); }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; }
.card .engine { color: var(--muted); font-size: 0.75rem; }
.footer { margin-top: 2rem; color: var(--muted); font-size: 0.78rem; }
.alert { color: var(--sell); background: var(--sell-bg); border-radius: 0.4rem; padding: 0.4rem 0.6rem; margin: 0.25rem 0; font-size: 0.82rem; }
.symbol-link { color: inherit; text-decoration: underline; text-decoration-style: dotted; }
.ticker-detail { border-top: 2px solid var(--border); padding-top: 0.75rem; margin-top: 1.5rem; }
.ticker-detail h3 { margin: 0 0 0.15rem; }
.ticker-detail .card > summary { cursor: pointer; font-weight: 600; }
.ticker-detail .card { margin-bottom: 0.4rem; }
.history-grid { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.history-grid .card { flex: 1 1 220px; }
"""

_PILL_CLASS = {
    "HOLD": "pill-hold",
    "REVISAR": "pill-revisar",
    "TRIM": "pill-trim",
    "SELL": "pill-sell",
    "ACOMPANHAR": "pill-acompanhar",
}


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""))


def _pill(action: str) -> str:
    css_class = _PILL_CLASS.get(action, "pill-revisar")
    return f'<span class="pill {css_class}">{_e(action)}</span>'


def _delta_html(delta: float | None) -> str:
    if delta is None:
        return '<span class="meta">—</span>'
    arrow = "▲" if delta > 0 else "▼" if delta < 0 else "→"
    css_class = "delta-up" if delta > 0 else "delta-down" if delta < 0 else ""
    return f'<span class="{css_class}">{arrow} {delta:+.1f}</span>'


def _not_included(label: str) -> str:
    return f'<p class="section-empty">{_e(label)} não incluído neste run.</p>'


def render_header(context: ReportContext) -> str:
    previous = context.previous_snapshot_date or "sem run anterior"
    coverage = (
        f"{context.average_coverage:.1f}%"
        if context.average_coverage is not None
        else "—"
    )
    return f"""
<h1>Atlas Decision Intelligence — {_e(context.mode)}</h1>
<p class="meta">
  Run atual: {_e(context.snapshot_date)} · Run anterior: {_e(previous)} ·
  {context.symbol_count} símbolo(s) · coverage médio {coverage}
</p>
"""


def render_required_actions(context: ReportContext) -> str:
    if not context.required_actions:
        return "<h2>Ações requeridas</h2>" + _not_included(
            "Nenhuma ação requerida"
        ).replace("não incluído neste run.", "")
    cards = "\n".join(
        f'<div class="card"><strong>{_e(item.symbol)}</strong> '
        f'{_pill(item.label)} <span class="engine">[{_e(item.engine)}]</span>'
        f'<br>{_e(item.message)}</div>'
        for item in context.required_actions
    )
    return f"<h2>Ações requeridas</h2>\n{cards}"


def render_informational_signals(context: ReportContext) -> str:
    """ACOMPANHAR: nunca esconde o sinal, mas nunca o mistura com Ações
    Requeridas -- seção deliberadamente mais leve, sempre com o mesmo
    detalhe numérico (top contribuições negativas) que já existe na seção
    de detalhe por ativo, nunca um rótulo vazio."""
    if not context.informational_signals:
        return "<h2>Sinais informativos</h2>" + _not_included(
            "Nenhum sinal informativo"
        ).replace("não incluído neste run.", "")
    cards = "\n".join(
        f'<div class="informational-card">'
        f'<a class="symbol-link" href="#{_e(item.anchor_id)}"><strong>{_e(item.symbol)}</strong></a> '
        f'{_pill("ACOMPANHAR")} {_e(item.name)}'
        f'<br>{_e(item.message)}'
        + (
            '<div class="features">'
            + " · ".join(
                f"{_e(feature.label)} (percentil {feature.percentile:.0f})"
                for feature in item.top_negative_features
            )
            + "</div>"
            if item.top_negative_features
            else ""
        )
        + "</div>"
        for item in context.informational_signals
    )
    return f"<h2>Sinais informativos</h2>\n{cards}"


def render_portfolio(context: ReportContext) -> str:
    if not context.portfolio_included:
        if context.portfolio_blocked_reason:
            return (
                "<h2>Carteira</h2>"
                f'<p class="section-empty">⚠ {_e(context.portfolio_blocked_reason)}</p>'
            )
        return "<h2>Carteira</h2>" + _not_included("Carteira")

    changed = [row for row in context.portfolio_rows if row.has_state_change]
    unchanged_count = len(context.portfolio_rows) - len(changed)

    rows_html = "\n".join(
        "<tr>"
        f'<td><a class="symbol-link" href="#{_e(row.anchor_id)}">{_e(row.symbol)}</a></td>'
        f"<td>{_e(row.name)}</td>"
        f"<td>{row.score:.1f}" + ("</td>" if row.score is not None else "—</td>")
        + f"<td>{_delta_html(row.score_delta)}</td>"
        + (f"<td>{row.coverage:.1f}%</td>" if row.coverage is not None else "<td>—</td>")
        + f"<td>{_pill(row.action)}</td>"
        + f"<td>{_e(', '.join(row.triggered_rules) or row.reason)}</td>"
        "</tr>"
        for row in changed
    )

    summary_row = (
        f'<tr><td colspan="7" class="meta">{unchanged_count} posição(ões) '
        "sem mudança de estado (HOLD, sem regra disparada)</td></tr>"
        if unchanged_count
        else ""
    )

    warnings_html = (
        "".join(f"<p class=\"meta\">⚠ {_e(w)}</p>" for w in context.portfolio_warnings)
    )

    return f"""
<h2>Carteira</h2>
{warnings_html}
<div class="table-scroll">
<table>
<colgroup>
<col style="width:12%"><col style="width:20%"><col style="width:10%">
<col style="width:10%"><col style="width:10%"><col style="width:13%">
<col style="width:25%">
</colgroup>
<thead><tr><th>Símbolo</th><th>Nome</th><th>Score</th><th>Δ</th>
<th>Coverage</th><th>Decisão</th><th>Regra ativa</th></tr></thead>
<tbody>
{rows_html}
{summary_row}
</tbody>
</table>
</div>
"""


def render_watchlist(context: ReportContext) -> str:
    if not context.watchlist_included:
        return "<h2>Watchlist</h2>" + _not_included("Watchlist")
    if not context.watchlist_rows:
        return "<h2>Watchlist</h2>" + '<p class="section-empty">Watchlist vazia.</p>'

    rows_html = "\n".join(
        "<tr>"
        f'<td><a class="symbol-link" href="#{_e(row.anchor_id)}">{_e(row.symbol)}</a></td>'
        f"<td>{_e(row.name)}</td>"
        f"<td>{_e(row.effective_state)}</td>"
        f"<td>{_e(row.analytical_origin)}</td>"
        + (f"<td>#{row.entry_rank}</td>" if row.entry_rank is not None else "<td>—</td>")
        + (f"<td>{row.entry_score:.1f}</td>" if row.entry_score is not None else "<td>—</td>")
        + f"<td>{_e(row.trigger_condition) or 'acompanhamento passivo'}</td>"
        + (f"<td>{row.score:.1f}</td>" if row.score is not None else "<td>—</td>")
        + (f"<td>{row.age_days}d</td>" if row.age_days is not None else "<td>—</td>")
        + (
            '<td><span class="pill pill-sell">DISPAROU</span></td>'
            if row.triggered_this_run
            else f"<td>{_e(row.status)}</td>"
        )
        + (
            '<td>sugerido</td>'
            if row.cleanup_suggested
            else "<td>—</td>"
        )
        + (f"<td>{_e(row.review_due_at)}</td>" if row.review_due_at else "<td>—</td>")
        + (f"<td>{_e(row.discard_condition)}</td>" if row.discard_condition else "<td>—</td>")
        + "</tr>"
        for row in context.watchlist_rows
    )
    return f"""
<h2>Watchlist</h2>
<div class="table-scroll">
<table>
<colgroup>
<col><col><col><col><col><col><col><col><col><col><col><col><col>
</colgroup>
<thead><tr><th>Símbolo</th><th>Nome</th><th>Estado</th><th>Origem</th>
<th>Rank entrada</th><th>Score entrada</th><th>Condição promoção</th>
<th>Score atual</th><th>Idade</th><th>Trigger</th><th>Limpeza?</th>
<th>Revisar em</th><th>Condição descarte</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
"""


def render_watchlist_proposals(context: ReportContext) -> str:
    if not context.watchlist_proposals:
        return "<h2>Sugestões para a watchlist</h2>" + _not_included(
            "Sugestões para a watchlist"
        )
    rows_html = "\n".join(
        "<tr>"
        f"<td>#{proposal.candidate_rank}</td>"
        f"<td>{_e(proposal.symbol)}</td>"
        f"<td>{_e(proposal.name)}</td>"
        f"<td>{_e(proposal.sector)}</td>"
        + (
            f"<td>{proposal.investment_score:.1f}</td>"
            if proposal.investment_score is not None
            else "<td>—</td>"
        )
        + (
            f"<td><code>{_e(proposal.suggested_condition)}</code></td>"
            if proposal.suggested_condition
            else "<td>—</td>"
        )
        + f"<td>{_e(proposal.condition_rationale)}</td>"
        "</tr>"
        for proposal in context.watchlist_proposals
    )
    return f"""
<h2>Sugestões para a watchlist</h2>
<p class="meta">Candidatos do screener (confiança ≥ 70, sem deal breaker) fora da
carteira e da watchlist, diversificados por setor. Apenas sugestão — nada é
gravado. Para incluir: <code>python -m watchlist.promote SÍMBOLO "motivo"</code>
e defina a condição sugerida.</p>
<div class="table-scroll">
<table>
<colgroup>
<col style="width:8%"><col style="width:10%"><col style="width:20%">
<col style="width:16%"><col style="width:8%"><col style="width:14%">
<col style="width:24%">
</colgroup>
<thead><tr><th>Rank</th><th>Símbolo</th><th>Nome</th><th>Setor</th>
<th>Score</th><th>Trigger sugerido</th><th>Por quê</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
"""


def render_watchlist_auto_curation(context: ReportContext) -> str:
    data = context.watchlist_auto_curation
    if data is None:
        return "<h2>Curadoria Automática da Watchlist</h2>" + _not_included(
            "Curadoria Automática da Watchlist"
        )
    if not data.get("enabled"):
        return (
            "<h2>Curadoria Automática da Watchlist</h2>"
            '<p class="section-empty">Desabilitada neste run '
            "(<code>config/watchlist_auto.yaml::enabled: false</code>).</p>"
        )

    included = data.get("included") or []
    excluded = data.get("excluded") or []
    if not included and not excluded:
        return (
            "<h2>Curadoria Automática da Watchlist</h2>"
            '<p class="section-empty">Nenhuma inclusão ou exclusão '
            "automática neste run.</p>"
        )

    if included:
        included_rows = "\n".join(
            "<tr>"
            f"<td>{_e(item.get('symbol'))}</td>"
            f"<td>{_e(item.get('name'))}</td>"
            f"<td>{_e(item.get('note'))}</td>"
            "</tr>"
            for item in included
        )
        included_block = f"""
<h3>Incluídos ({len(included)})</h3>
<div class="table-scroll">
<table>
<thead><tr><th>Símbolo</th><th>Nome</th><th>Motivo</th></tr></thead>
<tbody>{included_rows}</tbody>
</table>
</div>
"""
    else:
        included_block = (
            "<h3>Incluídos (0)</h3>"
            '<p class="section-empty">Nenhum candidato qualificou neste '
            "run.</p>"
        )

    if excluded:
        excluded_rows = "\n".join(
            "<tr>"
            f"<td>{_e(item.get('symbol'))}</td>"
            f"<td>{_e(item.get('reason'))}</td>"
            "</tr>"
            for item in excluded
        )
        excluded_block = f"""
<h3>Removidos ({len(excluded)})</h3>
<div class="table-scroll">
<table>
<thead><tr><th>Símbolo</th><th>Motivo</th></tr></thead>
<tbody>{excluded_rows}</tbody>
</table>
</div>
"""
    else:
        excluded_block = (
            "<h3>Removidos (0)</h3>"
            '<p class="section-empty">Nenhuma entrada elegível para '
            "remoção neste run.</p>"
        )

    return f"""
<h2>Curadoria Automática da Watchlist</h2>
<p class="meta">Fluxo adicional ao gate manual (planilha/CLI) -- inclui
candidatos com decisão estimada positiva
(<code>config/watchlist_auto.yaml::selection.qualifying_decisions</code>) e
remove entradas que o próprio fluxo automático incluiu (<code>source=auto</code>)
cujo Investment Score caiu abaixo do patamar configurado. Nunca remove
holdings reais nem entradas curadas à mão.</p>
{included_block}
{excluded_block}
"""


def render_earnings(context: ReportContext) -> str:
    if not context.earnings_rows:
        return "<h2>Earnings</h2>" + (
            '<p class="section-empty">Nenhuma divulgação de resultado desde '
            "o último run.</p>"
        )
    rows_html = "\n".join(
        "<tr>"
        f"<td>{_e(row.symbol)}</td>"
        f"<td>{_e(row.name)}</td>"
        f"<td>{_e(row.origin)}</td>"
        f"<td>{_e('; '.join(row.changed_fundamentals) or 'sem mudança relevante')}</td>"
        "</tr>"
        for row in context.earnings_rows
    )
    return f"""
<h2>Earnings</h2>
<div class="table-scroll">
<table>
<colgroup>
<col style="width:15%"><col style="width:20%"><col style="width:15%">
<col style="width:50%">
</colgroup>
<thead><tr><th>Símbolo</th><th>Nome</th><th>Origem</th>
<th>Mudança nos fundamentals</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
"""


def render_screener(context: ReportContext) -> str:
    screener = context.screener
    if not screener.included:
        return "<h2>Screener</h2>" + _not_included("Screener")

    blocked_html = "".join(
        f"<li>{_e(reason)}: {count}</li>"
        for reason, count in screener.blocked_by_reason.items()
    )
    new_html = (
        f"<p>Novos aprovados vs. run anterior: {_e(', '.join(screener.new_candidates))}</p>"
        if screener.new_candidates
        else "<p class=\"meta\">Nenhum candidato novo vs. run anterior.</p>"
    )
    top_rows = "\n".join(
        "<tr>"
        f"<td>{item['candidate_rank']}</td>"
        f"<td>{_e(item['symbol'])}</td>"
        f"<td>{_e(item['sector'])}</td>"
        f"<td>{item['investment_score']:.1f}</td>"
        f"<td>{item['confidence_score']:.1f}</td>"
        "</tr>"
        for item in screener.top_candidates
    )
    return f"""
<h2>Screener</h2>
<p>{screener.total_count} analisados · {screener.universe_eligible_count} elegíveis ·
{screener.candidate_count} candidatos</p>
<ul>{blocked_html}</ul>
{new_html}
<div class="table-scroll">
<table>
<colgroup>
<col style="width:12%"><col style="width:20%"><col style="width:28%">
<col style="width:20%"><col style="width:20%">
</colgroup>
<thead><tr><th>Rank</th><th>Símbolo</th><th>Setor</th><th>Score</th>
<th>Confiança</th></tr></thead>
<tbody>{top_rows}</tbody>
</table>
</div>
"""


def _broad_screener_html(summary: BroadScreenerSummary) -> str:
    if not summary.included:
        return f"<h3>{_e(summary.label)}</h3>" + _not_included(summary.label)

    staleness_html = (
        f'<p class="alert">⚠ Última coleta há {summary.age_days:.0f} dia(s) '
        "-- considere rodar a coleta novamente (universe.collector).</p>"
        if summary.stale
        else ""
    )
    generated_html = (
        f'<p class="meta">Coleta de {_e(summary.generated_at)} '
        f"({summary.age_days:.1f} dia(s) atrás)</p>"
        if summary.generated_at
        else ""
    )
    blocked_html = "".join(
        f"<li>{_e(reason)}: {count}</li>"
        for reason, count in summary.blocked_by_reason.items()
    )
    top_rows = "\n".join(
        "<tr>"
        f"<td>{item['candidate_rank']}</td>"
        f"<td>{_e(item['symbol'])}</td>"
        f"<td>{_e(item['sector'])}</td>"
        f"<td>{item['investment_score']:.1f}</td>"
        f"<td>{item['confidence_score']:.1f}</td>"
        "</tr>"
        for item in summary.top_candidates
    )
    return f"""
<h3>{_e(summary.label)}</h3>
{generated_html}
{staleness_html}
<p>{summary.total_count} analisados · {summary.universe_eligible_count} elegíveis ·
{summary.candidate_count} candidatos</p>
<ul>{blocked_html}</ul>
<div class="table-scroll">
<table>
<colgroup>
<col style="width:12%"><col style="width:20%"><col style="width:28%">
<col style="width:20%"><col style="width:20%">
</colgroup>
<thead><tr><th>Rank</th><th>Símbolo</th><th>Setor</th><th>Score</th>
<th>Confiança</th></tr></thead>
<tbody>{top_rows}</tbody>
</table>
</div>
"""


def render_broad_screeners(context: ReportContext) -> str:
    if not context.broad_screeners:
        return "<h2>Screeners amplos</h2>" + _not_included("Screeners amplos")
    sections = "\n".join(_broad_screener_html(summary) for summary in context.broad_screeners)
    return f"<h2>Screeners amplos</h2>\n{sections}"


def _feature_detail_html(feature: FeatureDetail) -> str:
    inputs_html = "".join(
        f"<li>{_e(label)}: {_e(value)}</li>" for label, value in feature.inputs
    )
    interpretation_html = (
        f'<p class="meta">{_e(feature.interpretation)}</p>'
        if feature.interpretation
        else ""
    )
    return f"""
<details class="card">
<summary>{_e(feature.label)} <span class="meta">({_e(feature.factor)})</span> —
percentil {feature.percentile:.0f} · contribuição {feature.contribution:+.1f}pt</summary>
<p>{_e(feature.formula)}</p>
{f'<ul>{inputs_html}</ul>' if inputs_html else ''}
{interpretation_html}
</details>
"""


def _sell_rules_html(detail: TickerDetail) -> str:
    if not detail.sell_rules_available:
        return _not_included("Regras de venda")
    if not detail.sell_rules:
        return '<p class="section-empty">Nenhuma regra avaliada.</p>'
    rows: list[str] = []
    for rule in detail.sell_rules:
        css_class = "pill-sell" if rule.status == "triggered" else "pill-hold"
        rows.append(
            f'<div class="card"><strong>{_e(rule.name)}</strong> '
            f'<span class="pill {css_class}">{_e(rule.status_label)}</span>'
            f"<br>{_e(rule.message)}"
            f'<br><span class="meta">{_e(rule.definition)}</span></div>'
        )
    return "\n".join(rows)


def _histories_html(detail: TickerDetail) -> str:
    cards = "\n".join(
        f'<div class="card"><strong>{_e(history.label)}</strong><br>'
        + (
            history.sparkline
            if history.available
            else '<p class="section-empty">Histórico pendente: schema de snapshot.</p>'
        )
        + "</div>"
        for history in detail.histories
    )
    return f'<div class="history-grid">{cards}</div>' if cards else ""


def _thesis_html(detail: TickerDetail) -> str:
    if detail.thesis is None:
        return '<p class="section-empty">Sem tese registrada (não é uma posição real ou tese pendente).</p>'
    thesis = detail.thesis
    meta_bits = []
    if thesis.entry_date:
        meta_bits.append(f"entrada: {_e(thesis.entry_date)}")
    if thesis.thesis_updated_at:
        meta_bits.append(f"atualizada: {_e(thesis.thesis_updated_at)}")
    if thesis.age_months is not None:
        meta_bits.append(f"{thesis.age_months:.1f} meses")
    attention_html = (
        f'<div class="alert">⚠ Tese pode estar desatualizada: {_e(thesis.attention)}</div>'
        if thesis.attention
        else ""
    )
    meta_html = f'<p class="meta">{" · ".join(meta_bits)}</p>' if meta_bits else ""
    return (
        f'<div class="card">{_e(thesis.text)}</div>{meta_html}{attention_html}'
    )


def _ticker_detail_html(detail: TickerDetail) -> str:
    price_bits = []
    if detail.average_price is not None:
        price_bits.append(f"PM {detail.average_price:.2f}")
    if detail.current_price is not None:
        price_bits.append(f"atual {detail.current_price:.2f}")
    if detail.unrealized_return is not None:
        price_bits.append(f"retorno {detail.unrealized_return:+.1f}%")
    price_html = f'<p class="meta">{" · ".join(price_bits)}</p>' if price_bits else ""

    positive_html = "".join(_feature_detail_html(item) for item in detail.positive_features)
    negative_html = "".join(_feature_detail_html(item) for item in detail.negative_features)

    return f"""
<section class="ticker-detail" id="{_e(detail.anchor_id)}">
<h3>{_e(detail.symbol)} — {_e(detail.name)} <span class="meta">{_e(detail.sector)}</span></h3>
<p class="meta">
origem: {_e(detail.origin)} ·
{_pill(detail.action)} <span class="engine">[{_e(detail.action_engine)}]</span> ·
score {f'{detail.score:.1f}' if detail.score is not None else '—'}
{_delta_html(detail.score_delta) if detail.score_delta is not None else ''} ·
coverage {f'{detail.coverage:.1f}%' if detail.coverage is not None else '—'}
</p>
<p>{_e(detail.action_reason)}</p>
{price_html}

<h4>Maiores contribuições positivas</h4>
{positive_html or '<p class="section-empty">Nenhuma.</p>'}

<h4>Maiores contribuições negativas</h4>
{negative_html or '<p class="section-empty">Nenhuma.</p>'}

<h4>Regras de venda</h4>
{_sell_rules_html(detail)}

<h4>Histórico</h4>
{_histories_html(detail) or '<p class="section-empty">Histórico insuficiente.</p>'}

<h4>Tese</h4>
{_thesis_html(detail)}
</section>
"""


def render_ticker_details(context: ReportContext) -> str:
    if not context.ticker_details:
        return "<h2>Detalhe por ativo</h2>" + _not_included("Detalhe por ativo")
    sections = "\n".join(_ticker_detail_html(detail) for detail in context.ticker_details)
    return f"<h2>Detalhe por ativo</h2>\n{sections}"


def render_footer(context: ReportContext) -> str:
    quality = context.data_quality
    failures_html = (
        f"<li>Fetches com falha: {_e(', '.join(quality.fetch_failures))}</li>"
        if quality.fetch_failures
        else ""
    )
    stale_html = (
        f"<li>Statements vencidos: {_e(', '.join(quality.stale_statements))}</li>"
        if quality.stale_statements
        else ""
    )
    conflicts_html = "".join(
        f'<div class="alert">⚠ {_e(alert)}</div>' for alert in context.engine_conflicts
    )
    return f"""
<div class="footer">
<h2 style="border:none;">Diagnóstico</h2>
{conflicts_html}
<h3>Qualidade de dados</h3>
<ul>
<li>Peso fantasma no Investment Score: {quality.phantom_weight_pct:.1f}%</li>
{failures_html}
{stale_html}
</ul>
<p>Gerado em {_e(context.generated_at.isoformat(timespec='seconds'))} pelo Atlas.</p>
</div>
"""


def page_shell(title: str, body: str) -> str:
    """
    Envelope HTML auto-contido comum (doctype/head/style) -- reaproveitado
    pelo relatório completo e pelo one-pager standalone (--ticker).
    """
    return (
        "<!doctype html>\n"
        '<html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>"
        f"<style>{_STYLE}</style></head><body>{body}</body></html>"
    )


def render_report(context: ReportContext) -> str:
    body = "\n".join(
        (
            render_header(context),
            render_required_actions(context),
            render_informational_signals(context),
            render_portfolio(context),
            render_watchlist(context),
            render_watchlist_proposals(context),
            render_watchlist_auto_curation(context),
            render_earnings(context),
            render_screener(context),
            render_broad_screeners(context),
            render_ticker_details(context),
            render_footer(context),
        )
    )
    return page_shell(f"Atlas Report — {context.snapshot_date}", body)

from __future__ import annotations

from html import escape

from reports.atlas_report.context import ReportContext

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
.delta-up { color: var(--hold); }
.delta-down { color: var(--sell); }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; }
.card .engine { color: var(--muted); font-size: 0.75rem; }
.footer { margin-top: 2rem; color: var(--muted); font-size: 0.78rem; }
.alert { color: var(--sell); background: var(--sell-bg); border-radius: 0.4rem; padding: 0.4rem 0.6rem; margin: 0.25rem 0; font-size: 0.82rem; }
"""

_PILL_CLASS = {
    "HOLD": "pill-hold",
    "REVISAR": "pill-revisar",
    "TRIM": "pill-trim",
    "SELL": "pill-sell",
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
        f"<td>{_e(row.symbol)}</td>"
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
        f"<td>{_e(row.symbol)}</td>"
        f"<td>{_e(row.name)}</td>"
        f"<td>{_e(row.trigger_condition) or 'acompanhamento passivo'}</td>"
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
        + "</tr>"
        for row in context.watchlist_rows
    )
    return f"""
<h2>Watchlist</h2>
<div class="table-scroll">
<table>
<colgroup>
<col style="width:12%"><col style="width:18%"><col style="width:24%">
<col style="width:10%"><col style="width:10%"><col style="width:14%">
<col style="width:12%">
</colgroup>
<thead><tr><th>Símbolo</th><th>Nome</th><th>Condição</th><th>Score</th>
<th>Idade</th><th>Trigger</th><th>Limpeza?</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
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
            render_portfolio(context),
            render_watchlist(context),
            render_earnings(context),
            render_screener(context),
            render_footer(context),
        )
    )
    return page_shell(f"Atlas Report — {context.snapshot_date}", body)

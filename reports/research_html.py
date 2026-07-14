from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

from reports.research_common import company_status

ROOT = Path(__file__).resolve().parent.parent

_STYLE = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card-bg: #f9fafb; --accent: #2563eb; --accent-bg: #dbeafe;
  --good: #16a34a; --good-bg: #dcfce7; --bad: #b91c1c; --bad-bg: #fee2e2;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111827; --fg: #f3f4f6; --muted: #9ca3af; --border: #374151;
    --card-bg: #1f2937; --accent: #60a5fa; --accent-bg: #1e3a5f;
    --good-bg: #14532d; --bad-bg: #7f1d1d;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 1rem; background: var(--bg); color: var(--fg);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.45;
}
h1 { font-size: 1.3rem; margin: 0 0 0.25rem; }
h2 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
.meta { color: var(--muted); font-size: 0.85rem; }
.stats { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.75rem 0; }
.stat { background: var(--card-bg); border: 1px solid var(--border); border-radius: 0.5rem;
  padding: 0.5rem 0.9rem; min-width: 7rem; }
.stat .value { font-size: 1.3rem; font-weight: 700; }
.stat .label { color: var(--muted); font-size: 0.75rem; }
.sector-bar-row { display: flex; align-items: center; gap: 0.5rem; margin: 0.15rem 0; font-size: 0.82rem; }
.sector-bar-track { flex: 1; background: var(--card-bg); border-radius: 3px; height: 0.9rem; overflow: hidden; }
.sector-bar-fill { background: var(--accent); height: 100%; }
.table-scroll { overflow-x: auto; max-width: 100%; }
table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
th, td { text-align: left; padding: 0.35rem 0.55rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--muted); font-weight: 600; cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--bg); }
th:hover { color: var(--fg); }
th.sorted-asc::after { content: " ▲"; }
th.sorted-desc::after { content: " ▼"; }
.badge { display: inline-block; padding: 0.05rem 0.5rem; border-radius: 999px; font-size: 0.72rem; font-weight: 600; }
.badge-good { color: var(--good); background: var(--good-bg); }
.badge-bad { color: var(--bad); background: var(--bad-bg); }
.badge-neutral { color: var(--muted); background: var(--card-bg); }
#search { width: 100%; max-width: 320px; padding: 0.4rem 0.6rem; margin: 0.5rem 0;
  border: 1px solid var(--border); border-radius: 0.4rem; background: var(--bg); color: var(--fg); }
.row-count { color: var(--muted); font-size: 0.8rem; }
.footer { margin-top: 2rem; color: var(--muted); font-size: 0.78rem; }
"""

_SORT_SCRIPT = """
function sortTable(table, columnIndex, numeric) {
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const th = table.tHead.rows[0].cells[columnIndex];
  const ascending = !th.classList.contains('sorted-asc');
  for (const cell of table.tHead.rows[0].cells) {
    cell.classList.remove('sorted-asc', 'sorted-desc');
  }
  th.classList.add(ascending ? 'sorted-asc' : 'sorted-desc');
  rows.sort((a, b) => {
    let av = a.cells[columnIndex].dataset.value ?? a.cells[columnIndex].textContent;
    let bv = b.cells[columnIndex].dataset.value ?? b.cells[columnIndex].textContent;
    if (numeric) { av = parseFloat(av) || -Infinity; bv = parseFloat(bv) || -Infinity; }
    if (av < bv) return ascending ? -1 : 1;
    if (av > bv) return ascending ? 1 : -1;
    return 0;
  });
  for (const row of rows) tbody.appendChild(row);
}
function filterTable(table, query, countEl, totalCount) {
  const tbody = table.tBodies[0];
  const needle = query.trim().toLowerCase();
  let visible = 0;
  for (const row of tbody.rows) {
    const match = !needle || row.textContent.toLowerCase().includes(needle);
    row.style.display = match ? '' : 'none';
    if (match) visible++;
  }
  countEl.textContent = visible + ' de ' + totalCount + ' empresas';
}
"""


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""))


def _num(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return "" if number != number else f"{number:.4g}"


_BADGE_CLASS = {"good": "badge-good", "bad": "badge-bad", "neutral": "badge-neutral"}


def _company_status(company: dict[str, Any]) -> tuple[str, str]:
    """Retorna (rótulo, classe do badge) -- lido do dado, nunca recalculado."""
    label, category = company_status(company)
    return label, _BADGE_CLASS[category]


def _render_stats(summary: dict[str, Any]) -> str:
    blocked = summary.get("blocked_by_reason", {}) or {}
    cards = [
        ("Analisados", summary.get("total_count", 0)),
        ("Elegíveis", summary.get("universe_eligible_count", 0)),
        ("Candidatos", summary.get("candidate_count", 0)),
    ]
    for reason, count in blocked.items():
        cards.append((reason, count))
    return "".join(
        f'<div class="stat"><div class="value">{_e(value)}</div>'
        f'<div class="label">{_e(label)}</div></div>'
        for label, value in cards
    )


def _render_model_portfolio(portfolio: dict[str, Any] | None) -> str:
    if portfolio is None:
        return ""
    positions = portfolio.get("positions", [])
    summary = portfolio.get("summary", {})
    sector_weights = summary.get("sector_weights", {})
    max_weight = max(sector_weights.values(), default=1.0) or 1.0

    sector_bars = "".join(
        f'<div class="sector-bar-row"><span style="min-width:9rem">{_e(sector)}</span>'
        f'<div class="sector-bar-track"><div class="sector-bar-fill" '
        f'style="width:{weight / max_weight * 100:.1f}%"></div></div>'
        f'<span>{weight * 100:.1f}%</span></div>'
        for sector, weight in sorted(sector_weights.items())
    )

    rows = "".join(
        "<tr>"
        f"<td>{position.get('candidate_rank', '')}</td>"
        f"<td>{_e(position.get('symbol'))}</td>"
        f"<td>{_e(position.get('name'))}</td>"
        f"<td>{_e(position.get('sector'))}</td>"
        f"<td>{position.get('target_weight', 0) * 100:.1f}%</td>"
        f"<td>{_num(position.get('investment_score'))}</td>"
        f"<td>{_num(position.get('reference_price'))}</td>"
        "</tr>"
        for position in positions
    )

    warnings_html = "".join(
        f'<p class="meta">⚠ {_e(warning)}</p>' for warning in summary.get("warnings", [])
    )

    return f"""
<h2>Carteira-modelo sugerida ({len(positions)} posições)</h2>
{warnings_html}
<div class="stats">
<div class="stat"><div class="value">{summary.get('invested_weight', 0) * 100:.0f}%</div><div class="label">Peso investido</div></div>
</div>
{sector_bars}
<div class="table-scroll"><table>
<thead><tr><th>Rank</th><th>Símbolo</th><th>Nome</th><th>Setor</th><th>Peso</th>
<th>Score</th><th>Preço ref.</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>
"""


def render_research_report(
    ranking: dict[str, Any],
    portfolio: dict[str, Any] | None,
    *,
    label: str,
) -> str:
    """
    Converte research_ranking_report*.json (+ model_portfolio_report*.json,
    opcional) num HTML auto-contido, navegável (busca + ordenação por
    coluna via JS embutido, sem dependência externa). Só formata o que já
    está no JSON -- nenhum dado é recalculado.
    """
    policy = ranking.get("policy", {})
    summary = ranking.get("summary", {})
    companies = sorted(
        ranking.get("companies", []),
        key=lambda item: (
            item.get("market_rank") is None,
            item.get("market_rank") or 10**9,
        ),
    )

    rows = []
    for company in companies:
        status_label, status_class = _company_status(company)
        rows.append(
            "<tr>"
            f"<td data-value=\"{company.get('market_rank') or ''}\">{company.get('market_rank') or ''}</td>"
            f"<td>{_e(company.get('symbol'))}</td>"
            f"<td>{_e(company.get('sector'))}</td>"
            f"<td data-value=\"{_num(company.get('investment_score'))}\">{_num(company.get('investment_score'))}</td>"
            f"<td data-value=\"{_num(company.get('opportunity_score'))}\">{_num(company.get('opportunity_score'))}</td>"
            f"<td data-value=\"{_num(company.get('conviction_score'))}\">{_num(company.get('conviction_score'))}</td>"
            f"<td data-value=\"{_num(company.get('confidence_score'))}\">{_num(company.get('confidence_score'))}</td>"
            f'<td><span class="badge {status_class}">{_e(status_label)}</span></td>'
            f"<td>{'já detida' if company.get('already_held') else ''}</td>"
            "</tr>"
        )

    body = f"""
<h1>Atlas Research Report — {_e(label)}</h1>
<p class="meta">
  Política: {_e(policy.get('name'))} · Gerado em {_e(ranking.get('generated_at'))} ·
  Confiança mínima: {_e(policy.get('min_confidence_score'))}
</p>
<div class="stats">{_render_stats(summary)}</div>
{_render_model_portfolio(portfolio)}
<h2>Todas as empresas analisadas</h2>
<input id="search" type="text" placeholder="Buscar por símbolo, setor ou status...">
<p class="row-count" id="row-count">{len(companies)} de {len(companies)} empresas</p>
<div class="table-scroll">
<table id="company-table">
<thead><tr>
<th onclick="sortTable(this.closest('table'),0,true)">Rank</th>
<th onclick="sortTable(this.closest('table'),1,false)">Símbolo</th>
<th onclick="sortTable(this.closest('table'),2,false)">Setor</th>
<th onclick="sortTable(this.closest('table'),3,true)">Investment</th>
<th onclick="sortTable(this.closest('table'),4,true)">Opportunity</th>
<th onclick="sortTable(this.closest('table'),5,true)">Conviction</th>
<th onclick="sortTable(this.closest('table'),6,true)">Confidence</th>
<th onclick="sortTable(this.closest('table'),7,false)">Status</th>
<th onclick="sortTable(this.closest('table'),8,false)">Carteira</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
<div class="footer">
<p>Gerado a partir de research_ranking_report{f'_{label.lower()}' if label.lower() != 'sp500' else ''}.json
pelo conversor Atlas -- nenhum dado é recalculado aqui.</p>
</div>
<script>
{_SORT_SCRIPT}
const table = document.getElementById('company-table');
const searchBox = document.getElementById('search');
const countEl = document.getElementById('row-count');
const total = table.tBodies[0].rows.length;
searchBox.addEventListener('input', () => filterTable(table, searchBox.value, countEl, total));
</script>
"""
    return (
        "<!doctype html>\n"
        '<html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Atlas Research Report — {_e(label)}</title>"
        f"<style>{_STYLE}</style></head><body>{body}</body></html>"
    )


def write_research_report(html: str, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Converte research_ranking_report*.json (+ model_portfolio_report*.json, "
            "opcional) num HTML navegável -- não recalcula nada, só formata."
        )
    )
    parser.add_argument(
        "--ranking",
        required=True,
        help="Caminho do research_ranking_report*.json.",
    )
    parser.add_argument(
        "--portfolio",
        default=None,
        help="Caminho do model_portfolio_report*.json correspondente (opcional).",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Rótulo do screener (ex.: S&P500, Market, ADR).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Caminho de saída. Default: mesmo diretório do --ranking, "
        "research_report_<label>.html.",
    )
    args = parser.parse_args()

    ranking_path = Path(args.ranking)
    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))

    portfolio = None
    if args.portfolio:
        portfolio_path = Path(args.portfolio)
        if portfolio_path.exists():
            portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))

    html = render_research_report(ranking, portfolio, label=args.label)

    output = Path(args.output) if args.output else (
        ranking_path.parent
        / f"research_report_{args.label.lower().replace(' ', '_').replace('&', '')}.html"
    )
    write_research_report(html, output)
    print(f"Relatório HTML gerado em {output}")


if __name__ == "__main__":
    main()

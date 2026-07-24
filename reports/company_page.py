"""
Página da empresa -- one-pager isolado com TODA a evidência coletada do ticker.

Diferente da seção de detalhe embutida no relatório completo (que continua
existindo), esta página é um documento fechado: só aquele símbolo, do preço às
demonstrações financeiras abertas, sem a próxima empresa logo abaixo.

Regra central, herdada do resto da camada de relatório: **não calcula e não
decide nada**. Tudo aqui já foi produzido e persistido pelos motores --

- `output/dados/dashboard.json`  -> scores, decisão, tese, riscos, catalisadores
- `data/atlas_history.db`        -> snapshot mais recente + série histórica e o
                                    `field_evidence_json` (status/fonte/data por campo)
- `storage/raw_snapshots`        -> snapshot bruto imutável do provedor, com os
                                    valores de cada campo e os DataFrames de
                                    balanço, DRE e fluxo de caixa

Campo ausente vira "não coletado" explícito; nunca um valor inventado.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from reports.statement_layout import TOTAL_LINES, order_statement

STATEMENTS = (
    ("_income_statement", "Demonstração de Resultado (DRE)"),
    ("_balance_sheet", "Balanço Patrimonial"),
    ("_cashflow", "Fluxo de Caixa"),
)

CATEGORY_LABELS = {
    "identity": "Identificação",
    "market": "Mercado e preço",
    "fundamentals": "Fundamentos",
    "analyst": "Analistas",
    "ownership": "Composição acionária",
}
CATEGORY_ORDER = ("identity", "market", "fundamentals", "analyst", "ownership")

STATUS_LABELS = {
    "present": ("presente", "ok"),
    "stale": ("desatualizado", "warn"),
    "missing": ("não coletado", "bad"),
    "unavailable": ("indisponível na fonte", "bad"),
    "invalid": ("rejeitado", "bad"),
    "not_applicable": ("não se aplica", "na"),
}

# Campos cujo valor persistido é fração e deve ser lido como percentual.
PERCENT_FIELDS = frozenset({
    "roe", "roa", "roic", "gross_margin", "net_margin", "operating_margin",
    "operating_margin_proxy", "ebitda_margin", "dividend_yield", "fcf_yield",
    "shareholder_yield", "short_float", "insider_own", "inst_own", "buyback",
})
# Campos já expressos em pontos percentuais pelo provedor.
POINT_FIELDS = frozenset({
    "change_pct", "target_upside", "momentum_3m", "momentum_6m", "momentum_12m",
    "distance_52w_high", "distance_52w_low", "current_liquidity",
})

FIELD_LABELS = {
    "price": "Preço", "previous_close": "Fechamento anterior", "change_pct": "Variação",
    "volume": "Volume", "average_volume": "Volume médio", "market_cap": "Valor de mercado",
    "enterprise_value": "Enterprise Value", "beta": "Beta", "year_high": "Máxima 52s",
    "year_low": "Mínima 52s", "sma_50": "Média 50d", "sma_200": "Média 200d",
    "rsi_14": "RSI (14)", "pe": "P/L", "forward_pe": "P/L projetado", "pb": "P/VP",
    "ps": "P/Receita", "peg": "PEG", "ev_ebitda": "EV/EBITDA", "ev_ebit": "EV/EBIT",
    "ev_to_revenue": "EV/Receita", "roe": "ROE", "roa": "ROA", "roic": "ROIC",
    "net_margin": "Margem líquida", "gross_margin": "Margem bruta",
    "operating_margin": "Margem operacional", "ebitda_margin": "Margem EBITDA",
    "total_debt": "Dívida total", "net_debt": "Dívida líquida", "total_cash": "Caixa",
    "debt_to_equity": "Dívida/Patrimônio", "net_debt_ebitda": "Dívida líq./EBITDA",
    "current_ratio": "Liquidez corrente", "quick_ratio": "Liquidez seca",
    "interest_coverage": "Cobertura de juros", "altman_z": "Altman Z",
    "f_score_annual": "Piotroski F-Score", "ebit": "EBIT", "ebitda": "EBITDA",
    "free_cashflow": "Fluxo de caixa livre", "operating_cashflow": "Caixa operacional",
    "shares_outstanding": "Ações em circulação", "short_float": "Short float",
    "dividend_rate": "Dividendo", "dividend_yield": "Dividend yield",
    "target_price": "Preço-alvo", "target_high_price": "Alvo máximo",
    "target_low_price": "Alvo mínimo", "consensus_target": "Alvo de consenso",
    "analyst_count": "Nº de analistas", "rating": "Rating", "earnings_date": "Próximo resultado",
    "target_upside": "Upside até o alvo", "momentum_3m": "Momentum 3m",
    "momentum_6m": "Momentum 6m", "momentum_12m": "Momentum 12m",
    "distance_52w_high": "Distância da máxima", "distance_52w_low": "Distância da mínima",
    "insider_own": "Participação de insiders", "inst_own": "Participação institucional",
    "sector": "Setor", "industry": "Indústria", "country": "País", "currency": "Moeda",
    "financial_currency": "Moeda do balanço", "exchange": "Bolsa", "name": "Nome",
    "symbol": "Símbolo", "quote_type": "Tipo", "origin": "Origem",
}


def _e(value: object) -> str:
    return escape(str(value if value is not None else ""))


def _fmt(field_name: str, value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, (int, float)):
        number = float(value)
        if field_name in PERCENT_FIELDS:
            return f"{number * 100:,.2f}%".replace(",", " ")
        if field_name in POINT_FIELDS:
            return f"{number:,.2f}%".replace(",", " ")
        for limit, suffix in ((1e12, " tri"), (1e9, " bi"), (1e6, " mi")):
            if abs(number) >= limit:
                return f"{number / limit:,.2f}{suffix}".replace(",", " ")
        if abs(number) >= 1000:
            return f"{number:,.0f}".replace(",", " ")
        return f"{number:,.2f}".replace(",", " ")
    return str(value)


def _fmt_dt(value: object) -> str:
    text = str(value or "")
    if not text:
        return "—"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.strftime("%d/%m/%Y %H:%M")


@dataclass
class CompanyData:
    symbol: str
    company: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.company or self.snapshot)


def load_company_data(symbol: str, root: Path) -> CompanyData:
    """Reúne, somente lendo, tudo que já foi persistido sobre o símbolo."""
    symbol = symbol.strip().upper()
    data = CompanyData(symbol=symbol)

    dashboard = root / "output" / "dados" / "dashboard.json"
    if dashboard.exists():
        try:
            payload = json.loads(dashboard.read_text(encoding="utf-8"))
            for company in payload.get("companies") or []:
                if str(company.get("symbol", "")).upper() == symbol:
                    data.company = company
                    break
        except (ValueError, OSError):
            pass

    database = root / "data" / "atlas_history.db"
    if database.exists():
        try:
            con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM snapshots WHERE symbol = ? ORDER BY snapshot_date DESC",
                (symbol,),
            ).fetchall()
            con.close()
            if rows:
                data.snapshot = dict(rows[0])
                data.history = [dict(row) for row in rows]
                try:
                    data.evidence = json.loads(
                        data.snapshot.get("field_evidence_json") or "{}"
                    )
                except ValueError:
                    data.evidence = {}
                try:
                    data.analysis = json.loads(
                        data.snapshot.get("analysis_values_json") or "{}"
                    )
                except ValueError:
                    data.analysis = {}
        except sqlite3.Error:
            pass

    raw_path = str(data.snapshot.get("raw_snapshot_path") or "")
    if raw_path:
        candidate = Path(raw_path)
        if candidate.exists():
            try:
                data.raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data.raw = {}
    return data


def _status_pill(status: str) -> str:
    label, tone = STATUS_LABELS.get(status, (status or "—", "na"))
    return f'<span class="pill {tone}">{_e(label)}</span>'


def _value_for(data: CompanyData, name: str) -> tuple[object, bool]:
    """Valor do campo e se ele está de fato persistido.

    Procura, nesta ordem, no snapshot bruto do provedor, no contrato do
    dashboard e nas colunas do histórico (onde vivem os derivados que o Atlas
    calcula, como Altman Z e ROIC). Métrica derivada que o pipeline não grava
    volta como não persistida -- a página diz isso em vez de mostrar um traço
    ambíguo ou, pior, inventar um número.
    """
    for source in (data.raw, data.analysis, data.company, data.snapshot):
        if name in source and source[name] is not None:
            return source[name], True
    return None, False


def _evidence_rows(data: CompanyData, category: str) -> str:
    names = sorted(
        name
        for name, meta in data.evidence.items()
        if (meta or {}).get("category") == category
    )
    rows = []
    for name in names:
        meta = data.evidence.get(name) or {}
        status = str(meta.get("status") or "")
        value, persisted = _value_for(data, name)
        label = FIELD_LABELS.get(name, name.replace("_", " ").capitalize())
        detail = meta.get("detail")
        detail_html = f'<div class="detail">{_e(detail)}</div>' if detail else ""
        confirmed = meta.get("confirmed_by")
        confirmed_html = (
            f'<div class="detail">confirmado por {_e(confirmed)}</div>'
            if confirmed
            else ""
        )
        if persisted:
            value_html = _e(_fmt(name, value))
        elif status in ("present", "stale"):
            value_html = '<span class="unstored">não persistido</span>'
        else:
            value_html = "—"
        rows.append(
            "<tr>"
            f'<td><b>{_e(label)}</b><div class="code">{_e(name)}</div></td>'
            f'<td class="num">{value_html}</td>'
            f"<td>{_status_pill(status)}{detail_html}{confirmed_html}</td>"
            f"<td>{_e(meta.get('source') or '—')}</td>"
            f"<td class=\"when\">{_e(_fmt_dt(meta.get('observed_at') or meta.get('retrieved_at')))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        f'<h3>{_e(CATEGORY_LABELS.get(category, category))} '
        f'<span class="count">{len(rows)} campos</span></h3>'
        '<div class="tbl"><table><thead><tr>'
        "<th>Campo</th><th>Valor</th><th>Situação</th><th>Fonte</th><th>Observado em</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _statement_table(frame: object, statement_key: str = "") -> str:
    """Renderiza um DataFrame serializado (orient='split') na ordem da SEC."""
    if not isinstance(frame, dict):
        return ""
    columns = frame.get("columns") or []
    index = frame.get("index") or []
    matrix = frame.get("data") or []
    if not columns or not index:
        return ""

    def header(value: object) -> str:
        text = str(value)
        if text.isdigit() and len(text) >= 10:  # epoch em ms
            try:
                return datetime.fromtimestamp(
                    int(text) / 1000, tz=timezone.utc
                ).strftime("%d/%m/%Y")
            except (ValueError, OSError):
                return text
        try:
            return datetime.fromisoformat(text).strftime("%d/%m/%Y")
        except ValueError:
            return text

    by_label = {str(label): row for label, row in zip(index, matrix)}
    head = "".join(f'<th class="num">{_e(header(c))}</th>' for c in columns)
    span = len(columns) + 1

    body = []
    for section, label in order_statement(statement_key, [str(i) for i in index]):
        if section:
            body.append(
                f'<tr class="sec"><td colspan="{span}">{_e(section)}</td></tr>'
            )
        row = by_label.get(label, [])
        cells = "".join(f'<td class="num">{_e(_fmt("", v))}</td>' for v in row)
        css = ' class="total"' if label in TOTAL_LINES else ""
        body.append(f"<tr{css}><td>{_e(label)}</td>{cells}</tr>")

    return (
        '<div class="tbl"><table><thead><tr><th>Linha</th>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def _list_block(title: str, values: object) -> str:
    items = [str(v) for v in (values or ()) if str(v) and str(v) != "Nenhum"]
    if not items:
        return ""
    return (
        f'<div class="block"><div class="k">{_e(title)}</div><ul>'
        + "".join(f"<li>{_e(item)}</li>" for item in items)
        + "</ul></div>"
    )


def _score_cards(data: CompanyData) -> str:
    source = data.company or data.snapshot
    cards = []
    for key, label in (
        ("investment_score", "Investment"),
        ("opportunity_score", "Opportunity"),
        ("conviction_score", "Convicção"),
        ("decision_confidence", "Confiança"),
        ("data_coverage", "Cobertura"),
        ("source_quality", "Qualidade fonte"),
        ("data_freshness", "Frescor"),
        ("risk_penalty", "Risk Penalty"),
        ("business_score", "Business"),
        ("valuation_score", "Valuation"),
        ("financial_score", "Financial"),
        ("timing_score", "Timing"),
    ):
        value = source.get(key)
        if value is None:
            continue
        cards.append(
            f'<div class="score"><div class="k">{_e(label)}</div>'
            f'<div class="v">{_e(_fmt(key, value))}</div></div>'
        )
    return f'<div class="scores">{"".join(cards)}</div>' if cards else ""


def _history_table(data: CompanyData) -> str:
    if len(data.history) < 2:
        return ""
    columns = (
        ("snapshot_date", "Data"),
        ("investment_score", "Investment"),
        ("opportunity_score", "Opportunity"),
        ("confidence_score", "Confiança"),
        ("roic", "ROIC"),
        ("f_score_annual", "F-Score"),
        ("altman_z", "Altman Z"),
        ("target_upside", "Upside"),
    )
    head = "".join(f'<th class="num">{_e(label)}</th>' for _, label in columns[1:])
    body = []
    for row in data.history[:30]:
        cells = "".join(
            f'<td class="num">{_e(_fmt(key, row.get(key)))}</td>'
            for key, _ in columns[1:]
        )
        body.append(
            f'<tr><td class="when">{_e(_fmt_dt(row.get("snapshot_date")))}</td>{cells}</tr>'
        )
    return (
        '<div class="tbl"><table><thead><tr><th>Data</th>'
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def render_company_page(symbol: str, root: Path) -> str | None:
    """HTML completo e isolado do símbolo, ou None se nada foi coletado ainda."""
    data = load_company_data(symbol, root)
    if not data.found:
        return None

    company = data.company
    raw = data.raw
    name = company.get("company_name") or raw.get("name") or data.symbol
    decision = str(company.get("decision") or "—")
    price = _fmt("price", raw.get("price"))
    change = raw.get("change_pct")
    change_html = (
        f'<span class="chg {"up" if (change or 0) >= 0 else "down"}">'
        f'{_e(_fmt("change_pct", change))}</span>'
        if change is not None
        else ""
    )
    identity = " · ".join(
        str(v)
        for v in (raw.get("sector"), raw.get("industry"), raw.get("country"), raw.get("exchange"))
        if v
    )

    evidence_sections = "".join(
        _evidence_rows(data, category) for category in CATEGORY_ORDER
    )
    extra = sorted(
        {
            str((meta or {}).get("category"))
            for meta in data.evidence.values()
            if (meta or {}).get("category") not in CATEGORY_ORDER
        }
        - {"None", ""}
    )
    evidence_sections += "".join(_evidence_rows(data, category) for category in extra)

    statements = ""
    for key, label in STATEMENTS:
        table = _statement_table(raw.get(key), key)
        if table:
            statements += f"<h3>{_e(label)}</h3>{table}"
    if not statements:
        statements = (
            '<p class="muted">Nenhuma demonstração financeira no snapshot bruto '
            "deste run.</p>"
        )

    thesis = company.get("investment_thesis")
    thesis_html = f'<div class="thesis">{_e(thesis)}</div>' if thesis else ""

    counts = {}
    for meta in data.evidence.values():
        status = str((meta or {}).get("status") or "?")
        counts[status] = counts.get(status, 0) + 1
    coverage_chips = "".join(
        f'<span class="pill {STATUS_LABELS.get(s, (s, "na"))[1]}">'
        f'{_e(STATUS_LABELS.get(s, (s, "na"))[0])}: {n}</span>'
        for s, n in sorted(counts.items(), key=lambda kv: -kv[1])
    )

    history_html = _history_table(data)
    history_section = (
        f"<section><h2>Histórico</h2>"
        f'<p class="muted">{len(data.history)} execuções registradas. '
        "Mostrando as 30 mais recentes.</p>"
        f"{history_html}</section>"
        if history_html
        else ""
    )

    provenance = (
        '<section><h2>Procedência</h2><div class="tbl"><table><tbody>'
        f'<tr><td>Universo de referência</td><td>{_e(data.snapshot.get("reference_universe"))} '
        f'({_e(data.snapshot.get("reference_count"))} empresas, '
        f'{_e(data.snapshot.get("reference_date"))}, v{_e(data.snapshot.get("reference_version"))})</td></tr>'
        f'<tr><td>Versão do modelo</td><td>{_e(data.snapshot.get("model_version"))}</td></tr>'
        f'<tr><td>Snapshot bruto (SHA-256)</td><td class="code">{_e(data.snapshot.get("raw_snapshot_hash"))}</td></tr>'
        f'<tr><td>Arquivo do snapshot</td><td class="code">{_e(data.snapshot.get("raw_snapshot_path"))}</td></tr>'
        f'<tr><td>Capturado em</td><td>{_e(_fmt_dt(data.snapshot.get("snapshot_date")))}</td></tr>'
        "</tbody></table></div></section>"
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(data.symbol)} — {_e(name)} · Atlas</title>
<style>
:root{{--bg:#f7f8fa;--surface:#fff;--surface-2:#f0f2f6;--ink:#141922;--ink-2:#48505e;--ink-3:#79808d;
--line:#e2e6ec;--accent:#1f6f6b;--accent-ink:#0e4744;--accent-soft:#e2f0ee;
--ok:#1f8f5f;--ok-soft:#e3f4ec;--warn:#b6791f;--warn-soft:#f8efdd;--bad:#c14545;--bad-soft:#f8e5e5;
--na:#5b6472;--na-soft:#eceff3;--shadow:0 1px 2px rgba(16,24,40,.05),0 5px 18px rgba(16,24,40,.06)}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1016;--surface:#151a22;--surface-2:#1b212b;--ink:#e7ebf1;
--ink-2:#aab3c0;--ink-3:#78808d;--line:#242c38;--accent:#4dc3ba;--accent-ink:#8fe0d8;--accent-soft:#12312e;
--ok:#4bbd85;--ok-soft:#12301f;--warn:#e0af58;--warn-soft:#33280f;--bad:#e07b7b;--bad-soft:#361c1c;
--na:#93a0b0;--na-soft:#1e2530;--shadow:0 1px 2px rgba(0,0,0,.3),0 6px 22px rgba(0,0,0,.4)}}}}
:root[data-theme="dark"]{{--bg:#0d1016;--surface:#151a22;--surface-2:#1b212b;--ink:#e7ebf1;--ink-2:#aab3c0;
--ink-3:#78808d;--line:#242c38;--accent:#4dc3ba;--accent-ink:#8fe0d8;--accent-soft:#12312e;--ok:#4bbd85;
--ok-soft:#12301f;--warn:#e0af58;--warn-soft:#33280f;--bad:#e07b7b;--bad-soft:#361c1c;--na:#93a0b0;--na-soft:#1e2530}}
:root[data-theme="light"]{{--bg:#f7f8fa;--surface:#fff;--surface-2:#f0f2f6;--ink:#141922;--ink-2:#48505e;
--ink-3:#79808d;--line:#e2e6ec;--accent:#1f6f6b;--accent-ink:#0e4744;--accent-soft:#e2f0ee;--ok:#1f8f5f;
--ok-soft:#e3f4ec;--warn:#b6791f;--warn-soft:#f8efdd;--bad:#c14545;--bad-soft:#f8e5e5;--na:#5b6472;--na-soft:#eceff3}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);line-height:1.55;
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1120px;margin:0 auto;padding:26px 20px 80px}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:22px;flex-wrap:wrap}}
.back{{color:var(--accent-ink);text-decoration:none;font-size:14px}}.back:hover{{text-decoration:underline}}
header.hero{{background:var(--surface);border:1px solid var(--line);border-radius:16px;
padding:24px 26px;box-shadow:var(--shadow);margin-bottom:22px}}
h1{{margin:0 0 4px;font-size:clamp(24px,4vw,34px);letter-spacing:-.02em}}
h1 small{{font-size:.5em;color:var(--ink-3);font-weight:500;letter-spacing:0}}
.ident{{color:var(--ink-2);font-size:14px;margin:0 0 14px}}
.priceline{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:14px}}
.price{{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums}}
.chg{{font-size:15px;font-weight:650}}.chg.up{{color:var(--ok)}}.chg.down{{color:var(--bad)}}
.decision{{display:inline-block;background:var(--accent-soft);color:var(--accent-ink);font-weight:700;
padding:5px 14px;border-radius:999px;font-size:14px}}
.thesis{{margin-top:14px;padding:13px 16px;background:var(--surface-2);border-left:3px solid var(--accent);
border-radius:0 10px 10px 0;font-size:14.5px;color:var(--ink-2)}}
.scores{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-top:18px}}
.score{{background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
.score .k{{font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--ink-3);font-weight:600}}
.score .v{{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}}
section{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px 24px;
box-shadow:var(--shadow);margin-bottom:20px}}
h2{{margin:0 0 4px;font-size:19px;letter-spacing:-.01em}}
h3{{margin:22px 0 8px;font-size:15px;color:var(--ink);display:flex;align-items:center;gap:9px}}
h3:first-of-type{{margin-top:12px}}
.count{{font-size:11px;font-weight:600;color:var(--ink-3);background:var(--surface-2);
border:1px solid var(--line);padding:2px 8px;border-radius:999px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 0}}
.muted{{color:var(--ink-3);font-size:13.5px}}
.tbl{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:6px 0 4px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}}
th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:var(--surface-2);font-size:11.5px;text-transform:uppercase;letter-spacing:.4px;
color:var(--ink-2);font-weight:600;position:sticky;top:0}}
tr:last-child td{{border-bottom:0}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
tr.sec td{{background:var(--accent-soft);color:var(--accent-ink);font-weight:700;font-size:11px;
text-transform:uppercase;letter-spacing:.7px;padding:7px 12px;border-bottom:1px solid var(--line)}}
tr.total td{{font-weight:700;border-top:1px solid var(--line-strong,var(--line));
background:var(--surface-2)}}
td.when{{white-space:nowrap;color:var(--ink-2);font-variant-numeric:tabular-nums}}
.code{{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--ink-3);word-break:break-all}}
.detail{{font-size:11.5px;color:var(--ink-3);margin-top:3px}}
.unstored{{font-size:11.5px;color:var(--ink-3);font-style:italic}}
.pill{{display:inline-block;font-size:11px;font-weight:650;padding:2px 8px;border-radius:999px;white-space:nowrap}}
.pill.ok{{background:var(--ok-soft);color:var(--ok)}}.pill.warn{{background:var(--warn-soft);color:var(--warn)}}
.pill.bad{{background:var(--bad-soft);color:var(--bad)}}.pill.na{{background:var(--na-soft);color:var(--na)}}
.block{{margin:14px 0 0}}
.block .k{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--accent);font-weight:600;margin-bottom:5px}}
.block ul{{margin:0;padding-left:19px;font-size:14px;color:var(--ink-2)}}.block li{{margin:3px 0}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media (max-width:720px){{.grid2{{grid-template-columns:1fr}}}}
.toggle{{background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:999px;
padding:6px 12px;font-size:12.5px;cursor:pointer;font-family:inherit}}
.toggle:hover{{border-color:var(--accent);color:var(--ink)}}
a:focus-visible,.toggle:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
</style></head><body><div class="wrap">

<div class="top">
  <a class="back" href="/cockpit">← Voltar para o cockpit</a>
  <button class="toggle" id="t">◐ Tema</button>
</div>

<header class="hero">
  <h1>{_e(name)} <small>{_e(data.symbol)}</small></h1>
  <p class="ident">{_e(identity)}</p>
  <div class="priceline">
    <span class="price">{_e(price)}</span>{change_html}
    <span class="decision">{_e(decision)}</span>
  </div>
  {thesis_html}
  {_score_cards(data)}
</header>

<section>
  <h2>Leitura do Atlas</h2>
  <p class="muted">Produzido pelos motores; esta página só exibe.</p>
  <div class="grid2">
    <div>
      {_list_block("Pontos fortes", company.get("strengths"))}
      {_list_block("Catalisadores", company.get("catalysts"))}
      {_list_block("Fatores da decisão", company.get("decision_drivers"))}
    </div>
    <div>
      {_list_block("Riscos", company.get("risks"))}
      {_list_block("Deal Breakers", company.get("deal_breakers"))}
      {_list_block("Features obrigatórias ausentes", company.get("missing_required_features"))}
      {_list_block("Evidência de risco ausente", company.get("risk_evidence_missing"))}
    </div>
  </div>
</section>

<section>
  <h2>Todos os dados coletados</h2>
  <p class="muted">{len(data.evidence)} campos, com situação, fonte e data de cada um.</p>
  <div class="chips">{coverage_chips}</div>
  {evidence_sections or '<p class="muted">Nenhuma evidência por campo neste snapshot.</p>'}
</section>

<section>
  <h2>Demonstrações financeiras</h2>
  <p class="muted">Do snapshot bruto imutável, como veio da fonte.</p>
  {statements}
</section>

{history_section}
{provenance}

</div>
<script>
document.getElementById('t').addEventListener('click',function(){{
  var r=document.documentElement,c=r.getAttribute('data-theme');
  if(!c)c=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  r.setAttribute('data-theme',c==='dark'?'light':'dark');
}});
</script>
</body></html>"""

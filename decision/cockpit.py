from __future__ import annotations

from html import escape
from pathlib import Path

from decision.queue import DecisionQueue
from portfolio.scenario import PortfolioScenario
from storage.atomic_write import replace_with_retry


GROUP_LABELS = {
    "EXECUTE": "Executar",
    "INVESTIGATE": "Investigar",
    "WAIT": "Aguardar",
    "MONITOR": "Monitorar",
}


def _e(value: object) -> str:
    return escape(str(value or ""))


def _item_card(item: dict[str, object]) -> str:
    metadata = []
    for key, label in (
        ("investment_score", "Score"),
        ("current_weight", "Peso"),
        ("analytical_origin", "Origem"),
        ("entry_rank", "Rank entrada"),
        ("entry_score", "Score entrada"),
        ("review_due_at", "Revisar em"),
    ):
        value = item.get(key)
        if value is not None and value != "":
            metadata.append(f"<span><b>{_e(label)}:</b> {_e(value)}</span>")
    return (
        '<article class="decision-card">'
        f'<div class="card-head"><strong>{_e(item.get("symbol"))}</strong>'
        f'<span class="action">{_e(item.get("action"))}</span></div>'
        f'<p>{_e(item.get("reason")) or "Sem justificativa publicada."}</p>'
        f'<div class="metadata">{"".join(metadata)}</div>'
        f'<small>{_e(item.get("engine"))} · consultivo</small>'
        "</article>"
    )


def render_decision_cockpit(
    queue: DecisionQueue,
    *,
    scenario: PortfolioScenario | None = None,
    journal_summary: dict[str, object] | None = None,
    execution_summary: dict[str, object] | None = None,
    reconciliation_summary: dict[str, object] | None = None,
) -> str:
    if not isinstance(queue, DecisionQueue):
        raise TypeError("queue deve ser DecisionQueue.")
    payload = queue.to_dict()
    groups = payload["groups"]
    summary = payload["summary"]
    summary_cards = "".join(
        f'<div class="summary {name.lower()}"><b>{count}</b><span>{GROUP_LABELS[name]}</span></div>'
        for name, count in (
            ("EXECUTE", summary["execute"]),
            ("INVESTIGATE", summary["investigate"]),
            ("WAIT", summary["wait"]),
            ("MONITOR", summary["monitor"]),
        )
    )
    scenario_html = ""
    if scenario is not None:
        scenario_summary = scenario.to_dict()["summary"]
        scenario_html = (
            '<section class="scenario"><h2>Impacto se executar SELL/TRIM</h2>'
            '<div class="metadata">'
            f'<span><b>Caixa liberado:</b> {scenario.currency} {_e(scenario_summary["released_cash"])}</span>'
            f'<span><b>Caixa pós:</b> {scenario.currency} {_e(scenario_summary["cash_after"])}</span>'
            f'<span><b>Caixa %:</b> {_e(round(scenario_summary["cash_weight_after"] * 100, 1))}%</span>'
            f'<span><b>Turnover:</b> {_e(round(scenario_summary["turnover"] * 100, 1))}%</span>'
            '</div><p class="meta">Sem compras substitutas; custos conforme cenário.</p></section>'
        )
    journal_html = ""
    if journal_summary is not None:
        journal_html = (
            '<section class="scenario"><h2>Revisões humanas registradas</h2>'
            '<div class="metadata">'
            f'<span><b>Aceitas:</b> {_e(journal_summary.get("accepted", 0))}</span>'
            f'<span><b>Rejeitadas:</b> {_e(journal_summary.get("rejected", 0))}</span>'
            f'<span><b>Adiadas:</b> {_e(journal_summary.get("deferred", 0))}</span>'
            f'<span><b>Eventos:</b> {_e(journal_summary.get("total_events", 0))}</span>'
            '</div></section>'
        )
    execution_html = ""
    if execution_summary is not None:
        execution_html = (
            '<section class="scenario"><h2>Execuções reais informadas</h2>'
            '<div class="metadata">'
            f'<span><b>Preenchimentos:</b> {_e(execution_summary.get("fills", 0))}</span>'
            f'<span><b>Decisões:</b> {_e(execution_summary.get("decisions_executed", 0))}</span>'
            f'<span><b>Valor bruto:</b> {_e(execution_summary.get("gross_sell_value", 0))}</span>'
            f'<span><b>Taxas:</b> {_e(execution_summary.get("fees", 0))}</span>'
            f'<span><b>Caixa líquido:</b> {_e(execution_summary.get("net_cash_delta", 0))}</span>'
            '</div><p class="meta">Registro auditável; não altera carteira nem envia ordens.</p></section>'
        )
    reconciliation_html = ""
    if reconciliation_summary is not None:
        reconciliation_html = (
            '<section class="scenario"><h2>Reconciliação de custódia</h2><div class="metadata">'
            f'<span><b>Confirmadas:</b> {_e(reconciliation_summary.get("confirmed", 0))}</span>'
            f'<span><b>Parciais:</b> {_e(reconciliation_summary.get("partial", 0))}</span>'
            f'<span><b>Não refletidas:</b> {_e(reconciliation_summary.get("not_reflected", 0))}</span>'
            f'<span><b>Divergências:</b> {_e(reconciliation_summary.get("variance", 0))}</span>'
            f'<span><b>Não verificáveis:</b> {_e(reconciliation_summary.get("unverifiable", 0))}</span>'
            '</div></section>'
        )
    sections = []
    for name in ("EXECUTE", "INVESTIGATE", "WAIT", "MONITOR"):
        items = groups[name]
        body = "".join(_item_card(item) for item in items)
        if not body:
            body = '<p class="empty">Nenhum item nesta fila.</p>'
        sections.append(
            f'<section id="{name.lower()}"><div class="section-head">'
            f'<h2>{GROUP_LABELS[name]}</h2><span>{len(items)}</span></div>'
            f'<div class="cards">{body}</div></section>'
        )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas Decision Cockpit</title>
<style>
:root{{--bg:#f4f6f8;--surface:#fff;--text:#17202a;--muted:#64748b;--line:#dbe2ea;
--execute:#b42318;--investigate:#b54708;--wait:#175cd3;--monitor:#475467}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font:15px/1.45 Inter,Segoe UI,Arial,sans-serif}}main{{max-width:1320px;margin:auto;padding:28px}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:22px}}
h1,h2,p{{margin-top:0}}h1{{margin-bottom:4px;font-size:28px}}.meta{{color:var(--muted)}}
.summary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:26px}}
.summary{{background:var(--surface);border:1px solid var(--line);border-top:4px solid;
border-radius:10px;padding:16px;display:flex;justify-content:space-between;align-items:center}}
.summary b{{font-size:30px}}.summary span{{color:var(--muted)}}.execute{{border-top-color:var(--execute)}}
.investigate{{border-top-color:var(--investigate)}}.wait{{border-top-color:var(--wait)}}
.monitor{{border-top-color:var(--monitor)}}section{{margin:25px 0}}.section-head{{display:flex;
align-items:center;gap:10px}}.section-head h2{{margin:0}}.section-head span{{background:#e9eef4;
border-radius:999px;padding:2px 9px}}.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
gap:12px;margin-top:10px}}.decision-card{{background:var(--surface);border:1px solid var(--line);
border-radius:10px;padding:15px}}.card-head{{display:flex;justify-content:space-between;gap:12px}}
.action{{font-size:12px;font-weight:700;background:#eef2f6;border-radius:999px;padding:4px 8px}}
.decision-card p{{margin:10px 0;color:#344054}}.metadata{{display:flex;flex-wrap:wrap;gap:8px 16px;
font-size:13px;margin-bottom:8px}}small,.empty{{color:var(--muted)}}
@media(max-width:800px){{main{{padding:16px}}header{{display:block}}.summary-grid{{grid-template-columns:repeat(2,1fr)}}
.cards{{grid-template-columns:1fr}}}}@media(prefers-color-scheme:dark){{:root{{--bg:#101828;--surface:#1d2939;
--text:#f2f4f7;--muted:#98a2b3;--line:#344054}}.decision-card p{{color:#d0d5dd}}.action,.section-head span{{background:#344054}}}}
</style></head><body><main><header><div><h1>Atlas Decision Cockpit</h1>
<p class="meta">Fila decisória consolidada · somente consultiva</p></div>
<p class="meta">Gerado em {_e(payload["generated_at"])}</p></header>
<div class="summary-grid">{summary_cards}</div>{scenario_html}{journal_html}{execution_html}{reconciliation_html}{''.join(sections)}
</main></body></html>"""


def write_decision_cockpit(
    queue: DecisionQueue,
    path: str | Path,
    *,
    scenario: PortfolioScenario | None = None,
    journal_summary: dict[str, object] | None = None,
    execution_summary: dict[str, object] | None = None,
    reconciliation_summary: dict[str, object] | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        render_decision_cockpit(
            queue, scenario=scenario, journal_summary=journal_summary,
            execution_summary=execution_summary,
            reconciliation_summary=reconciliation_summary,
        ),
        encoding="utf-8",
    )
    replace_with_retry(temporary, output)
    return output

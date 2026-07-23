from __future__ import annotations

from html import escape
from pathlib import Path

from decision.queue import DecisionQueue
from decision.status import STATUS_LABELS, STATUS_NEW, status_for
from portfolio.scenario import PortfolioScenario
from storage.atomic_write import replace_with_retry


GROUP_LABELS = {
    "EXECUTE": "Executar",
    "INVESTIGATE": "Investigar",
    "WAIT": "Aguardar",
    "MONITOR": "Monitorar",
}

# Interação mínima: só funciona quando a página é servida por api.server
# (mesma origem que POST /journal). Aberta via file://, os botões ficam
# desativados e um aviso explica como habilitar. Sem dependências externas.
_COCKPIT_SCRIPT = """<script>
(function () {
  var MAP = {
    ACCEPTED: { slug: "decidido", label: "Decidido" },
    DEFERRED: { slug: "em_analise", label: "Em análise" },
    REJECTED: { slug: "descartado", label: "Descartado" }
  };
  var live = location.protocol === "http:" || location.protocol === "https:";
  if (!live) {
    var notice = document.getElementById("notice");
    if (notice) notice.style.display = "block";
    document.querySelectorAll(".review button").forEach(function (b) {
      b.disabled = true;
      b.title = "Abra via http://127.0.0.1:8000/cockpit para registrar.";
    });
    return;
  }
  document.querySelectorAll(".review").forEach(function (row) {
    var id = row.getAttribute("data-decision-id");
    row.querySelectorAll("button[data-status]").forEach(function (button) {
      button.addEventListener("click", function () {
        var status = button.getAttribute("data-status");
        var reason = window.prompt("Motivo da revisão (" + status + "):");
        if (reason === null) return;
        reason = reason.trim();
        if (!reason) { window.alert("Motivo é obrigatório."); return; }
        row.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
        fetch("/journal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision_id: id, status: status, reason: reason })
        }).then(function (resp) {
          return resp.json().then(function (data) { return { ok: resp.ok, data: data }; });
        }).then(function (result) {
          if (!result.ok) {
            window.alert("Erro: " + (result.data.error || "falha ao registrar."));
            row.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
            return;
          }
          var chip = row.querySelector(".status");
          var mapped = MAP[status];
          if (chip && mapped) {
            chip.className = "status status-" + mapped.slug;
            chip.textContent = mapped.label;
          }
        }).catch(function () {
          window.alert("Falha de rede ao registrar a revisão.");
          row.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
        });
      });
    });
  });
})();
</script>"""

DELTA_FIELD_LABELS = {
    "group": "Fila",
    "investment_score": "Score",
    "opportunity_score": "Opportunity",
    "conviction_score": "Convicção",
    "decision_confidence": "Confiança",
    "data_coverage": "Cobertura",
    "risk_penalty": "Risco",
    "investment_thesis": "Tese",
}


def _e(value: object) -> str:
    return escape(str(value or ""))


def _delta_label(item: dict[str, object]) -> str:
    name = str(item.get("company_name") or item.get("symbol") or "")
    return f"{name} <small>({_e(item.get('symbol'))})</small>"


def _change_phrase(change: dict[str, object]) -> str:
    field = str(change.get("field", ""))
    label = DELTA_FIELD_LABELS.get(field, field)
    if field == "investment_thesis":
        return f"{_e(label)} revista"
    origin = change.get("from")
    target = change.get("to")
    if origin is None:
        return f"{_e(label)}: nova evidência ({_e(target)})"
    if target is None:
        return f"{_e(label)}: evidência perdida"
    if "delta" in change:
        signal = "+" if float(change["delta"]) >= 0 else ""
        return f"{_e(label)} {_e(origin)}→{_e(target)} ({signal}{_e(change['delta'])})"
    return f"{_e(label)} {_e(origin)}→{_e(target)}"


def _delta_section(delta: dict[str, object] | None) -> str:
    if delta is None:
        return ""
    baseline = delta.get("baseline_generated_at")
    if not baseline:
        return (
            '<section class="delta"><h2>Mudou desde a última execução</h2>'
            '<p class="meta">Primeira execução registrada — sem base de comparação.</p>'
            "</section>"
        )
    summary = delta.get("summary", {})
    blocks: list[str] = []

    transitions = delta.get("action_transitions", ())
    if transitions:
        rows = "".join(
            f'<li><b>{_delta_label(item)}</b>: '
            f'{_e(item.get("from_action"))} → <b>{_e(item.get("action"))}</b> '
            f'({_e(item.get("from_group"))} → {_e(item.get("group"))})</li>'
            for item in transitions
        )
        blocks.append(
            f'<div class="delta-block"><h3>Mudança de ação ({len(transitions)})</h3>'
            f"<ul>{rows}</ul></div>"
        )

    changed = delta.get("changed", ())
    if changed:
        rows = "".join(
            f'<li><b>{_delta_label(item)}</b> ({_e(item.get("action"))}): '
            + "; ".join(_change_phrase(change) for change in item.get("changes", ()))
            + "</li>"
            for item in changed
        )
        blocks.append(
            f'<div class="delta-block"><h3>Evidência/fila alterada ({len(changed)})</h3>'
            f"<ul>{rows}</ul></div>"
        )

    entered = delta.get("entered", ())
    if entered:
        rows = "".join(
            f'<li><b>{_delta_label(item)}</b> — {_e(item.get("action"))} '
            f'({GROUP_LABELS.get(str(item.get("group")), _e(item.get("group")))})</li>'
            for item in entered
        )
        blocks.append(
            f'<div class="delta-block"><h3>Entrou na fila ({len(entered)})</h3>'
            f"<ul>{rows}</ul></div>"
        )

    exited = delta.get("exited", ())
    if exited:
        rows = "".join(
            f'<li><b>{_delta_label(item)}</b> — saiu de {_e(item.get("action"))}</li>'
            for item in exited
        )
        blocks.append(
            f'<div class="delta-block"><h3>Saiu da fila ({len(exited)})</h3>'
            f"<ul>{rows}</ul></div>"
        )

    if not blocks:
        body = (
            '<p class="meta">Nenhuma mudança material desde '
            f'{_e(baseline)} · {_e(summary.get("unchanged", 0))} itens estáveis.</p>'
        )
    else:
        body = "".join(blocks) + (
            f'<p class="meta">{_e(summary.get("unchanged", 0))} itens sem mudança '
            f"material (ocultos) · base {_e(baseline)}.</p>"
        )
    return f'<section class="delta"><h2>Mudou desde a última execução</h2>{body}</section>'


def _review_controls(item: dict[str, object], statuses: dict[str, str]) -> str:
    decision_id = str(item.get("decision_id", ""))
    if not decision_id:
        return ""
    status = status_for(statuses, decision_id)
    return (
        f'<div class="review" data-decision-id="{_e(decision_id)}">'
        f'<span class="status status-{_e(status)}">{_e(STATUS_LABELS.get(status, status))}</span>'
        '<button type="button" data-status="ACCEPTED">Aceitar</button>'
        '<button type="button" data-status="DEFERRED">Adiar</button>'
        '<button type="button" data-status="REJECTED">Rejeitar</button>'
        "</div>"
    )


def _item_card(item: dict[str, object], statuses: dict[str, str] | None = None) -> str:
    metadata = []
    for key, label in (
        ("investment_score", "Score"),
        ("opportunity_score", "Opportunity"),
        ("conviction_score", "Convicção"),
        ("decision_confidence", "Confiança"),
        ("data_coverage", "Cobertura"),
        ("risk_penalty", "Risco"),
        ("current_weight", "Peso"),
        ("analytical_origin", "Origem"),
        ("entry_rank", "Rank entrada"),
        ("entry_score", "Score entrada"),
        ("review_due_at", "Revisar em"),
    ):
        value = item.get(key)
        if value is not None and value != "":
            metadata.append(f"<span><b>{_e(label)}:</b> {_e(value)}</span>")
    thesis_html = (
        f'<p><b>Tese:</b> {_e(item.get("investment_thesis"))}</p>'
        if item.get("investment_thesis")
        else ""
    )
    return (
        '<article class="decision-card">'
        f'<div class="card-head"><strong>{_e(item.get("company_name")) or _e(item.get("symbol"))} '
        f'<small>({_e(item.get("symbol"))})</small></strong>'
        f'<span class="action">{_e(item.get("action"))}</span></div>'
        f'<p>{_e(item.get("reason")) or "Sem justificativa publicada."}</p>'
        f'{thesis_html}'
        f'<div class="metadata">{"".join(metadata)}</div>'
        f'<small>{_e(item.get("engine"))} · consultivo</small>'
        f'{_review_controls(item, statuses or {})}'
        "</article>"
    )


def _opportunity_card(item: dict[str, object]) -> str:
    metadata = []
    for key, label in (
        ("opportunity_score", "Opportunity"),
        ("conviction_score", "Convicção"),
        ("decision_confidence", "Confiança"),
        ("data_coverage", "Cobertura"),
        ("risk_penalty", "Risco"),
    ):
        value = item.get(key)
        if value is not None and value != "":
            metadata.append(f"<span><b>{_e(label)}:</b> {_e(value)}</span>")
    thesis_html = (
        f'<p><b>Tese:</b> {_e(item.get("investment_thesis"))}</p>'
        if item.get("investment_thesis")
        else ""
    )
    drivers = item.get("decision_drivers") or ()
    drivers_html = (
        f'<p><b>Por quê:</b> {_e("; ".join(str(d) for d in drivers))}</p>'
        if drivers
        else ""
    )
    return (
        '<article class="decision-card">'
        f'<div class="card-head"><strong>{_e(item.get("company_name")) or _e(item.get("symbol"))} '
        f'<small>({_e(item.get("symbol"))})</small></strong>'
        f'<span class="action">{_e(item.get("action")) or "CANDIDATA"}</span></div>'
        f'{drivers_html}'
        f'{thesis_html}'
        f'<div class="metadata">{"".join(metadata)}</div>'
        f'<small>fora da carteira · consultivo</small>'
        "</article>"
    )


def _health_section(health: dict[str, object] | None) -> str:
    if not health:
        return ""
    warnings = health.get("warnings") or ()
    warnings_html = "".join(f"<li>{_e(w)}</li>" for w in warnings) or (
        "<li>Sem alertas de alocação.</li>"
    )
    return (
        '<section class="scenario"><h2>Saúde da carteira</h2><div class="metadata">'
        f'<span><b>Valor:</b> {_e(health.get("currency", "USD"))} '
        f'{_e(health.get("total_value", "-"))}</span>'
        f'<span><b>Qualidade:</b> {_e(health.get("quality_score", "-"))} '
        f'({_e(health.get("quality_rating", "-"))})</span>'
        f'<span><b>Caixa:</b> {_e(health.get("cash_weight", "-"))}</span>'
        f'<span><b>Maior posição:</b> {_e(health.get("largest_position_weight", "-"))}</span>'
        f'</div><ul>{warnings_html}</ul></section>'
    )


def render_decision_cockpit(
    queue: DecisionQueue,
    *,
    delta: dict[str, object] | None = None,
    statuses: dict[str, str] | None = None,
    opportunities: tuple[dict[str, object], ...] = (),
    portfolio_health: dict[str, object] | None = None,
    outcomes_line: str | None = None,
    scenario: PortfolioScenario | None = None,
    journal_summary: dict[str, object] | None = None,
    execution_summary: dict[str, object] | None = None,
    reconciliation_summary: dict[str, object] | None = None,
) -> str:
    statuses = statuses or {}
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
    delta_html = _delta_section(delta)

    def _group_block(name: str) -> str:
        items = groups[name]
        body = "".join(_item_card(item, statuses) for item in items) or (
            '<p class="empty">Nenhum item nesta fila.</p>'
        )
        return (
            f'<div class="section-head"><h3>{GROUP_LABELS[name]}</h3>'
            f'<span>{len(items)}</span></div><div class="cards">{body}</div>'
        )

    # Tier 1 — AÇÃO: decisões sobre a carteira que pedem ação/revisão agora.
    action_count = summary["execute"] + summary["investigate"]
    action_html = (
        f'<section id="acao" class="tier tier-action">'
        f'<div class="tier-head"><h2>Agir agora</h2><span>{action_count}</span></div>'
        f'{_group_block("EXECUTE")}{_group_block("INVESTIGATE")}</section>'
    )

    # Tier 2 — OPORTUNIDADE: candidatas de compra fora da carteira e gatilhos
    # de entrada aguardando (watchlist waiting_trigger).
    opportunity_cards = "".join(_opportunity_card(item) for item in opportunities)
    wait_items = groups["WAIT"]
    wait_cards = "".join(_item_card(item, statuses) for item in wait_items)
    opportunity_body = opportunity_cards + wait_cards or (
        '<p class="empty">Nenhuma oportunidade qualificada nesta execução.</p>'
    )
    opportunity_count = len(opportunities) + len(wait_items)
    opportunity_html = (
        f'<section id="oportunidade" class="tier tier-opportunity">'
        f'<div class="tier-head"><h2>Oportunidades</h2><span>{opportunity_count}</span></div>'
        f'<div class="cards">{opportunity_body}</div></section>'
    )

    # Tier 3 — MONITORAMENTO: sem ação; colapsado para não competir com o topo.
    monitor_items = groups["MONITOR"]
    monitor_cards = "".join(_item_card(item, statuses) for item in monitor_items) or (
        '<p class="empty">Nenhum item em monitoramento.</p>'
    )
    monitor_html = (
        f'<section id="monitor" class="tier tier-monitor"><details>'
        f'<summary><h2>Acompanhar</h2><span>{len(monitor_items)}</span>'
        '<em>sem ação — clique para expandir</em></summary>'
        f'<div class="cards">{monitor_cards}</div></details></section>'
    )

    health_html = _health_section(portfolio_health)
    outcomes_html = (
        f'<section class="scenario"><h2>Evidência histórica</h2>'
        f'<p>{_e(outcomes_line)}</p></section>'
        if outcomes_line
        else ""
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
.delta{{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--wait);
border-radius:10px;padding:16px 20px}}.delta h2{{margin-bottom:6px}}.delta-block{{margin:12px 0}}
.delta-block h3{{margin:0 0 6px;font-size:14px}}.delta ul{{margin:0;padding-left:18px}}
.delta li{{margin:4px 0;color:#344054}}
.tier{{border-left:4px solid var(--line);padding-left:16px}}.tier-action{{border-left-color:var(--execute)}}
.tier-opportunity{{border-left-color:#12805c}}.tier-monitor{{border-left-color:var(--monitor)}}
.tier-head{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}.tier-head h2{{margin:0}}
.tier-head span,.section-head span,summary span{{background:#e9eef4;border-radius:999px;padding:2px 9px;font-size:14px}}
.section-head{{display:flex;align-items:center;gap:8px;margin:14px 0 0}}.section-head h3{{margin:0;font-size:15px;color:var(--muted)}}
.tier-monitor summary{{display:flex;align-items:center;gap:10px;cursor:pointer;list-style:none}}
.tier-monitor summary h2{{margin:0}}.tier-monitor summary em{{color:var(--muted);font-style:normal;font-size:13px}}
.tier-monitor summary::-webkit-details-marker{{display:none}}
.review{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:10px;
border-top:1px solid var(--line);padding-top:10px}}.review button{{font:inherit;font-size:12px;
border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:6px;
padding:3px 9px;cursor:pointer}}.review button:hover{{border-color:var(--muted)}}
.status{{font-size:12px;font-weight:700;border-radius:999px;padding:3px 9px;margin-right:auto}}
.status-novo{{background:#eef2f6;color:var(--muted)}}.status-em_analise{{background:#fff4e5;color:#b54708}}
.status-decidido{{background:#e7f0ff;color:#175cd3}}.status-executado{{background:#e6f4ea;color:#12805c}}
.status-descartado{{background:#fdeceb;color:#b42318}}
.notice{{background:#fff4e5;color:#7a4d00;border:1px solid #f0c98a;border-radius:8px;
padding:10px 14px;margin-bottom:18px;font-size:14px;display:none}}
@media(max-width:800px){{main{{padding:16px}}header{{display:block}}.summary-grid{{grid-template-columns:repeat(2,1fr)}}
.cards{{grid-template-columns:1fr}}}}@media(prefers-color-scheme:dark){{:root{{--bg:#101828;--surface:#1d2939;
--text:#f2f4f7;--muted:#98a2b3;--line:#344054}}.decision-card p,.delta li{{color:#d0d5dd}}.action,.tier-head span,.section-head span,summary span{{background:#344054}}
.status-novo{{background:#344054;color:#d0d5dd}}}}
</style></head><body><main><header><div><h1>Atlas — Hoje</h1>
<p class="meta">Mesa de decisão consolidada · agir agora, oportunidades e acompanhamento · somente consultiva</p></div>
<p class="meta">Gerado em {_e(payload["generated_at"])}</p></header>
<div id="notice" class="notice">Para registrar revisões (Aceitar/Adiar/Rejeitar), abra esta página via <b>http://127.0.0.1:8000/cockpit</b> (servidor local <code>python -m api.server</code>). No modo arquivo os botões ficam desativados.</div>
<div class="summary-grid">{summary_cards}</div>{delta_html}{action_html}{opportunity_html}{scenario_html}{journal_html}{execution_html}{reconciliation_html}{monitor_html}{health_html}{outcomes_html}
</main>{_COCKPIT_SCRIPT}</body></html>"""


def write_decision_cockpit(
    queue: DecisionQueue,
    path: str | Path,
    *,
    delta: dict[str, object] | None = None,
    statuses: dict[str, str] | None = None,
    opportunities: tuple[dict[str, object], ...] = (),
    portfolio_health: dict[str, object] | None = None,
    outcomes_line: str | None = None,
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
            queue, delta=delta, statuses=statuses, opportunities=opportunities,
            portfolio_health=portfolio_health, outcomes_line=outcomes_line,
            scenario=scenario, journal_summary=journal_summary,
            execution_summary=execution_summary,
            reconciliation_summary=reconciliation_summary,
        ),
        encoding="utf-8",
    )
    replace_with_retry(temporary, output)
    return output

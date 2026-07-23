from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Sequence

from outcomes.analytics import OutcomeAnalyticsReport
from portfolio.report import PortfolioReport
from reports.report_models import CompanyReport


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _label(report: CompanyReport) -> str:
    return f"{report.company_name} ({report.symbol})"


def _metrics(report: CompanyReport) -> str:
    return (
        "<dl class=\"metrics\">"
        f"<div><dt>Opportunity</dt><dd>{_number(report.opportunity_score)}</dd></div>"
        f"<div><dt>Convicção</dt><dd>{_number(report.conviction_score)}</dd></div>"
        f"<div><dt>Confiança</dt><dd>{_number(report.decision_confidence)}</dd></div>"
        f"<div><dt>Cobertura</dt><dd>{_number(report.data_coverage)}</dd></div>"
        f"<div><dt>Risco</dt><dd>{_number(report.risk_penalty)}</dd></div>"
        "</dl>"
    )


def _company_card(
    report: CompanyReport,
    *,
    action: str,
    context: str,
    weight: float | None = None,
) -> str:
    allocation = (
        f"<p><strong>Peso atual:</strong> {_percent(weight)}</p>"
        if weight is not None
        else ""
    )
    risks = "; ".join(report.risks) or "Sem risco crítico identificado"
    return (
        "<article class=\"card\">"
        f"<h3>{escape(_label(report))}</h3>"
        f"<p class=\"action\">{escape(action)}</p>"
        f"<p><strong>Decisão Atlas:</strong> {escape(report.decision_rating)} — {escape(report.suggested_action)}</p>"
        f"{allocation}"
        f"{_metrics(report)}"
        f"<p><strong>Por quê:</strong> {escape(context)}</p>"
        f"<p><strong>Tese:</strong> {escape(report.investment_thesis)}</p>"
        f"<p><strong>Riscos:</strong> {escape(risks)}</p>"
        "</article>"
    )


def render_decision_brief(
    reports: Sequence[CompanyReport],
    *,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> str:
    by_symbol = {report.symbol: report for report in reports}
    held_weights = (
        portfolio_report.allocation.get("by_symbol", {})
        if portfolio_report is not None
        else {}
    )
    actions = (
        portfolio_report.rebalance.get("actions", ())
        if portfolio_report is not None
        else ()
    )
    action_by_symbol = {
        str(action.get("symbol", "")).upper(): action
        for action in actions
    }
    urgent = [
        action for action in actions
        if str(action.get("action", "")).upper() in {"SELL", "TRIM", "REVISAR"}
    ]
    urgent_cards = []
    for action in urgent:
        symbol = str(action.get("symbol", "")).upper()
        report = by_symbol.get(symbol)
        if report is not None:
            urgent_cards.append(
                _company_card(
                    report,
                    action=str(action.get("action", "")),
                    context=str(action.get("reason", "")),
                    weight=held_weights.get(symbol),
                )
            )
    candidates = sorted(
        (
            report for report in reports
            if report.symbol not in held_weights
            and report.decision in {"BUY", "ACCUMULATE"}
        ),
        key=lambda report: report.opportunity_score or 0.0,
        reverse=True,
    )[:5]
    candidate_cards = [
        _company_card(
            report,
            action="CANDIDATA",
            context="; ".join(report.decision_drivers),
        )
        for report in candidates
    ]
    summary = portfolio_report.summary if portfolio_report else {}
    warnings = portfolio_report.warnings if portfolio_report else ()
    hit_rate = outcome_report.hit_rate if outcome_report else None
    outcomes = (
        "Ainda não há amostra direcional madura."
        if hit_rate is None or hit_rate.eligible_count == 0
        else (
            f"Hit rate direcional: {hit_rate.hit_rate:.1f}% "
            f"({hit_rate.hit_count}/{hit_rate.eligible_count})."
        )
    )
    urgent_html = "".join(urgent_cards) or "<p>Nenhuma ação imediata.</p>"
    candidates_html = "".join(candidate_cards) or "<p>Nenhuma candidata qualificada nesta execução.</p>"
    warnings_html = "".join(f"<li>{escape(warning)}</li>" for warning in warnings) or "<li>Sem alertas de alocação.</li>"
    return f"""<!doctype html>
<html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>Atlas — Relatório de Decisão</title>
<style>body{{font-family:Arial,sans-serif;margin:32px auto;max-width:1120px;color:#18212b;background:#f6f8fa}}header,section{{background:white;border:1px solid #d8dee4;border-radius:10px;padding:22px;margin:16px 0}}h1,h2,h3{{margin-top:0}}.subtitle{{color:#57606a}}.action{{font-weight:bold;color:#9a6700}}.card{{border-top:1px solid #d8dee4;padding:18px 0}}.metrics{{display:flex;gap:18px;flex-wrap:wrap}}.metrics div{{min-width:100px}}dt{{font-size:12px;color:#57606a}}dd{{margin:3px 0;font-weight:bold}}li{{margin:7px 0}}</style>
</head><body><header><h1>Relatório de Decisão</h1><p class=\"subtitle\">Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} — leitura operacional consolidada; sugestões são consultivas e não executam ordens.</p></header>
<section><h2>1. O que exige decisão agora</h2>{urgent_html}</section>
<section><h2>2. Oportunidades fora da carteira</h2>{candidates_html}</section>
<section><h2>3. Saúde da carteira</h2><p><strong>Valor:</strong> {escape(str(summary.get('currency', 'USD')))} {float(summary.get('total_value', 0.0)):,.2f} · <strong>Qualidade:</strong> {_number(summary.get('quality_score'))} ({escape(str(summary.get('quality_rating', '-')) )}) · <strong>Caixa:</strong> {_percent(summary.get('cash_weight'))} · <strong>Maior posição:</strong> {_percent(summary.get('largest_position_weight'))}</p><ul>{warnings_html}</ul></section>
<section><h2>4. Evidência histórica</h2><p>{escape(outcomes)}</p></section>
<section><h2>Como ler os números</h2><p>Opportunity e Convicção medem atratividade e solidez (0–100). Confiança e Cobertura mostram a suficiência dos dados; Risco é a penalidade aplicada. Uma tese só deve orientar ação quando esses números e as evidências estiverem consistentes.</p></section>
</body></html>"""


def write_decision_brief(
    reports: Sequence[CompanyReport],
    output_path: Path,
    *,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_decision_brief(
            reports,
            portfolio_report=portfolio_report,
            outcome_report=outcome_report,
        ),
        encoding="utf-8",
    )
    return path

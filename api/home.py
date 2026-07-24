"""
Página inicial humana do Atlas -- a "porta única" (Fase 1 de usabilidade).

`render_home` monta um HTML self-contido (CSS inline, sem dependência externa,
tema claro/escuro) que lista os pontos de entrada que o usuário de fato abre --
o cockpit "Hoje", o relatório completo -- junto com o frescor da última execução
e um lembrete de como atualizar. É estritamente read-only: só olha o que os
motores já produziram em `output/relatorios/` e `output/dados/`; nunca dispara
uma run nem toca em config.

O servidor (`api/server.py`) serve este HTML em `/` apenas quando o cliente
pede `text/html` (navegador); `urllib`/scripts continuam recebendo o índice
JSON da API, preservando o contrato programático.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _reports_dir(root: Path) -> Path:
    return root / "output" / "relatorios"


def _dashboard_generated_at(root: Path) -> str | None:
    path = root / "output" / "dados" / "dashboard.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    value = data.get("generated_at")
    return str(value) if value else None


def _humanize_age(iso_value: str | None, mtime: float | None) -> str:
    """Frescor legível: prefere o `generated_at` do dashboard, cai no mtime."""
    reference: datetime | None = None
    if iso_value:
        try:
            reference = datetime.fromisoformat(iso_value)
        except ValueError:
            reference = None
    if reference is None and mtime is not None:
        reference = datetime.fromtimestamp(mtime)
    if reference is None:
        return "nunca executado"
    if reference.tzinfo is not None:
        reference = reference.astimezone().replace(tzinfo=None)
    delta = datetime.now() - reference
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        rel = f"há {days} dia{'s' if days != 1 else ''}"
    elif hours > 0:
        rel = f"há {hours} h"
    elif minutes > 0:
        rel = f"há {minutes} min"
    else:
        rel = "agora mesmo"
    stamp = reference.strftime("%d/%m/%Y %H:%M")
    stale = " stale" if days >= 2 else ""
    return f'<span class="fresh{stale}">{stamp} · {rel}</span>'


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def render_home(root: Path) -> str:
    """Retorna o HTML da página inicial, refletindo o estado atual em disco."""
    reports = _reports_dir(root)
    cockpit = reports / "decision_cockpit.html"
    report = reports / "atlas_report_latest.html"
    brief = reports / "morning_brief.md"
    excel = reports / "latest.xlsx"

    generated_at = _dashboard_generated_at(root)
    freshness = _humanize_age(generated_at, _mtime(cockpit) or _mtime(report))
    has_run = cockpit.exists() or report.exists()

    def card(href: str, exists: bool, kicker: str, title: str, desc: str) -> str:
        if exists:
            return (
                f'<a class="card live" href="{href}">'
                f'<div class="k">{kicker}</div><h2>{title} <span class="go">→</span></h2>'
                f'<p>{desc}</p></a>'
            )
        return (
            f'<div class="card dead" aria-disabled="true">'
            f'<div class="k">{kicker}</div><h2>{title}</h2>'
            f'<p>{desc}</p><p class="muted">Ainda não gerado — rode uma atualização.</p></div>'
        )

    aux = []
    if brief.exists():
        aux.append('<li><b>Morning Brief</b> — <code>output/relatorios/morning_brief.md</code></li>')
    if excel.exists():
        aux.append('<li><b>Excel</b> — <code>output/relatorios/latest.xlsx</code></li>')
    aux_html = (
        '<div class="aux"><div class="k">Também disponível</div><ul>'
        + "".join(aux)
        + "</ul></div>"
        if aux
        else ""
    )

    empty_banner = (
        ""
        if has_run
        else '<div class="banner">Nenhuma execução encontrada ainda. '
        'Rode <code>python atlas.py hoje</code> (ou use o menu) para gerar os relatórios.</div>'
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas — Início</title>
<style>
:root{{--bg:#f7f8fa;--surface:#fff;--surface-2:#f0f2f6;--ink:#141922;--ink-2:#48505e;--ink-3:#79808d;
--line:#e2e6ec;--accent:#1f6f6b;--accent-ink:#0e4744;--accent-soft:#e2f0ee;--warn:#b6791f;--warn-soft:#f8efdd;
--shadow:0 1px 2px rgba(16,24,40,.05),0 6px 22px rgba(16,24,40,.07)}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1016;--surface:#151a22;--surface-2:#1b212b;--ink:#e7ebf1;
--ink-2:#aab3c0;--ink-3:#78808d;--line:#242c38;--accent:#4dc3ba;--accent-ink:#8fe0d8;--accent-soft:#12312e;
--warn:#e0af58;--warn-soft:#33280f;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 26px rgba(0,0,0,.4)}}}}
:root[data-theme="dark"]{{--bg:#0d1016;--surface:#151a22;--surface-2:#1b212b;--ink:#e7ebf1;--ink-2:#aab3c0;
--ink-3:#78808d;--line:#242c38;--accent:#4dc3ba;--accent-ink:#8fe0d8;--accent-soft:#12312e;--warn:#e0af58;--warn-soft:#33280f}}
:root[data-theme="light"]{{--bg:#f7f8fa;--surface:#fff;--surface-2:#f0f2f6;--ink:#141922;--ink-2:#48505e;
--ink-3:#79808d;--line:#e2e6ec;--accent:#1f6f6b;--accent-ink:#0e4744;--accent-soft:#e2f0ee;--warn:#b6791f;--warn-soft:#f8efdd}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
line-height:1.55;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:920px;margin:0 auto;padding:clamp(28px,6vw,64px) 22px 80px}}
.brand{{display:flex;align-items:center;gap:12px;margin-bottom:30px}}
.mark{{width:38px;height:38px;border-radius:10px;background:radial-gradient(circle at 30% 30%,var(--accent),var(--accent-ink));
display:grid;place-items:center;color:#fff;font-weight:700;font-size:19px;box-shadow:var(--shadow)}}
.brand b{{font-size:17px;letter-spacing:.2px}}.brand small{{display:block;color:var(--ink-3);font-size:12px}}
h1{{font-size:clamp(26px,5vw,38px);letter-spacing:-.02em;margin:0 0 6px;font-weight:700}}
.sub{{color:var(--ink-2);font-size:16px;margin:0 0 4px}}
.status{{display:inline-flex;gap:8px;align-items:center;margin:20px 0 26px;font-size:13.5px;color:var(--ink-2);
background:var(--surface);border:1px solid var(--line);padding:7px 13px;border-radius:999px;box-shadow:var(--shadow)}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--accent)}}
.fresh{{font-variant-numeric:tabular-nums;color:var(--ink)}}.fresh.stale{{color:var(--warn)}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media (max-width:620px){{.grid{{grid-template-columns:1fr}}}}
.card{{display:block;text-decoration:none;color:inherit;background:var(--surface);border:1px solid var(--line);
border-radius:14px;padding:22px 22px 20px;box-shadow:var(--shadow);transition:transform .12s ease,border-color .12s ease}}
.card.live:hover{{transform:translateY(-2px);border-color:var(--accent)}}
.card.dead{{opacity:.62}}
.card .k{{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--accent);font-weight:600;margin-bottom:9px}}
.card h2{{font-size:20px;margin:0 0 6px;font-weight:650;display:flex;align-items:center;gap:8px}}
.card .go{{color:var(--accent);font-weight:700}}
.card p{{margin:0;color:var(--ink-2);font-size:14px}}.card p.muted{{color:var(--warn);margin-top:8px;font-size:13px}}
.banner{{background:var(--warn-soft);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:24px;font-size:14px}}
.aux{{margin-top:28px;border-top:1px solid var(--line);padding-top:20px}}
.aux .k{{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--ink-3);font-weight:600;margin-bottom:8px}}
.aux ul{{margin:0;padding-left:18px;color:var(--ink-2);font-size:14px}}.aux li{{margin:4px 0}}
.update{{margin-top:28px;background:var(--surface-2);border:1px solid var(--line);border-radius:12px;padding:16px 18px}}
.update .k{{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--ink-3);font-weight:600;margin-bottom:10px}}
.update p{{margin:0 0 6px;font-size:14px;color:var(--ink-2)}}
code{{font-family:ui-monospace,Consolas,monospace;font-size:.88em;background:var(--surface);border:1px solid var(--line);
padding:.12em .42em;border-radius:5px;color:var(--ink)}}
.toggle{{position:fixed;top:14px;right:16px;background:var(--surface);border:1px solid var(--line);color:var(--ink-2);
border-radius:999px;padding:7px 13px;font-size:12.5px;cursor:pointer;box-shadow:var(--shadow);font-family:inherit}}
.toggle:hover{{color:var(--ink);border-color:var(--accent)}}
footer{{margin-top:34px;color:var(--ink-3);font-size:12.5px}}
a:focus-visible,.toggle:focus-visible{{outline:2px solid var(--accent);outline-offset:2px;border-radius:8px}}
</style></head><body>
<button class="toggle" id="t" aria-label="Alternar tema">◐ Tema</button>
<div class="wrap">
  <div class="brand"><div class="mark">A</div><div><b>Atlas Investment OS</b><small>Plataforma consultiva de decisão · v1.2.0</small></div></div>
  <h1>Bom te ver.</h1>
  <p class="sub">Comece pelo que precisa de você hoje.</p>
  <div class="status"><span class="dot"></span>Última atualização: {freshness}</div>
  {empty_banner}
  <div class="grid">
    {card("/cockpit", cockpit.exists(), "Decisão do dia", "Atlas — Hoje", "Agir agora, oportunidades e o que só acompanhar. Comece aqui.")}
    {card("/report", report.exists(), "Aprofundar", "Relatório completo", "Scores, fórmulas, teses e detalhe por ativo.")}
  </div>
  {aux_html}
  <div class="update">
    <div class="k">Atualizar os dados</div>
    <p><b>Rápido (carteira):</b> <code>python atlas.py hoje</code></p>
    <p><b>Completo (com screener):</b> <code>python atlas.py full</code></p>
    <p><b>Um ticker:</b> <code>python atlas.py ticker MSFT</code> — ou use o menu do <code>Atlas.bat</code>.</p>
  </div>
  <footer>Servido localmente em 127.0.0.1 · read-only · o Atlas não executa ordens.</footer>
</div>
<script>
document.getElementById('t').addEventListener('click',function(){{
  var r=document.documentElement,c=r.getAttribute('data-theme');
  if(!c)c=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  r.setAttribute('data-theme',c==='dark'?'light':'dark');
}});
</script>
</body></html>"""

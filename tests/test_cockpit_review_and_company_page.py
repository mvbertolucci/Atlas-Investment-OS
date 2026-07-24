"""
Trava o contrato da revisão por lista suspensa e da página da empresa.

Dois comportamentos novos da Fase 1 de usabilidade:

1. O cockpit oferece motivos de revisão em `<select>` -- ESPECÍFICOS do card
   (derivados da razão que o próprio motor publicou) antes dos genéricos. A
   regra que importa é a de não inventar evidência: uma opção específica só
   pode aparecer se o motor citou aquele sinal.
2. Toda empresa linka para uma página com os números já coletados
   (`/company/SYM`), que resolve para o one-pager do símbolo ou para a âncora
   do ativo no relatório completo.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

import api.server as server_module
from api.server import DashboardRequestHandler
from decision.cockpit import _company_link, _reason_options, _review_controls


SELL_ITEM = {
    "decision_id": "d1",
    "symbol": "FMC",
    "company_name": "FMC Corporation",
    "action": "SELL",
    "engine": "portfolio.sell_rules",
    "reason": "fundamental_decay: F-Score caiu 3 pontos; valuation_stretch: upside -18%",
    "missing_evidence": ["F-Score Piotroski (anual)"],
}


def test_specific_reasons_reflect_the_rules_the_engine_cited() -> None:
    options = _reason_options(SELL_ITEM)
    accepted = options["ACCEPTED"]
    assert any("fundamentos" in reason for reason in accepted)
    assert any("alvo" in reason for reason in accepted)
    # O motor não citou solvência neste card -- não pode aparecer.
    assert not any("solvência" in reason for reason in accepted)


def test_specific_reasons_come_before_generic_ones() -> None:
    accepted = _reason_options(SELL_ITEM)["ACCEPTED"]
    specific = next(i for i, r in enumerate(accepted) if "fundamentos" in r)
    generic = next(i for i, r in enumerate(accepted) if "evidência apresentada" in r)
    assert specific < generic


def test_missing_evidence_becomes_a_deferral_reason() -> None:
    deferred = _reason_options(SELL_ITEM)["DEFERRED"]
    assert any("F-Score Piotroski (anual)" in reason for reason in deferred)


def test_every_status_keeps_a_free_text_escape_hatch() -> None:
    options = _reason_options(SELL_ITEM)
    for status in ("ACCEPTED", "DEFERRED", "REJECTED"):
        assert options[status][-1] == "Outro (escrever)"
        assert len(options[status]) == len(set(options[status]))


def test_item_without_engine_reason_still_offers_generic_reasons() -> None:
    options = _reason_options({"decision_id": "x", "symbol": "ABC"})
    assert options["ACCEPTED"]
    assert options["ACCEPTED"][-1] == "Outro (escrever)"


def test_review_controls_embed_reasons_as_valid_json() -> None:
    html = _review_controls(SELL_ITEM, {})
    marker = 'data-reasons="'
    raw = html.split(marker, 1)[1].split('"', 1)[0]
    parsed = json.loads(raw.replace("&quot;", '"').replace("&amp;", "&"))
    assert set(parsed) == {"ACCEPTED", "DEFERRED", "REJECTED"}


def test_company_link_points_at_the_company_page() -> None:
    html = _company_link(SELL_ITEM)
    assert 'href="/company/FMC"' in html
    assert 'data-symbol="FMC"' in html
    assert "FMC Corporation" in html


def test_company_link_survives_missing_symbol() -> None:
    assert "href" not in _company_link({"company_name": "Sem símbolo"})


@pytest.fixture()
def base_url(tmp_path: Path, monkeypatch) -> Iterator[str]:
    reports = tmp_path / "output" / "relatorios"
    reports.mkdir(parents=True)
    (reports / "atlas_report_latest.html").write_text(
        "<!doctype html><title>relatorio</title>", encoding="utf-8"
    )
    # Raiz de dados isolada: sem isso a rota leria o dashboard/histórico reais
    # do projeto e nenhum fallback seria exercitado.
    monkeypatch.setattr(server_module, "ROOT", tmp_path)
    monkeypatch.setattr(server_module, "REPORTS_DIR", reports)
    monkeypatch.setattr(
        server_module, "REPORT_PATH", reports / "atlas_report_latest.html"
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", reports
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def _open(url: str):
    return urllib.request.build_opener(_NoRedirect).open(url, timeout=5)


def test_company_route_falls_back_to_the_report_anchor(base_url) -> None:
    base, _ = base_url
    with pytest.raises(urllib.error.HTTPError) as exc:
        _open(f"{base}/company/FMC")
    assert exc.value.code == 302
    assert exc.value.headers.get("Location") == "/report#ticker-FMC"


def _seed_company(root: Path, symbol: str = "FMC") -> None:
    data_dir = root / "output" / "dados"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "dashboard.json").write_text(
        json.dumps(
            {
                "companies": [
                    {
                        "symbol": symbol,
                        "company_name": "FMC Corporation",
                        "decision": "SELL",
                        "investment_score": 41.2,
                        "risks": ["Alavancagem elevada"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_company_route_renders_a_standalone_page_when_data_exists(base_url) -> None:
    base, reports = base_url
    _seed_company(reports.parent.parent)
    response = _open(f"{base}/company/FMC")
    body = response.read().decode("utf-8")
    assert response.status == 200
    assert "FMC Corporation" in body
    # Documento fechado: nada do relatório completo, nenhuma outra empresa.
    assert "Todos os dados coletados" in body
    assert body.rstrip().endswith("</html>")


def test_company_page_reports_the_atlas_reading(base_url) -> None:
    base, reports = base_url
    _seed_company(reports.parent.parent)
    body = _open(f"{base}/company/FMC").read().decode("utf-8")
    assert "Alavancagem elevada" in body
    assert "SELL" in body


def test_company_route_normalizes_case(base_url) -> None:
    base, _ = base_url
    with pytest.raises(urllib.error.HTTPError) as exc:
        _open(f"{base}/company/fmc")
    assert exc.value.headers.get("Location") == "/report#ticker-FMC"


def test_company_route_rejects_a_junk_symbol(base_url) -> None:
    base, _ = base_url
    with pytest.raises(urllib.error.HTTPError) as exc:
        _open(f"{base}/company/@@@")
    assert exc.value.code == 404


def test_home_is_html_for_a_browser_but_json_for_a_script(base_url) -> None:
    base, _ = base_url
    request = urllib.request.Request(f"{base}/", headers={"Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers.get("Content-Type").startswith("text/html")
    # Sem Accept de navegador o contrato programático permanece JSON.
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["service"] == "atlas-dashboard-api"
    except urllib.error.HTTPError as exc:
        # 503 quando não há dashboard.json no tmp -- ainda assim JSON, não HTML.
        assert exc.headers.get("Content-Type").startswith("application/json")


def test_analysis_values_persist_derived_metrics(tmp_path: Path) -> None:
    """Métricas derivadas em memória passam a ter valor persistido (ADR-045)."""
    import pandas as pd

    from storage.history_db import HistoryDatabase

    database = HistoryDatabase(str(tmp_path / "hist.db"))
    frame = pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "Investment Score": 50.0,
                "rsi_14": 61.2,
                "momentum_3m": 4.5,
                "ev_ebitda": 12.3,
                "field_evidence": {"rsi_14": {"status": "present"}},
            }
        ]
    )
    database.save_snapshot(frame, "2026-07-24T12:00:00", model_version="0.3")

    con = sqlite3.connect(tmp_path / "hist.db")
    stored = con.execute(
        "SELECT analysis_values_json FROM snapshots WHERE symbol = 'TEST'"
    ).fetchone()[0]
    con.close()
    values = json.loads(stored)
    assert values["rsi_14"] == 61.2
    assert values["momentum_3m"] == 4.5
    # o dicionário de evidência tem coluna própria e não é duplicado aqui
    assert "field_evidence" not in values


def test_adding_the_column_preserves_existing_rows(tmp_path: Path) -> None:
    """A migração é aditiva: banco antigo abre sem perder histórico."""
    import pandas as pd

    from storage.history_db import HistoryDatabase

    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE snapshots (snapshot_date TEXT, symbol TEXT, "
        "PRIMARY KEY (snapshot_date, symbol))"
    )
    con.execute("INSERT INTO snapshots VALUES ('2026-01-01T00:00:00','OLD')")
    con.commit()
    con.close()

    HistoryDatabase(str(path))

    con = sqlite3.connect(path)
    columns = {row[1] for row in con.execute("PRAGMA table_info(snapshots)")}
    rows = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    con.close()
    assert "analysis_values_json" in columns
    assert rows == 1

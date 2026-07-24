"""
Trava o disparo de execução a partir do visor (POST /run).

O que está em jogo, na mesma ordem do módulo `api.runner`:

1. Uma run por vez -- duas execuções simultâneas escreveriam ao mesmo tempo
   no `atlas_history.db` e no `dashboard.json`. O segundo clique recebe 409,
   nunca uma segunda thread.
2. O modo vem de allowlist -- nada do HTTP chega a `run_all` como argumento.
3. Local por construção -- `serve(allow_run=False)` faz a rota deixar de
   existir (404), que é como o visor hospedado da Fase 2 deve subir.

O runner é testado direto (sem porta) e as rotas via servidor real em
loopback, como nos demais testes de API.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Iterator

import pytest

import api.server as server_module
from api.runner import PipelineRunner, RUN_MODES
from api.server import DashboardRequestHandler


# ---------------------------------------------------------------- runner --


def test_only_allowlisted_modes_start_anything() -> None:
    calls: list[list[str]] = []
    runner = PipelineRunner(execute=lambda argv: calls.append(list(argv)))
    status, payload = runner.start("rm -rf /")
    assert status == 400
    assert payload["accepted"] == sorted(RUN_MODES)
    runner.join()
    assert calls == []


def test_the_client_chooses_a_key_never_the_argv() -> None:
    calls: list[list[str]] = []
    runner = PipelineRunner(execute=lambda argv: calls.append(list(argv)))
    status, _ = runner.start("portfolio")
    assert status == 202
    runner.join()
    assert calls == [["--portfolio"]]


def test_second_start_while_running_is_rejected_not_queued() -> None:
    release = threading.Event()
    started = threading.Event()

    def slow(argv) -> None:
        started.set()
        release.wait(timeout=5)

    runner = PipelineRunner(execute=slow)
    assert runner.start("portfolio")[0] == 202
    assert started.wait(timeout=5)
    status, payload = runner.start("full")
    assert status == 409
    assert payload["running"]["mode"] == "portfolio"
    release.set()
    runner.join()
    assert runner.status()["state"] == "done"


def test_failure_is_reported_with_cause_and_frees_the_lock() -> None:
    def boom(argv) -> None:
        raise RuntimeError("provedor fora do ar")

    runner = PipelineRunner(execute=boom)
    runner.start("portfolio")
    runner.join()
    state = runner.status()
    assert state["state"] == "failed"
    assert "provedor fora do ar" in state["error"]
    # A trava não pode ficar presa depois de uma falha.
    assert runner.start("portfolio")[0] == 202
    runner.join()


def test_health_check_abort_reads_as_failure_not_shutdown() -> None:
    def abort(argv) -> None:
        raise SystemExit(1)

    runner = PipelineRunner(execute=abort)
    runner.start("full")
    runner.join()
    state = runner.status()
    assert state["state"] == "failed"
    assert "Health Check" in state["error"]


# ---------------------------------------------------------------- routes --


@pytest.fixture()
def api(monkeypatch) -> Iterator[tuple[str, PipelineRunner]]:
    release = threading.Event()
    runner = PipelineRunner(execute=lambda argv: release.wait(timeout=5))
    monkeypatch.setattr(server_module, "RUNNER", runner)
    monkeypatch.setattr(DashboardRequestHandler, "run_enabled", True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", runner
    finally:
        release.set()
        runner.join()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _post_run(base: str, mode: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{base}/run",
        data=json.dumps({"mode": mode}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_post_run_starts_and_status_reports_it(api) -> None:
    base, runner = api
    status, payload = _post_run(base, "portfolio")
    assert status == 202
    assert payload["state"] == "running"
    with urllib.request.urlopen(f"{base}/run/status", timeout=5) as response:
        seen = json.loads(response.read().decode("utf-8"))
    assert seen["state"] == "running"
    assert seen["mode"] == "portfolio"


def test_concurrent_click_gets_409_through_http_too(api) -> None:
    base, _ = api
    assert _post_run(base, "portfolio")[0] == 202
    status, payload = _post_run(base, "full")
    assert status == 409
    assert "andamento" in payload["error"]


def test_run_route_vanishes_when_disabled(api, monkeypatch) -> None:
    base, _ = api
    monkeypatch.setattr(DashboardRequestHandler, "run_enabled", False)
    assert _post_run(base, "portfolio")[0] == 404
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base}/run/status", timeout=5)
    assert exc.value.code == 404


def test_run_requires_json_content_type(api) -> None:
    base, _ = api
    request = urllib.request.Request(
        f"{base}/run", data=b"mode=portfolio", method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 415


# ------------------------------------------------------------------ home --


def test_home_shows_buttons_only_when_running_is_allowed(tmp_path) -> None:
    from api.home import render_home

    with_buttons = render_home(tmp_path, allow_run=True)
    assert 'data-mode="portfolio"' in with_buttons
    assert 'data-mode="full"' in with_buttons
    without = render_home(tmp_path, allow_run=False)
    assert "data-mode=" not in without
    assert "python atlas.py hoje" in without


# ------------------------------------------------------- defesa em camada --
#
# A rota já é inalcançável de fora por desenho (o servidor liga só em
# 127.0.0.1). A checagem de origem existe para o caso em que esse desenho
# falha -- um bind acidental em 0.0.0.0 não pode virar execução remota de
# processo. É a única proteção do conjunto cuja falha é irreversível, e por
# isso merece teste próprio em vez de confiar no bind.


class _RemoteClient(DashboardRequestHandler):
    """Handler idêntico, fingindo um cliente fora da máquina."""

    client_address = ("203.0.113.7", 54321)

    def __init__(self) -> None:  # noqa: D107 -- não queremos o setup de socket
        pass


def test_run_is_refused_for_a_client_outside_the_machine() -> None:
    handler = _RemoteClient()
    handler.run_enabled = True

    denial = handler._run_allowed()

    assert denial is not None
    status, payload = denial
    assert status == 403
    assert "local" in payload["error"]


def test_loopback_forms_are_all_accepted() -> None:
    """IPv4, IPv6 e IPv4-mapeado-em-IPv6 são a mesma máquina; recusar
    qualquer um deles quebraria o uso legítimo conforme o stack resolve."""
    for address in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        handler = _RemoteClient()
        handler.client_address = (address, 54321)
        handler.run_enabled = True

        assert handler._run_allowed() is None, address


def test_disabled_route_hides_itself_even_from_localhost() -> None:
    """404, não 403: com `allow_run=False` a rota não existe, e dizer
    'proibido' revelaria um recurso que o modo hospedado não tem."""
    handler = _RemoteClient()
    handler.client_address = ("127.0.0.1", 54321)
    handler.run_enabled = False

    denial = handler._run_allowed()

    assert denial is not None
    assert denial[0] == 404

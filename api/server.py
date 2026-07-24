from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api.home import render_home
from api.resources import ROOT, dispatch
from api.runner import RUNNER
from reports.company_page import render_company_page


REPORTS_DIR = ROOT / "output" / "relatorios"
COCKPIT_PATH = REPORTS_DIR / "decision_cockpit.html"
REPORT_PATH = REPORTS_DIR / "atlas_report_latest.html"
# Limite defensivo do corpo de POST: uma revisão de journal são poucos campos.
MAX_BODY_BYTES = 64 * 1024


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Adaptador fino de HTTP sobre `api.resources.dispatch`.

    GET serve o contrato read-only e o cockpit HTML. Há dois caminhos de
    escrita, ambos exigindo `Content-Type: application/json` -- um formulário
    cross-site não consegue definir esse cabeçalho sem preflight CORS (que não
    respondemos), o que mitiga CSRF simples:

    - `POST /journal`: revisão humana consultiva, append-only;
    - `POST /run`: dispara o pipeline (`api.runner`), uma execução por vez,
      só de loopback e só com `run_enabled`.

    O servidor liga apenas em 127.0.0.1.
    """

    server_version = "AtlasDashboardAPI/2.0"

    # Execução a partir do visor: ligada no uso local, desligada no modo
    # hospedado (Fase 2), onde não há motor do outro lado. É atributo de
    # classe para `serve(allow_run=False)` decidir uma vez, não por request.
    run_enabled = True

    # Loopback: quem pode disparar uma run. Um cliente fora daqui não fala com
    # este servidor por desenho (ele liga só em 127.0.0.1), mas a checagem é
    # explícita para que um bind acidental em 0.0.0.0 não vire execução remota.
    LOOPBACK = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})

    def _is_local(self) -> bool:
        return str(self.client_address[0]) in self.LOOPBACK

    def _run_allowed(self) -> tuple[int, dict[str, str]] | None:
        """None se a rota pode ser servida; senão, o par (status, erro)."""
        if not self.run_enabled:
            return 404, {"error": "recurso não encontrado", "path": "/run"}
        if not self._is_local():
            return 403, {"error": "execução só é permitida a partir da máquina local."}
        return None

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # Estas páginas são reescritas a cada execução do Atlas. Sem isto o
        # navegador reexibe a versão anterior e o usuário conclui que a run
        # não surtiu efeito.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html_file(self, path: Path, missing: str) -> None:
        if not path.exists():
            self._send_json(503, {"error": missing})
            return
        self._send_html(path.read_bytes())

    def _serve_company(self, symbol: str) -> None:
        """Página isolada da empresa, com toda a evidência já coletada.

        `reports.company_page` monta o documento a partir do que os motores
        persistiram (dashboard, histórico, snapshot bruto). Se o símbolo ainda
        não foi coletado, cai para a âncora do relatório completo e, por fim,
        explica o que rodar. Nada é recalculado aqui.
        """
        clean_symbol = "".join(
            ch for ch in symbol.upper() if ch.isalnum() or ch in "-."
        )
        if not clean_symbol:
            self._send_json(404, {"error": "símbolo inválido."})
            return
        page = render_company_page(clean_symbol, ROOT)
        if page is not None:
            self._send_html(page.encode("utf-8"))
            return
        if REPORT_PATH.exists():
            self.send_response(302)
            self.send_header("Location", f"/report#ticker-{clean_symbol}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(
            503,
            {
                "error": (
                    f"nenhum dado coletado de {clean_symbol} ainda; "
                    "rode 'python atlas.py hoje' ou 'python atlas.py ticker "
                    f"{clean_symbol}'."
                )
            },
        )

    def _wants_html(self) -> bool:
        # Só o navegador manda `Accept: text/html`; urllib/scripts não, então o
        # contrato JSON da API em `/` permanece intacto para eles.
        return "text/html" in (self.headers.get("Accept") or "")

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        clean = self.path.split("?", 1)[0].rstrip("/") or "/"
        if clean in ("/cockpit", "/cockpit.html"):
            self._serve_html_file(
                COCKPIT_PATH, "decision_cockpit.html ainda não foi gerado."
            )
            return
        if clean in ("/report", "/report.html", "/relatorio"):
            self._serve_html_file(
                REPORT_PATH, "atlas_report_latest.html ainda não foi gerado."
            )
            return
        if clean.startswith("/company/"):
            self._serve_company(clean.rsplit("/", 1)[-1])
            return
        if clean in ("/run/status", "/run"):
            denial = self._run_allowed()
            self._send_json(*(denial or (200, RUNNER.status())))
            return
        if clean in ("/", "/home") and self._wants_html():
            self._send_html(
                render_home(
                    ROOT, allow_run=self.run_enabled and self._is_local()
                ).encode("utf-8")
            )
            return
        status, payload = dispatch("GET", self.path)
        self._send_json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self._send_json(
                415, {"error": "Content-Type deve ser application/json."}
            )
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "Content-Length inválido."})
            return
        if length <= 0:
            self._send_json(400, {"error": "corpo vazio."})
            return
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "corpo excede o limite."})
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "corpo não é JSON válido."})
            return
        clean = self.path.split("?", 1)[0].rstrip("/") or "/"
        if clean == "/run":
            denial = self._run_allowed()
            if denial is not None:
                self._send_json(*denial)
                return
            if not isinstance(body, dict):
                self._send_json(400, {"error": "corpo deve ser um objeto JSON."})
                return
            self._send_json(*RUNNER.start(body.get("mode")))
            return
        status, payload = dispatch("POST", self.path, body=body)
        self._send_json(status, payload)

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "método não suportado", "method": "PUT"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "método não suportado", "method": "DELETE"})

    def log_message(self, *args: object) -> None:
        # Silencia o log padrão no stderr; o Atlas tem seu próprio logger.
        return


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    open_browser: bool = False,
    open_path: str = "/",
    allow_run: bool = True,
) -> None:
    """Sobe o servidor local (bloqueante). Ctrl+C para encerrar.

    GET é read-only sobre os artefatos; as escritas são POST /journal (revisão
    humana consultiva) e POST /run (dispara o pipeline, uma execução por vez).
    Liga só em loopback por padrão -- não exponha em rede.

    `allow_run=False` remove as rotas de execução: é assim que o visor
    hospedado da Fase 2 deve subir, já que lá não há motor para disparar.
    Com `open_browser=True`, abre o navegador em `open_path` logo após ligar.
    """
    DashboardRequestHandler.run_enabled = allow_run
    httpd = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    url = f"http://{host}:{port}{open_path}"
    print(
        f"Atlas em {url} -- início em /, cockpit em /cockpit, "
        "relatório em /report. Ctrl+C para encerrar."
    )
    if open_browser:
        # Pequeno atraso para o serve_forever já estar aceitando conexões.
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

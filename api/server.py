from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from api.resources import ROOT, dispatch


COCKPIT_PATH = ROOT / "output" / "relatorios" / "decision_cockpit.html"
# Limite defensivo do corpo de POST: uma revisão de journal são poucos campos.
MAX_BODY_BYTES = 64 * 1024


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Adaptador fino de HTTP sobre `api.resources.dispatch`.

    GET serve o contrato read-only e o cockpit HTML. POST /journal é o único
    caminho de escrita (revisão humana consultiva, append-only) e exige
    `Content-Type: application/json` -- um formulário cross-site não consegue
    definir esse cabeçalho sem preflight CORS (que não respondemos), o que
    mitiga CSRF simples. O servidor liga apenas em 127.0.0.1.
    """

    server_version = "AtlasDashboardAPI/2.0"

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_cockpit(self) -> None:
        if not COCKPIT_PATH.exists():
            self._send_json(
                503, {"error": "decision_cockpit.html ainda não foi gerado."}
            )
            return
        body = COCKPIT_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        clean = self.path.split("?", 1)[0].rstrip("/") or "/"
        if clean in ("/cockpit", "/cockpit.html"):
            self._serve_cockpit()
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
        status, payload = dispatch("POST", self.path, body=body)
        self._send_json(status, payload)

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "método não suportado", "method": "PUT"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "método não suportado", "method": "DELETE"})

    def log_message(self, *args: object) -> None:
        # Silencia o log padrão no stderr; o Atlas tem seu próprio logger.
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Sobe o servidor local (bloqueante). Ctrl+C para encerrar.

    GET é read-only; a única escrita é POST /journal (revisão humana
    consultiva). Liga só em loopback por padrão -- não exponha em rede.
    """
    httpd = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    print(
        f"Atlas API em http://{host}:{port} -- cockpit em /cockpit, "
        "revisão via POST /journal (local). Ctrl+C para encerrar."
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

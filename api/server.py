from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from api.resources import dispatch


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """
    Adaptador fino de HTTP sobre `api.resources.dispatch`.

    Somente GET; qualquer outro método recebe 405. Não escreve nada, não
    dispara execução -- apenas serve o contrato já gerado.
    """

    server_version = "AtlasDashboardAPI/1.0"

    def _handle(self, method: str) -> None:
        status, payload = dispatch(method, self.path)
        body = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def log_message(self, *args: object) -> None:
        # Silencia o log padrão no stderr; o Atlas tem seu próprio logger.
        return


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Sobe o servidor read-only (bloqueante). Ctrl+C para encerrar."""
    httpd = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    print(
        f"Atlas dashboard API (read-only) em http://{host}:{port} "
        "-- Ctrl+C para encerrar."
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()

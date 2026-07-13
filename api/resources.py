from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD_PATH = ROOT / "output" / "dashboard.json"


class ResourceError(Exception):
    """Erro de recurso da API, com status HTTP associado."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def load_dashboard(dashboard_path: Path | None = None) -> dict[str, Any]:
    """
    Carrega o contrato do dashboard já emitido (output/dashboard.json).

    Levanta ResourceError(503) se o arquivo ainda não existe (nenhuma execução
    do Atlas produziu o artefato). A API é read-only: nunca dispara uma run.
    """
    source = (
        Path(dashboard_path)
        if dashboard_path is not None
        else DEFAULT_DASHBOARD_PATH
    )
    if not source.exists():
        raise ResourceError(
            503,
            "dashboard.json ainda não foi gerado; execute run_all.py.",
        )
    return json.loads(source.read_text(encoding="utf-8"))


def _companies(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("companies") or [])


def route(path: str, data: dict[str, Any]) -> tuple[int, Any]:
    """
    Roteia um GET já validado sobre um contrato de dashboard carregado.

    Função pura (sem I/O), para ser testável sem servidor nem arquivo.
    """
    clean = path.split("?", 1)[0].rstrip("/") or "/"
    parts = [segment for segment in clean.split("/") if segment]

    if clean == "/":
        return 200, {
            "service": "atlas-dashboard-api",
            "contract_version": data.get("contract_version"),
            "generated_at": data.get("generated_at"),
            "resources": [
                "/dashboard",
                "/companies",
                "/companies/{symbol}",
                "/market",
                "/portfolio",
                "/outcomes",
            ],
        }

    if parts == ["dashboard"]:
        return 200, data

    if parts == ["companies"]:
        companies = _companies(data)
        return 200, {"count": len(companies), "companies": companies}

    if len(parts) == 2 and parts[0] == "companies":
        symbol = parts[1].upper()
        for company in _companies(data):
            if str(company.get("symbol", "")).upper() == symbol:
                return 200, company
        return 404, {"error": "empresa não encontrada", "symbol": symbol}

    if parts == ["market"]:
        return 200, {"market": data.get("market")}

    if parts == ["portfolio"]:
        return 200, {"portfolio": data.get("portfolio")}

    if parts == ["outcomes"]:
        return 200, {"outcomes": data.get("outcomes")}

    return 404, {"error": "recurso não encontrado", "path": clean}


def dispatch(
    method: str,
    path: str,
    *,
    dashboard_path: Path | None = None,
) -> tuple[int, Any]:
    """
    Ponto único de entrada: valida o método, carrega o contrato e roteia.

    Somente GET é aceito (API read-only). Retorna (status, payload).
    """
    if method.upper() != "GET":
        return 405, {"error": "método não suportado", "method": method}

    try:
        data = load_dashboard(dashboard_path)
    except ResourceError as exc:
        return exc.status, {"error": exc.message}

    return route(path, data)

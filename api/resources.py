from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision.journal import DECISION_STATUSES, record_decision


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD_PATH = ROOT / "output" / "dados" / "dashboard.json"
DEFAULT_QUEUE_PATH = ROOT / "output" / "dados" / "decision_queue.json"
DEFAULT_JOURNAL_PATH = ROOT / "output" / "dados" / "decision_journal.json"


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
                "/priority",
                "/priority/sell",
                "/priority/buy",
                "/decision-queue",
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

    if parts == ["priority"]:
        return 200, {"priority": data.get("priority")}

    if parts == ["priority", "sell"]:
        priority = data.get("priority") or {}
        return 200, {"sell": priority.get("sell")}

    if parts == ["priority", "buy"]:
        priority = data.get("priority") or {}
        return 200, {"buy": priority.get("buy")}

    if parts == ["decision-queue"]:
        return 200, {"decision_queue": data.get("decision_queue")}

    return 404, {"error": "recurso não encontrado", "path": clean}


def write_journal_event(
    body: Any,
    *,
    queue_path: Path | None = None,
    journal_path: Path | None = None,
) -> tuple[int, Any]:
    """Registra um evento humano no Decision Journal a partir de um corpo JSON.

    Escrita local, append-only e consultiva: não envia ordem nem muta a
    carteira. Localiza a decisão na Decision Queue corrente pelo `decision_id`
    e delega a `decision.journal.record_decision` (que valida status/motivo e
    rejeita duplicatas). Função pura quanto a HTTP — o servidor só adapta.
    """
    if not isinstance(body, dict):
        return 400, {"error": "corpo deve ser um objeto JSON."}
    decision_id = str(body.get("decision_id", "")).strip()
    status = str(body.get("status", "")).strip().upper()
    reason = str(body.get("reason", "")).strip()
    if not decision_id:
        return 400, {"error": "decision_id obrigatório."}
    if status not in DECISION_STATUSES:
        return 400, {"error": f"status deve ser um de {list(DECISION_STATUSES)}."}
    if not reason:
        return 400, {"error": "reason não pode ser vazio."}

    queue_source = Path(queue_path) if queue_path is not None else DEFAULT_QUEUE_PATH
    if not queue_source.exists():
        return 503, {"error": "decision_queue.json ainda não foi gerado."}
    queue = json.loads(queue_source.read_text(encoding="utf-8"))
    decision = next(
        (
            item
            for item in queue.get("items", [])
            if str(item.get("decision_id")) == decision_id
        ),
        None,
    )
    if decision is None:
        return 404, {"error": "decision_id não encontrado na Decision Queue."}

    try:
        event = record_decision(
            decision,
            queue_generated_at=str(queue.get("generated_at", "")),
            status=status,
            reason=reason,
            journal_path=(
                Path(journal_path) if journal_path is not None else DEFAULT_JOURNAL_PATH
            ),
        )
    except ValueError as exc:
        return 409, {"error": str(exc)}
    return 201, event.to_dict()


def dispatch(
    method: str,
    path: str,
    *,
    dashboard_path: Path | None = None,
    body: Any = None,
    queue_path: Path | None = None,
    journal_path: Path | None = None,
) -> tuple[int, Any]:
    """
    Ponto único de entrada: valida o método, carrega o contrato e roteia.

    GET é read-only sobre o contrato do dashboard. POST /journal é o único
    caminho de escrita: registra uma revisão humana consultiva (append-only,
    sem envio de ordem). Qualquer outro método/rota é rejeitado.
    """
    clean = path.split("?", 1)[0].rstrip("/") or "/"
    if method.upper() == "POST":
        if clean != "/journal":
            return 404, {"error": "recurso não encontrado", "path": clean}
        return write_journal_event(
            body, queue_path=queue_path, journal_path=journal_path
        )
    if method.upper() != "GET":
        return 405, {"error": "método não suportado", "method": method}

    try:
        data = load_dashboard(dashboard_path)
    except ResourceError as exc:
        return exc.status, {"error": exc.message}

    return route(path, data)

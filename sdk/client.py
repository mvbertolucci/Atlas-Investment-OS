from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from api.resources import dispatch


# Um transport é uma função GET-only: recebe um path e devolve (status, payload).
Transport = Callable[[str], "tuple[int, Any]"]


class AtlasApiError(Exception):
    """Erro retornado pela API do Atlas, com status HTTP associado."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.message = message


class NotFoundError(AtlasApiError):
    """Recurso inexistente (404)."""


class ServiceUnavailableError(AtlasApiError):
    """Contrato ainda não gerado ou API indisponível (503)."""


def http_transport(
    base_url: str = "http://127.0.0.1:8000",
    *,
    timeout: float = 5.0,
) -> Transport:
    """Transport HTTP (urllib) contra a API read-only em execução."""
    base = base_url.rstrip("/")

    def _call(path: str) -> tuple[int, Any]:
        url = base + path
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8")
                )
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001 - corpo de erro não-JSON
                body = {"error": str(exc)}
            return exc.code, body
        except urllib.error.URLError as exc:
            raise AtlasApiError(
                0, f"falha de conexão com {base}: {exc.reason}"
            ) from exc

    return _call


def local_transport(dashboard_path: Path | None = None) -> Transport:
    """
    Transport in-process: resolve os recursos direto via `api.resources`,
    sem servidor. Lê o `output/dashboard.json` (ou o caminho informado).
    """

    def _call(path: str) -> tuple[int, Any]:
        return dispatch("GET", path, dashboard_path=dashboard_path)

    return _call


class AtlasClient:
    """
    Cliente Python read-only para o contrato do dashboard do Atlas.

    Só lê: espelha os recursos GET da API. Use `for_url` para falar com a API
    em execução ou `for_file` para ler o artefato direto (offline).
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @classmethod
    def for_url(
        cls,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout: float = 5.0,
    ) -> "AtlasClient":
        return cls(http_transport(base_url, timeout=timeout))

    @classmethod
    def for_file(
        cls,
        dashboard_path: Path | None = None,
    ) -> "AtlasClient":
        return cls(local_transport(dashboard_path))

    def _get(self, path: str) -> Any:
        status, payload = self._transport(path)
        if status == 200:
            return payload

        message = (
            payload.get("error", "erro")
            if isinstance(payload, dict)
            else str(payload)
        )
        if status == 404:
            raise NotFoundError(status, message)
        if status == 503:
            raise ServiceUnavailableError(status, message)
        raise AtlasApiError(status, message)

    def index(self) -> dict[str, Any]:
        return self._get("/")

    def dashboard(self) -> dict[str, Any]:
        return self._get("/dashboard")

    def companies(self) -> list[dict[str, Any]]:
        return self._get("/companies")["companies"]

    def company(self, symbol: str) -> dict[str, Any]:
        return self._get(f"/companies/{symbol}")

    def market(self) -> Any:
        return self._get("/market")["market"]

    def portfolio(self) -> Any:
        return self._get("/portfolio")["portfolio"]

    def outcomes(self) -> Any:
        return self._get("/outcomes")["outcomes"]

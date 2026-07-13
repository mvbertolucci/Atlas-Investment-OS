"""
Integration test for the stdlib HTTP adapter (api/server.py).

Drives the real server over a loopback socket on an ephemeral port. This is
deterministic and uses no external network -- it locks the HTTP behavior
(status codes, JSON body, read-only method handling) that the resource-layer
unit tests cannot observe.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

import api.resources as resources
from api.server import DashboardRequestHandler


@pytest.fixture()
def base_url(tmp_path: Path, monkeypatch) -> Iterator[str]:
    artifact = tmp_path / "dashboard.json"
    artifact.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "generated_at": "2026-07-13T00:00:00",
                "market": None,
                "companies": [
                    {"symbol": "ADBE", "decision": "BUY"}
                ],
                "portfolio": None,
                "outcomes": None,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(resources, "DEFAULT_DASHBOARD_PATH", artifact)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardRequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_get_company_over_http(base_url: str) -> None:
    status, payload = _get(f"{base_url}/companies/adbe")
    assert status == 200
    assert payload["symbol"] == "ADBE"
    assert payload["decision"] == "BUY"


def test_index_over_http(base_url: str) -> None:
    status, payload = _get(f"{base_url}/")
    assert status == 200
    assert payload["service"] == "atlas-dashboard-api"


def test_unknown_path_is_404_over_http(base_url: str) -> None:
    status, _ = _get(f"{base_url}/nope")
    assert status == 404


def test_post_is_rejected_over_http(base_url: str) -> None:
    request = urllib.request.Request(
        f"{base_url}/dashboard", method="POST", data=b"{}"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 405

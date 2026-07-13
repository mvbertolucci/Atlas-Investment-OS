"""
Tests for the read-only Atlas SDK client.

Most tests use the in-process `for_file` transport (no socket). One integration
test drives the real HTTP transport (`for_url`) against a loopback server so the
urllib path is covered too.
"""
from __future__ import annotations

import json
import threading
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

import api.resources as resources
from api.server import DashboardRequestHandler
from sdk import (
    AtlasApiError,
    AtlasClient,
    NotFoundError,
    ServiceUnavailableError,
)


def _contract() -> dict:
    return {
        "contract_version": "1.0",
        "generated_at": "2026-07-13T00:00:00",
        "market": None,
        "companies": [
            {"symbol": "AAA", "decision": "BUY"},
            {"symbol": "BBB", "decision": "AVOID"},
        ],
        "portfolio": {"portfolio_name": "Main"},
        "outcomes": {"hit_rate": {"hit_rate": 100.0}},
        "priority": {
            "sell": {"items": [{"symbol": "BBB", "action": "SELL"}]},
            "buy": {"items": [{"symbol": "CCC", "candidate_rank": 1}]},
        },
    }


@pytest.fixture()
def artifact(tmp_path: Path) -> Path:
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    return path


def test_dashboard_and_collections(artifact: Path) -> None:
    client = AtlasClient.for_file(artifact)

    assert client.dashboard()["contract_version"] == "1.0"
    assert [c["symbol"] for c in client.companies()] == ["AAA", "BBB"]
    assert client.index()["service"] == "atlas-dashboard-api"


def test_single_company_case_insensitive(artifact: Path) -> None:
    client = AtlasClient.for_file(artifact)
    assert client.company("aaa")["decision"] == "BUY"


def test_unknown_company_raises_not_found(artifact: Path) -> None:
    client = AtlasClient.for_file(artifact)
    with pytest.raises(NotFoundError) as exc:
        client.company("ZZZ")
    assert exc.value.status == 404


def test_sub_resources_are_unwrapped(artifact: Path) -> None:
    client = AtlasClient.for_file(artifact)
    assert client.market() is None
    assert client.portfolio() == {"portfolio_name": "Main"}
    assert client.outcomes() == {"hit_rate": {"hit_rate": 100.0}}


def test_priority_methods(artifact: Path) -> None:
    client = AtlasClient.for_file(artifact)
    assert client.priority()["sell"]["items"][0]["symbol"] == "BBB"
    assert client.priority_sell()["items"][0]["action"] == "SELL"
    assert client.priority_buy()["items"][0]["symbol"] == "CCC"


def test_missing_artifact_raises_service_unavailable(tmp_path: Path) -> None:
    client = AtlasClient.for_file(tmp_path / "absent.json")
    with pytest.raises(ServiceUnavailableError) as exc:
        client.dashboard()
    assert exc.value.status == 503


def test_generic_error_status_raises_api_error() -> None:
    client = AtlasClient(lambda path: (500, {"error": "boom"}))
    with pytest.raises(AtlasApiError) as exc:
        client.dashboard()
    assert exc.value.status == 500
    assert "boom" in exc.value.message


@pytest.fixture()
def base_url(artifact: Path, monkeypatch) -> Iterator[str]:
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


def test_http_transport_against_live_server(base_url: str) -> None:
    client = AtlasClient.for_url(base_url)
    assert client.company("bbb")["decision"] == "AVOID"
    with pytest.raises(NotFoundError):
        client.company("ZZZ")


def test_http_transport_connection_failure_raises() -> None:
    # Nothing listening on this port -> connection refused -> AtlasApiError(0).
    client = AtlasClient.for_url("http://127.0.0.1:9", timeout=1.0)
    with pytest.raises(AtlasApiError) as exc:
        client.dashboard()
    assert exc.value.status == 0

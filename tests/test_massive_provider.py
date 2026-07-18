from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import providers.massive as massive_module
from providers.massive import (
    MassiveMarketDataProvider,
    build_massive_secondary_provider,
    load_massive_api_key,
)


def _transport(path, params, api_key, timeout):
    assert params["ticker"] == "AAPL"
    assert api_key == "secret-key"
    assert timeout == 7
    if path.endswith("/ratios"):
        return {
            "results": [
                {
                    "ticker": "AAPL",
                    "date": "2026-07-16",
                    "market_cap": 3_000_000_000_000,
                    "enterprise_value": 3_100_000_000_000,
                }
            ]
        }
    if path.endswith("/short-interest"):
        return {
            "results": [
                {
                    "ticker": "AAPL",
                    "settlement_date": "2026-06-30",
                    "short_interest": 150_000_000,
                }
            ]
        }
    return {
        "results": [
            {
                "ticker": "AAPL",
                "effective_date": "2026-06-15",
                "free_float": 15_000_000_000,
            }
        ]
    }


def test_massive_maps_comparable_market_and_short_float_fields() -> None:
    provider = MassiveMarketDataProvider(
        "secret-key", timeout_seconds=7, transport=_transport
    )

    record = provider("aapl")

    assert record["market_cap"] == 3_000_000_000_000
    assert record["enterprise_value"] == 3_100_000_000_000
    assert record["short_float"] == pytest.approx(0.01)
    assert record["field_evidence"]["market_cap"]["observed_at"] == (
        "2026-07-16"
    )
    assert record["field_evidence"]["short_float"]["observed_at"] == (
        "2026-06-30"
    )
    assert "api_key" not in json.dumps(record).casefold()


def test_massive_does_not_combine_misaligned_short_and_float_periods() -> None:
    def transport(path, params, api_key, timeout):
        payload = _transport(path, params, api_key, timeout)
        if path.endswith("/float"):
            payload["results"][0]["effective_date"] = "2025-12-31"
        return payload

    record = MassiveMarketDataProvider(
        "secret-key", timeout_seconds=7, transport=transport
    )("AAPL")

    assert record["short_float"] is None
    evidence = record["field_evidence"]["short_float"]
    assert evidence["status"] == "unavailable"
    assert "more than 45 days" in evidence["detail"]


def test_massive_key_is_loaded_only_when_enabled(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps({"massive_api_key": "file-key"}), encoding="utf-8"
    )
    settings = {
        "massive_secondary_enabled": True,
        "provider_secrets_path": str(secrets),
    }

    assert load_massive_api_key(tmp_path, settings) == "file-key"
    assert isinstance(
        build_massive_secondary_provider(tmp_path, settings),
        MassiveMarketDataProvider,
    )
    assert load_massive_api_key(
        tmp_path, {**settings, "massive_secondary_enabled": False}
    ) is None


def test_massive_environment_key_takes_precedence(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "environment-key")

    assert load_massive_api_key(
        tmp_path, {"massive_secondary_enabled": True}
    ) == "environment-key"


def test_massive_rejects_empty_key_and_isolates_invalid_payload() -> None:
    with pytest.raises(ValueError, match="api_key"):
        MassiveMarketDataProvider("")

    provider = MassiveMarketDataProvider(
        "secret-key", transport=lambda *args: []
    )
    record = provider("AAPL")

    assert record["market_cap"] is None
    assert record["enterprise_value"] is None
    assert record["short_float"] is None
    assert set(record["massive_endpoint_errors"]) == {
        "ratios",
        "short_interest",
        "float",
    }


def test_massive_keeps_short_float_when_ratios_are_forbidden() -> None:
    def transport(path, params, api_key, timeout):
        if path.endswith("/ratios"):
            raise RuntimeError("Massive HTTP 403")
        return _transport(path, params, api_key, 7)

    record = MassiveMarketDataProvider(
        "secret-key", timeout_seconds=7, transport=transport
    )("AAPL")

    assert record["market_cap"] is None
    assert record["enterprise_value"] is None
    assert record["short_float"] == pytest.approx(0.01)
    assert record["massive_endpoint_errors"]["ratios"]["message"] == (
        "Massive HTTP 403"
    )
    assert record["field_evidence"]["market_cap"]["status"] == (
        "unavailable"
    )


def test_massive_transport_parses_json_and_sanitizes_http_errors(
    monkeypatch,
) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"results": []}'

    monkeypatch.setattr(
        massive_module, "urlopen", lambda *args, **kwargs: Response()
    )
    assert massive_module._request_json("/test", {}, "secret", 1) == {
        "results": []
    }

    def unauthorized(*args, **kwargs):
        raise HTTPError("https://example.test", 401, "denied", {}, None)

    monkeypatch.setattr(massive_module, "urlopen", unauthorized)
    with pytest.raises(RuntimeError, match="HTTP 401") as captured:
        massive_module._request_json("/test", {}, "secret", 1)
    assert "secret" not in str(captured.value)

    monkeypatch.setattr(
        massive_module,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        massive_module._request_json("/test", {}, "secret", 1)


def test_massive_helpers_reject_malformed_and_unusable_values() -> None:
    with pytest.raises(ValueError, match="results list"):
        massive_module._latest_result({}, "date")
    assert massive_module._latest_result({"results": []}, "date") == {}
    assert massive_module._number("invalid") is None
    assert massive_module._number(-1) is None
    assert massive_module._dates_within_days(None, "2026-01-01", 45) is False
    assert massive_module._dates_within_days(
        "invalid", "2026-01-01", 45
    ) is False


def test_massive_missing_key_and_invalid_secret_file_return_none(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    settings = {"massive_secondary_enabled": True}
    assert load_massive_api_key(tmp_path, settings) is None
    assert build_massive_secondary_provider(tmp_path, settings) is None

    secrets = tmp_path / "invalid.json"
    secrets.write_text("not-json", encoding="utf-8")
    settings["provider_secrets_path"] = str(secrets)
    assert load_massive_api_key(tmp_path, settings) is None


def test_massive_marks_short_float_unavailable_without_source_dates() -> None:
    def transport(path, params, api_key, timeout):
        payload = _transport(path, params, api_key, 7)
        if path.endswith("/short-interest"):
            payload["results"][0].pop("settlement_date")
        return payload

    record = MassiveMarketDataProvider(
        "secret-key", timeout_seconds=7, transport=transport
    )("AAPL")

    assert record["short_float"] is None
    assert "period unavailable" in record["field_evidence"]["short_float"][
        "detail"
    ]


def test_massive_rejects_nonpositive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        MassiveMarketDataProvider("secret", timeout_seconds=0)

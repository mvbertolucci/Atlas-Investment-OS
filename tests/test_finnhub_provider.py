from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.contracts import ProviderError, ProviderPolicy
from providers.finnhub import (
    FinnhubMarketDataProvider,
    build_finnhub_secondary_provider,
    load_finnhub_api_key,
)
from providers.finnhub_cache import FinnhubMetricCache


def _transport(path, params, api_key, timeout):
    assert path == "/stock/metric"
    assert params == {"symbol": "AAPL", "metric": "all"}
    assert api_key == "free-key"
    assert timeout == 7
    return {
        "symbol": "AAPL",
        "metricType": "all",
        "metric": {
            "marketCapitalization": 4_860_046.5,
            "enterpriseValue": 4_899_185.5,
            "totalDebt/totalEquityAnnual": 1.3547,
        },
        "series": {},
    }


def test_finnhub_converts_millions_to_absolute_and_claims_only_ev_and_cap() -> (
    None
):
    provider = FinnhubMarketDataProvider(
        "free-key", timeout_seconds=7, transport=_transport
    )

    record = provider("aapl")

    assert record["symbol"] == "AAPL"
    assert record["market_cap"] == pytest.approx(4_860_046_500_000)
    assert record["enterprise_value"] == pytest.approx(4_899_185_500_000)
    assert record["field_evidence"]["market_cap"]["status"] == "present"
    assert FinnhubMarketDataProvider.supported_fields == frozenset(
        {"market_cap", "enterprise_value"}
    )


def test_finnhub_marks_fields_unavailable_on_missing_metric_object() -> None:
    def transport(path, params, api_key, timeout):
        return {"symbol": "AAPL", "metric": None}

    provider = FinnhubMarketDataProvider(
        "free-key", transport=transport, prefetch_policy=ProviderPolicy(max_retries=0)
    )

    record = provider("AAPL")

    assert record["market_cap"] is None
    assert record["enterprise_value"] is None
    assert record["field_evidence"]["market_cap"]["status"] == "unavailable"
    assert "metric" in record["finnhub_endpoint_errors"]


def test_finnhub_cache_hit_skips_network(tmp_path: Path) -> None:
    def transport(path, params, api_key, timeout):
        raise AssertionError("Finnhub must not be re-requested from cache")

    cache = FinnhubMetricCache(tmp_path / "finnhub.json")
    cache.put("AAPL", {"metric": {"marketCapitalization": 100.0}})
    provider = FinnhubMarketDataProvider(
        "free-key", transport=transport, cache=cache
    )

    record = provider("AAPL")

    assert record["market_cap"] == pytest.approx(100_000_000.0)


def test_finnhub_internal_pacing_honors_call_window() -> None:
    waits: list[float] = []
    clock = [0.0]
    provider = FinnhubMarketDataProvider(
        "free-key",
        timeout_seconds=7,
        transport=_transport,
        request_limit_per_minute=1,
        sleeper=waits.append,
        monotonic=lambda: clock[0],
    )

    provider("AAPL")
    provider("AAPL")

    assert waits == [60.0]


def test_finnhub_key_is_loaded_only_when_enabled(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps({"finnhub_api_key": "abc"}), encoding="utf-8"
    )
    settings = {
        "finnhub_secondary_enabled": True,
        "provider_secrets_path": str(secrets),
    }

    assert load_finnhub_api_key(tmp_path, settings) == "abc"
    assert load_finnhub_api_key(tmp_path, {}) is None


def test_finnhub_missing_key_and_invalid_secret_file_return_none(
    tmp_path: Path,
) -> None:
    settings = {
        "finnhub_secondary_enabled": True,
        "provider_secrets_path": str(tmp_path / "missing.json"),
    }
    assert build_finnhub_secondary_provider(tmp_path, settings) is None

    secrets = tmp_path / "secrets.json"
    secrets.write_text("not-json", encoding="utf-8")
    settings["provider_secrets_path"] = str(secrets)
    assert build_finnhub_secondary_provider(tmp_path, settings) is None


def test_finnhub_builder_wires_cache_and_rate_limit(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps({"finnhub_api_key": "abc"}), encoding="utf-8"
    )
    settings = {
        "finnhub_secondary_enabled": True,
        "provider_secrets_path": str(secrets),
        "finnhub_request_limit_per_minute": 30,
        "finnhub_cache_days": 5,
    }

    provider = build_finnhub_secondary_provider(tmp_path, settings)

    assert provider is not None
    assert provider.request_limit_per_minute == 30
    assert provider.cache_days == 5
    assert provider.cache is not None
    assert provider.cache.path == tmp_path / "data/provider_cache/finnhub.json"


def test_finnhub_rejects_empty_key_and_nonpositive_settings() -> None:
    with pytest.raises(ValueError, match="api_key"):
        FinnhubMarketDataProvider("")
    with pytest.raises(ValueError, match="request_limit_per_minute"):
        FinnhubMarketDataProvider("key", request_limit_per_minute=0)


def test_finnhub_transport_sanitizes_http_and_url_errors(monkeypatch) -> None:
    import providers.finnhub as finnhub_module
    from urllib.error import HTTPError, URLError

    def raise_http(*args, **kwargs):
        raise HTTPError("url", 429, "too many", None, None)

    monkeypatch.setattr(finnhub_module, "urlopen", raise_http)
    with pytest.raises(RuntimeError, match="429"):
        finnhub_module._request_json("/stock/metric", {}, "key", 5)

    def raise_url(*args, **kwargs):
        raise URLError("boom")

    monkeypatch.setattr(finnhub_module, "urlopen", raise_url)
    with pytest.raises(RuntimeError, match="unavailable"):
        finnhub_module._request_json("/stock/metric", {}, "key", 5)

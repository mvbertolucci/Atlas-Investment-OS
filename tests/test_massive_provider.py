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
from providers.contracts import ProviderPolicy
from providers.fmp_cache import FmpQuotaExceeded
from providers.massive_cache import (
    MassiveFloatSnapshotCache,
    MassiveTickerDetailsCache,
)


def _transport(path, params, api_key, timeout):
    assert api_key == "secret-key"
    assert timeout == 7
    if "/reference/tickers/" in path:
        assert path.endswith("/AAPL")
        return {
            "results": {
                "ticker": "AAPL",
                "market_cap": 3_000_000_000_000,
                "last_updated_utc": "2026-07-16T20:00:00Z",
                "share_class_shares_outstanding": 15_000_000_000,
            }
        }
    assert params["ticker"] == "AAPL"
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


def _sec_fundamentals(symbol):
    assert symbol == "AAPL"
    return {
        "total_debt": 150_000_000_000,
        "total_cash": 50_000_000_000,
        "field_evidence": {
            "total_debt": {"observed_at": "2026-06-30"},
            "total_cash": {"observed_at": "2026-06-30"},
        },
    }


def test_massive_maps_comparable_market_and_short_float_fields() -> None:
    provider = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=_transport,
        fundamentals_fetcher=_sec_fundamentals,
    )

    record = provider("aapl")

    assert record["market_cap"] == 3_000_000_000_000
    assert record["enterprise_value"] == 3_100_000_000_000
    assert record["short_float"] == pytest.approx(0.01)
    assert record["field_evidence"]["market_cap"]["observed_at"] == (
        "2026-07-16T20:00:00Z"
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
        "ticker_details",
        "short_interest",
        "float",
    }


def test_massive_keeps_short_float_when_ticker_details_are_forbidden() -> None:
    def transport(path, params, api_key, timeout):
        if "/reference/tickers/" in path:
            raise RuntimeError("Massive HTTP 403")
        return _transport(path, params, api_key, 7)

    record = MassiveMarketDataProvider(
        "secret-key", timeout_seconds=7, transport=transport
    )("AAPL")

    assert record["market_cap"] is None
    assert record["enterprise_value"] is None
    assert record["short_float"] == pytest.approx(0.01)
    assert record["massive_endpoint_errors"]["ticker_details"]["message"] == (
        "Massive HTTP 403"
    )
    assert record["field_evidence"]["market_cap"]["status"] == (
        "unavailable"
    )


def test_massive_uses_fmp_float_when_native_period_is_misaligned() -> None:
    requested_paths = []

    def transport(path, params, api_key, timeout):
        requested_paths.append(path)
        payload = _transport(path, params, api_key, 7)
        if path.endswith("/float"):
            payload["results"][0]["effective_date"] = "2025-12-31"
        return payload

    provider = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=transport,
        float_fetcher=lambda symbol: {
            "free_float": 14_662_387_495,
            "observed_at": "2026-07-15 22:36:05",
            "_raw_fmp_float": [{"symbol": symbol}],
        },
    )

    record = provider("AAPL")

    assert requested_paths == [
        "/v3/reference/tickers/AAPL",
        "/stocks/v1/short-interest",
        "/stocks/vX/float",
    ]
    assert record["short_float"] == pytest.approx(
        150_000_000 / 14_662_387_495
    )
    assert record["source"] == "Massive + Financial Modeling Prep"
    assert record["field_evidence"]["short_float"]["source"] == (
        "Massive + Financial Modeling Prep"
    )


def test_massive_prefers_aligned_native_float_without_fmp_call() -> None:
    fallback_calls = []
    provider = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=_transport,
        float_fetcher=lambda symbol: fallback_calls.append(symbol) or {},
    )

    record = provider("AAPL")

    assert fallback_calls == []
    assert record["short_float"] == pytest.approx(0.01)
    assert record["field_evidence"]["short_float"]["source"] == "Massive"


def test_massive_requires_aligned_sec_components_for_enterprise_value() -> None:
    def misaligned(symbol):
        payload = _sec_fundamentals(symbol)
        payload["field_evidence"]["total_cash"]["observed_at"] = "2025-12-31"
        return payload

    record = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=_transport,
        fundamentals_fetcher=misaligned,
    )("AAPL")

    assert record["market_cap"] == 3_000_000_000_000
    assert record["enterprise_value"] is None
    assert "cash_period=2025-12-31" in record["field_evidence"][
        "enterprise_value"
    ]["detail"]


def test_massive_isolates_fmp_quota_failure_and_keeps_native_evidence() -> None:
    def transport(path, params, api_key, timeout):
        payload = _transport(path, params, api_key, 7)
        if path.endswith("/float"):
            payload["results"][0]["effective_date"] = "2025-12-31"
        return payload

    def exhausted(_symbol):
        raise FmpQuotaExceeded("reserved")

    record = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=transport,
        float_fetcher=exhausted,
    )("AAPL")

    assert record["short_float"] is None
    assert record["massive_endpoint_errors"]["float_fallback"]["type"] == (
        "FmpQuotaExceeded"
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
    with pytest.raises(ValueError, match="results object"):
        massive_module._result_object({"results": []})
    assert massive_module._result_object({"results": {"ticker": "AAPL"}}) == {
        "ticker": "AAPL"
    }
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


def test_massive_ticker_details_cache_reuses_on_demand_payload(
    tmp_path: Path,
) -> None:
    calls = []

    def transport(path, params, api_key, timeout):
        calls.append(path)
        return {"results": {"ticker": "AAPL", "market_cap": 100}}

    provider = MassiveMarketDataProvider(
        "secret",
        transport=transport,
        ticker_details_cache=MassiveTickerDetailsCache(tmp_path / "cache.json"),
    )

    assert provider.fetch_ticker_details("AAPL")["results"]["market_cap"] == 100
    assert provider.fetch_ticker_details("aapl")["results"]["market_cap"] == 100
    assert calls == ["/v3/reference/tickers/AAPL"]


def test_massive_prefetch_resumes_and_negative_caches_not_found(
    tmp_path: Path,
) -> None:
    calls = []

    def transport(path, params, api_key, timeout):
        symbol = path.rsplit("/", 1)[-1]
        calls.append(symbol)
        if symbol == "BBB":
            raise RuntimeError("Massive HTTP 404")
        return {"results": {"ticker": symbol, "market_cap": 100}}

    provider = MassiveMarketDataProvider(
        "secret",
        transport=transport,
        ticker_details_cache=MassiveTickerDetailsCache(tmp_path / "cache.json"),
        prefetch_policy=ProviderPolicy(
            max_retries=0, rate_limit_per_second=100_000
        ),
    )

    first = provider.prefetch_ticker_details(
        ["AAA", "BBB", "CCC"], max_symbols=2
    )
    second = provider.prefetch_ticker_details(
        ["AAA", "BBB", "CCC"], max_symbols=2
    )

    assert first["attempted"] == 2
    assert first["negative_cached"] == 1
    assert first["cached"] == 2
    assert first["remaining"] == 1
    assert second["attempted"] == 1
    assert second["complete"] is True
    assert second["available"] == 2
    assert second["missing"] == 1
    assert calls == ["AAA", "BBB", "CCC"]


def test_massive_prefetch_stops_on_authentication_and_validates_config(
    tmp_path: Path,
) -> None:
    provider = MassiveMarketDataProvider(
        "secret",
        transport=lambda *args: (_ for _ in ()).throw(
            RuntimeError("Massive HTTP 403")
        ),
        ticker_details_cache=MassiveTickerDetailsCache(tmp_path / "cache.json"),
        prefetch_policy=ProviderPolicy(
            max_retries=0, rate_limit_per_second=100_000
        ),
    )

    summary = provider.prefetch_ticker_details(
        ["AAA", "BBB"], max_symbols=2
    )

    assert summary["attempted"] == 1
    assert summary["stopped_reason"] == "authentication"
    assert summary["remaining"] == 2
    with pytest.raises(ValueError, match="max_symbols"):
        provider.prefetch_ticker_details(["AAA"], max_symbols=0)
    with pytest.raises(ValueError, match="cache_days"):
        MassiveMarketDataProvider("secret", ticker_details_cache_days=0)
    with pytest.raises(ValueError, match="request_limit_per_minute"):
        MassiveMarketDataProvider("secret", request_limit_per_minute=0)
    with pytest.raises(RuntimeError, match="cache não configurado"):
        MassiveMarketDataProvider("secret").prefetch_ticker_details(
            ["AAA"], max_symbols=1
        )


def test_massive_internal_pacing_honors_call_window() -> None:
    current = [0.0]
    sleeps = []

    def sleep(delay):
        sleeps.append(delay)
        current[0] += delay

    provider = MassiveMarketDataProvider(
        "secret",
        transport=lambda *args: {"results": {}},
        request_limit_per_minute=2,
        sleeper=sleep,
        monotonic=lambda: current[0],
    )

    provider._get("/one")
    provider._get("/two")
    provider._get("/three")

    assert sleeps == [60.0]


def test_massive_bulk_float_prefetch_resumes_pages_and_strips_api_key(
    tmp_path: Path,
) -> None:
    calls = []

    def transport(path, params, api_key, timeout):
        calls.append((path, dict(params)))
        if "cursor" not in params:
            return {
                "results": [
                    {
                        "ticker": "AAA",
                        "free_float": 80,
                        "effective_date": "2026-07-01",
                    }
                ],
                "next_url": (
                    "https://api.massive.com/stocks/vX/float?"
                    "cursor=next-page&apiKey=must-not-persist"
                ),
            }
        return {
            "results": [
                {
                    "ticker": "BBB",
                    "free_float": 90,
                    "effective_date": "2026-07-01",
                }
            ]
        }

    cache = MassiveFloatSnapshotCache(tmp_path / "float.json")
    provider = MassiveMarketDataProvider(
        "secret",
        transport=transport,
        float_snapshot_cache=cache,
        request_limit_per_minute=100,
        prefetch_policy=ProviderPolicy(
            max_retries=0, rate_limit_per_second=100_000
        ),
    )

    first = provider.prefetch_float_universe(
        ["AAA", "BBB", "CCC"], max_pages=1
    )
    second = provider.prefetch_float_universe(
        ["AAA", "BBB", "CCC"], max_pages=10
    )
    third = provider.prefetch_float_universe(
        ["AAA", "BBB", "CCC"], max_pages=10
    )

    assert first["pages_fetched"] == 1
    assert first["stopped_reason"] == "page_limit"
    assert second["pages_fetched"] == 1
    assert second["complete"] is True
    assert second["available"] == 2
    assert second["missing"] == 1
    assert third["pages_fetched"] == 0
    assert calls == [
        ("/stocks/vX/float", {"limit": "1000", "sort": "ticker.asc"}),
        ("/stocks/vX/float", {"cursor": "next-page"}),
    ]
    assert "must-not-persist" not in cache.path.read_text(encoding="utf-8")


def test_massive_provider_uses_complete_bulk_float_without_symbol_call(
    tmp_path: Path,
) -> None:
    cache = MassiveFloatSnapshotCache(tmp_path / "float.json")
    cache.append_page(
        [
            {
                "ticker": "AAPL",
                "free_float": 15_000_000_000,
                "effective_date": "2026-06-15",
            }
        ],
        None,
    )
    requested_paths = []

    def transport(path, params, api_key, timeout):
        requested_paths.append(path)
        if path.endswith("/float"):
            raise AssertionError("per-symbol Float must not be called")
        return _transport(path, params, api_key, 7)

    record = MassiveMarketDataProvider(
        "secret-key",
        timeout_seconds=7,
        transport=transport,
        float_snapshot_cache=cache,
    )("AAPL")

    assert record["short_float"] == pytest.approx(0.01)
    assert "/stocks/vX/float" not in requested_paths
    assert record["_raw_massive"]["float_bulk"]["free_float"] == (
        15_000_000_000
    )


def test_massive_float_prefetch_rejects_unsafe_cursor_and_invalid_config(
    tmp_path: Path,
) -> None:
    assert MassiveMarketDataProvider._next_request_from_url(None) is None
    with pytest.raises(ValueError, match="host"):
        MassiveMarketDataProvider._next_request_from_url(
            "https://evil.example/stocks/vX/float?cursor=x"
        )
    with pytest.raises(ValueError, match="path"):
        MassiveMarketDataProvider._next_request_from_url(
            "https://api.massive.com/other?cursor=x"
        )
    with pytest.raises(ValueError, match="float cache"):
        MassiveMarketDataProvider("secret", float_page_limit=0)
    with pytest.raises(RuntimeError, match="snapshot cache"):
        MassiveMarketDataProvider("secret").prefetch_float_universe(
            ["AAPL"], max_pages=1
        )
    provider = MassiveMarketDataProvider(
        "secret",
        float_snapshot_cache=MassiveFloatSnapshotCache(tmp_path / "float.json"),
    )
    with pytest.raises(ValueError, match="max_pages"):
        provider.prefetch_float_universe(["AAPL"], max_pages=0)

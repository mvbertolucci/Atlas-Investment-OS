from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import providers.fmp as fmp_module
from providers.fmp import (
    FmpMarketDataProvider,
    build_fmp_secondary_provider,
    load_fmp_api_key,
)
from providers.fmp_cache import FmpCacheStore


def _transport(path, params, api_key, timeout):
    assert params["symbol"] == "AAPL"
    assert api_key == "free-key"
    assert timeout == 7
    if path.endswith("market-capitalization"):
        return [
            {
                "symbol": "AAPL",
                "date": "2026-07-17",
                "marketCap": 4_901_758_191_440,
            }
        ]
    if path.endswith("enterprise-values"):
        return [
            {
                "symbol": "AAPL",
                "date": "2025-09-27",
                "addTotalDebt": 112_377_000_000,
                "minusCashAndCashEquivalents": 35_934_000_000,
            }
        ]
    return [
        {
            "symbol": "AAPL",
            "date": "2026-07-15 22:36:05",
            "floatShares": 14_662_387_495,
        }
    ]


def test_fmp_maps_current_market_cap_and_derives_enterprise_value() -> None:
    record = FmpMarketDataProvider(
        "free-key", timeout_seconds=7, transport=_transport
    )("aapl")

    assert record["market_cap"] == 4_901_758_191_440
    assert record["enterprise_value"] == 4_978_201_191_440
    assert record["field_evidence"]["market_cap"]["observed_at"] == (
        "2026-07-17"
    )
    assert "balance_sheet_period=2025-09-27" in record[
        "field_evidence"
    ]["enterprise_value"]["detail"]
    assert "free-key" not in json.dumps(record)


def test_fmp_fetch_float_returns_dated_share_count() -> None:
    result = FmpMarketDataProvider(
        "free-key", timeout_seconds=7, transport=_transport
    ).fetch_float("aapl")

    assert result["free_float"] == 14_662_387_495
    assert result["observed_at"] == "2026-07-15 22:36:05"
    assert result["source"] == "Financial Modeling Prep"


def test_fmp_key_loading_is_gated_and_environment_wins(
    tmp_path: Path, monkeypatch
) -> None:
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"fmp_api_key": "file-key"}), "utf-8")
    settings = {
        "fmp_secondary_enabled": True,
        "provider_secrets_path": str(secrets),
    }
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    assert load_fmp_api_key(tmp_path, settings) == "file-key"
    assert isinstance(
        build_fmp_secondary_provider(tmp_path, settings),
        FmpMarketDataProvider,
    )
    assert load_fmp_api_key(
        tmp_path, {**settings, "fmp_secondary_enabled": False}
    ) is None
    monkeypatch.setenv("FMP_API_KEY", "environment-key")
    assert load_fmp_api_key(tmp_path, settings) == "environment-key"


def test_fmp_missing_or_invalid_secret_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    settings = {"fmp_secondary_enabled": True}
    assert load_fmp_api_key(tmp_path, settings) is None
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", "utf-8")
    settings["provider_secrets_path"] = str(invalid)
    assert load_fmp_api_key(tmp_path, settings) is None


def test_fmp_rejects_invalid_configuration_and_payload() -> None:
    with pytest.raises(ValueError, match="api_key"):
        FmpMarketDataProvider("")
    with pytest.raises(ValueError, match="timeout_seconds"):
        FmpMarketDataProvider("key", timeout_seconds=0)
    with pytest.raises(ValueError, match="list"):
        FmpMarketDataProvider("key", transport=lambda *args: {})("AAPL")


def test_fmp_marks_enterprise_value_unavailable_without_components() -> None:
    def transport(path, params, api_key, timeout):
        rows = _transport(path, params, "free-key", 7)
        if path.endswith("enterprise-values"):
            rows[0].pop("addTotalDebt")
        return rows

    record = FmpMarketDataProvider(
        "free-key", timeout_seconds=7, transport=transport
    )("AAPL")

    assert record["enterprise_value"] is None
    assert record["field_evidence"]["enterprise_value"]["status"] == (
        "unavailable"
    )


def test_fmp_transport_parses_json_and_sanitizes_errors(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(
        fmp_module, "urlopen", lambda *args, **kwargs: Response()
    )
    assert fmp_module._request_json("/test", {}, "secret", 1) == []

    def forbidden(*args, **kwargs):
        raise HTTPError("https://example.test", 403, "denied", {}, None)

    monkeypatch.setattr(fmp_module, "urlopen", forbidden)
    with pytest.raises(RuntimeError, match="HTTP 403") as captured:
        fmp_module._request_json("/test", {}, "secret", 1)
    assert "secret" not in str(captured.value)

    monkeypatch.setattr(
        fmp_module,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        fmp_module._request_json("/test", {}, "secret", 1)


def test_fmp_helpers_reject_unusable_values() -> None:
    assert fmp_module._latest_row([]) == {}
    assert fmp_module._number("invalid") is None
    assert fmp_module._number(-1) is None


def test_fmp_prefetch_batches_market_float_and_resumable_enterprise(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(path, params, api_key, timeout):
        calls.append((path, dict(params)))
        if path.endswith("market-capitalization-batch"):
            return [
                {"symbol": symbol, "date": "2026-07-17", "marketCap": 100}
                for symbol in params["symbols"].split(",")
            ]
        if path.endswith("shares-float-all"):
            return [
                {"symbol": "AAA", "date": "2026-07-16", "floatShares": 80},
                {"symbol": "BBB", "date": "2026-07-16", "floatShares": 90},
            ]
        return [
            {
                "symbol": params["symbol"],
                "date": "2026-06-30",
                "addTotalDebt": 20,
                "minusCashAndCashEquivalents": 5,
            }
        ]

    cache = FmpCacheStore(tmp_path / "fmp.json")
    provider = FmpMarketDataProvider(
        "free-key",
        transport=transport,
        cache=cache,
        daily_call_limit=10,
        prefetch_reserve_calls=2,
        prefetch_threshold=2,
        market_batch_size=10,
        float_page_size=100,
        prefetch_rate_limit_per_second=100_000,
    )

    summary = provider.prefetch(["AAA", "BBB", "AAA"])
    record = provider("AAA")
    float_record = provider.fetch_float("BBB")

    assert summary["mode"] == "batch_cache"
    assert summary["requested"] == 2
    assert summary["market_cached"] == 2
    assert summary["market_available"] == 2
    assert summary["float_cached"] == 2
    assert summary["float_available"] == 2
    assert summary["enterprise_cached"] == 2
    assert summary["enterprise_available"] == 2
    assert summary["quota_used_after"] == 4
    assert record["market_cap"] == 100
    assert record["enterprise_value"] == 115
    assert float_record["free_float"] == 90
    assert len(calls) == 4


def test_fmp_prefetch_stops_before_reserved_quota_and_stays_cache_only(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def transport(path, params, api_key, timeout):
        calls.append(path)
        if path.endswith("market-capitalization-batch"):
            return [
                {"symbol": symbol, "date": "2026-07-17", "marketCap": 100}
                for symbol in params["symbols"].split(",")
            ]
        if path.endswith("shares-float-all"):
            return [
                {"symbol": "AAA", "date": "2026-07-16", "floatShares": 80},
                {"symbol": "BBB", "date": "2026-07-16", "floatShares": 90},
            ]
        raise AssertionError("enterprise call must remain reserved")

    provider = FmpMarketDataProvider(
        "free-key",
        transport=transport,
        cache=FmpCacheStore(tmp_path / "fmp.json"),
        daily_call_limit=3,
        prefetch_reserve_calls=1,
        prefetch_threshold=2,
        market_batch_size=10,
        float_page_size=100,
        prefetch_rate_limit_per_second=100_000,
    )

    summary = provider.prefetch(["AAA", "BBB"])
    record = provider("AAA")

    assert summary["quota_exhausted"] is True
    assert summary["enterprise_missing"] == 2
    assert summary["quota_remaining"] == 1
    assert record["market_cap"] == 100
    assert record["enterprise_value"] is None
    assert len(calls) == 2


def test_fmp_prefetch_negative_caches_unsupported_free_symbols(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def transport(path, params, api_key, timeout):
        calls.append((path, params.get("symbol")))
        if path.endswith("market-capitalization-batch"):
            return [
                {"symbol": "AAA", "date": "2026-07-17", "marketCap": 100}
            ]
        if path.endswith("shares-float-all"):
            return [
                {"symbol": "AAA", "date": "2026-07-16", "floatShares": 80}
            ]
        return [
            {
                "symbol": "AAA",
                "date": "2026-06-30",
                "addTotalDebt": 20,
                "minusCashAndCashEquivalents": 5,
            }
        ]

    provider = FmpMarketDataProvider(
        "free-key",
        transport=transport,
        cache=FmpCacheStore(tmp_path / "fmp.json"),
        daily_call_limit=10,
        prefetch_reserve_calls=1,
        prefetch_threshold=2,
        market_batch_size=10,
        float_page_size=100,
        prefetch_rate_limit_per_second=100_000,
    )

    summary = provider.prefetch(["AAA", "BBB"])
    unsupported = provider("BBB")

    assert summary["market_cached"] == 2
    assert summary["market_available"] == 1
    assert summary["market_missing"] == 1
    assert summary["float_cached"] == 2
    assert summary["float_available"] == 1
    assert summary["enterprise_available"] == 1
    assert summary["enterprise_missing"] == 1
    assert unsupported["market_cap"] is None
    assert unsupported["enterprise_value"] is None
    assert len(calls) == 3


def test_fmp_prefetch_does_not_negative_cache_float_without_full_scan(
    tmp_path: Path,
) -> None:
    def transport(path, params, api_key, timeout):
        assert path.endswith("market-capitalization-batch")
        return [
            {"symbol": symbol, "date": "2026-07-17", "marketCap": 100}
            for symbol in params["symbols"].split(",")
        ]

    provider = FmpMarketDataProvider(
        "free-key",
        transport=transport,
        cache=FmpCacheStore(tmp_path / "fmp.json"),
        daily_call_limit=2,
        prefetch_reserve_calls=1,
        prefetch_threshold=2,
        market_batch_size=10,
        prefetch_rate_limit_per_second=100_000,
    )

    summary = provider.prefetch(["AAA", "BBB"])

    assert summary["quota_exhausted"] is True
    assert summary["float_cached"] == 0
    assert summary["float_missing"] == 2

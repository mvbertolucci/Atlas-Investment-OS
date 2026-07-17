from __future__ import annotations

from pathlib import Path

import pandas as pd

import providers.yahoo as yahoo
from providers.contracts import ProviderPolicy


def _payload(source: str, market_cap):
    return {
        "symbol": "AAA",
        "source": source,
        "as_of": "2026-07-17T12:00:00+00:00",
        "market_cap": market_cap,
        "history": [],
    }


def test_watchlist_persists_raw_and_uses_secondary_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        yahoo,
        "fetch_symbol",
        lambda *_args, **_kwargs: _payload("Yahoo Finance", None),
    )
    rows = yahoo.fetch_watchlist(
        pd.DataFrame([{"symbol": "AAA", "name": "Company AAA"}]),
        provider_policy=ProviderPolicy(max_retries=0, rate_limit_per_second=1000),
        raw_snapshot_dir=tmp_path,
        secondary_fetcher=lambda *_args, **_kwargs: _payload("Independent", 500.0),
        critical_fields=("market_cap",),
    )

    assert rows[0]["market_cap"] == 500.0
    assert rows[0]["field_evidence"]["market_cap"]["confirmation_status"] == "fallback"
    assert Path(rows[0]["raw_snapshot_path"]).exists()
    assert Path(rows[0]["secondary_raw_snapshot_path"]).exists()


def test_secondary_failure_does_not_discard_valid_primary(monkeypatch) -> None:
    monkeypatch.setattr(
        yahoo,
        "fetch_symbol",
        lambda *_args, **_kwargs: _payload("Yahoo Finance", 100.0),
    )

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    rows = yahoo.fetch_watchlist(
        pd.DataFrame([{"symbol": "AAA"}]),
        provider_policy=ProviderPolicy(max_retries=0, rate_limit_per_second=1000),
        secondary_fetcher=unavailable,
        critical_fields=("market_cap",),
    )

    assert rows[0]["market_cap"] == 100.0
    assert rows[0]["secondary_provider_error"]["kind"] == "unavailable"
    assert rows[0]["field_evidence"]["market_cap"]["confirmation_status"] == (
        "secondary_unavailable"
    )

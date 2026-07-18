from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.sec_companyfacts import (
    SecCompanyFactsProvider,
    build_sec_secondary_provider,
    load_sec_user_agent,
    record_from_company_facts,
)


def _entry(value: float, *, end: str = "2026-06-30") -> dict:
    return {
        "end": end,
        "val": value,
        "filed": "2026-07-15",
        "accn": f"0000000001-26-{int(value):06d}",
        "form": "10-K",
    }


def _facts() -> dict:
    tags = {
        "CashAndCashEquivalentsAtCarryingValue": 50,
        "LongTermDebtNoncurrent": 100,
        "LongTermDebtCurrent": 10,
        "ShortTermBorrowings": 5,
        "AssetsCurrent": 200,
        "LiabilitiesCurrent": 100,
        "NetCashProvidedByUsedInOperatingActivities": 80,
        "PaymentsToAcquirePropertyPlantAndEquipment": 20,
        "OperatingIncomeLoss": 70,
        "DepreciationDepletionAndAmortization": 30,
    }
    return {
        "facts": {
            "us-gaap": {
                tag: {"units": {"USD": [_entry(value)]}}
                for tag, value in tags.items()
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_entry(1_000)]}
                }
            },
        }
    }


def test_companyfacts_maps_comparable_critical_fields() -> None:
    record = record_from_company_facts(
        "AAA",
        _facts(),
        cik="0000000001",
        retrieved_at="2026-07-17T12:00:00+00:00",
    )

    assert record["total_cash"] == 50
    assert record["total_debt"] == 115
    assert record["current_ratio"] == 2
    assert record["free_cashflow"] == 60
    assert record["ebitda"] == 100
    assert record["shares_outstanding"] == 1_000
    assert record["market_cap"] is None
    assert record["field_evidence"]["total_debt"]["observed_at"] == "2026-06-30"
    assert record["field_evidence"]["market_cap"]["status"] == "unavailable"


def test_sec_provider_caches_ticker_map() -> None:
    map_calls = 0
    facts_calls = 0

    def map_fetcher(*, user_agent: str):
        nonlocal map_calls
        map_calls += 1
        assert "Marcus" in user_agent
        return {"AAA": "0000000001"}

    def facts_fetcher(_cik, *, user_agent):
        nonlocal facts_calls
        facts_calls += 1
        return _facts()

    provider = SecCompanyFactsProvider(
        "Atlas Marcus contact@example.com",
        ticker_map_fetcher=map_fetcher,
        facts_fetcher=facts_fetcher,
    )

    assert provider("AAA")["total_cash"] == 50
    assert provider("AAA")["total_cash"] == 50
    assert map_calls == 1
    assert facts_calls == 1


def test_sec_provider_has_typed_not_found_input_for_boundary() -> None:
    provider = SecCompanyFactsProvider(
        "Atlas Marcus contact@example.com",
        ticker_map_fetcher=lambda **_kwargs: {},
        facts_fetcher=lambda *_args, **_kwargs: {},
    )
    with pytest.raises(RuntimeError, match="404 CIK"):
        provider("UNKNOWN")


def test_user_agent_is_loaded_only_when_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    secrets = tmp_path / "secrets.json"
    secrets.write_text(
        json.dumps({"sec_user_agent": "Atlas Marcus contact@example.com"}),
        encoding="utf-8",
    )
    settings = {
        "sec_secondary_enabled": True,
        "provider_secrets_path": str(secrets),
    }

    assert load_sec_user_agent(tmp_path, settings) == "Atlas Marcus contact@example.com"
    assert isinstance(build_sec_secondary_provider(tmp_path, settings), SecCompanyFactsProvider)
    assert load_sec_user_agent(
        tmp_path,
        {**settings, "sec_secondary_enabled": False},
    ) is None


def test_environment_user_agent_takes_precedence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "SEC_EDGAR_USER_AGENT",
        "Atlas Environment contact@example.com",
    )
    assert load_sec_user_agent(
        tmp_path,
        {"sec_secondary_enabled": True},
    ) == "Atlas Environment contact@example.com"


def test_sec_provider_rejects_unidentified_user_agent() -> None:
    with pytest.raises(ValueError, match="e-mail"):
        SecCompanyFactsProvider("anonymous bot")

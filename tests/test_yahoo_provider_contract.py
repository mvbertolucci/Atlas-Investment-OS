from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

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


def test_multiple_secondaries_reconcile_their_declared_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        yahoo,
        "fetch_symbol",
        lambda *_args, **_kwargs: {
            **_payload("Yahoo Finance", None),
            "total_debt": None,
        },
    )

    class Sec:
        provider_name = "SEC"
        supported_fields = frozenset({"total_debt"})

        def __call__(self, *_args, **_kwargs):
            return {
                "symbol": "AAA",
                "source": "SEC",
                "as_of": "2026-07-17T12:00:00+00:00",
                "total_debt": 100.0,
            }

    class Market:
        provider_name = "Market Data"
        supported_fields = frozenset({"market_cap"})

        def __call__(self, *_args, **_kwargs):
            return _payload("Market Data", 500.0)

    rows = yahoo.fetch_watchlist(
        pd.DataFrame([{"symbol": "AAA"}]),
        provider_policy=ProviderPolicy(
            max_retries=0, rate_limit_per_second=1000
        ),
        raw_snapshot_dir=tmp_path,
        secondary_fetcher=Sec(),
        secondary_fetchers=(Market(),),
        critical_fields=("market_cap", "total_debt", "short_float"),
    )

    assert rows[0]["market_cap"] == 500.0
    assert rows[0]["total_debt"] == 100.0
    assert set(rows[0]["secondary_raw_snapshots"]) == {
        "SEC",
        "Market Data",
    }
    assert rows[0]["field_evidence"]["short_float"][
        "confirmation_status"
    ] == "secondary_unavailable"


def test_trailing_pe_marked_not_applicable_when_earnings_non_positive() -> None:
    """PE ausente por lucro trailing nao-positivo e' estrutural (not_applicable),
    nunca `missing` -- do contrario nomes deficitarios com valuation completo
    (EV/EBITDA, Forward PE) travam eternamente no gate de confianca."""
    # trailingPE ausente + EPS trailing negativo => nao aplicavel
    assert yahoo._trailing_pe_structurally_absent(
        None, {"trailingEps": -1.42, "forwardPE": 18.0}
    )
    # sinal de prejuizo via margem liquida negativa tambem qualifica
    assert yahoo._trailing_pe_structurally_absent(
        None, {"profitMargins": -0.11}
    )
    # PE presente => nunca not_applicable, mesmo com sinais ruidosos
    assert not yahoo._trailing_pe_structurally_absent(
        22.5, {"trailingEps": -1.0}
    )
    # PE ausente SEM nenhum sinal de earnings => mantem `missing` conservador
    # (nao mascara falha de coleta como se fosse estrutural)
    assert not yahoo._trailing_pe_structurally_absent(None, {})
    # empresa lucrativa com PE faltando por falha de fetch => segue `missing`
    assert not yahoo._trailing_pe_structurally_absent(
        None, {"trailingEps": 3.2, "profitMargins": 0.18}
    )


def test_stockholders_equity_reads_most_recent_column() -> None:
    bs = pd.DataFrame(
        {"2025-12-31": [81_544_000_000.0], "2024-12-31": [76_000_000_000.0]},
        index=["Stockholders Equity"],
    )
    assert yahoo._stockholders_equity(bs) == pytest.approx(81_544_000_000.0)
    # patrimonio negativo (deficit acumulado) e' devolvido como negativo
    neg = pd.DataFrame({"2025-12-31": [-500_469_000.0]}, index=["Stockholders Equity"])
    assert yahoo._stockholders_equity(neg) < 0
    assert yahoo._stockholders_equity(None) is None


def test_roe_reconciled_from_finnhub_when_yahoo_omits_it_and_equity_positive() -> None:
    """Cenario JNJ: Yahoo omite returnOnEquity (equity>0), Finnhub supre roeTTM.
    Como o primario esta `missing` (usable-gap), a reconciliacao preenche."""
    from providers.evidence import ensure_field_evidence, reconcile_critical_fields

    primary = ensure_field_evidence(
        {"symbol": "JNJ", "source": "Yahoo Finance", "as_of": "2026-07-21", "roe": None},
        raw_presence={"roe": False},
    )
    # Yahoo omite a chave => `missing` (ausencia genuina, dentro do usable-gap)
    assert primary["field_evidence"]["roe"]["status"] == "missing"
    secondary = ensure_field_evidence(
        {"symbol": "JNJ", "source": "Finnhub", "as_of": "2026-07-21", "roe": 0.2626}
    )
    reconciled = reconcile_critical_fields(primary, secondary, ("roe",))
    assert reconciled["roe"] == pytest.approx(0.2626)
    assert reconciled["field_evidence"]["roe"]["status"] == "present"


def test_not_applicable_roe_is_never_overwritten_by_secondary() -> None:
    """Cenario IBRX: equity<=0 marca roe not_applicable no primario; mesmo com
    Finnhub devolvendo um numero (enganoso), a reconciliacao nao sobrescreve."""
    from providers.evidence import (
        DataValueStatus,
        FieldEvidence,
        ensure_field_evidence,
        reconcile_critical_fields,
    )

    primary = ensure_field_evidence(
        {"symbol": "IBRX", "source": "Yahoo Finance", "as_of": "2026-07-21", "roe": None},
        not_applicable_fields={"roe"},
    )
    assert primary["field_evidence"]["roe"]["status"] == "not_applicable"
    secondary = ensure_field_evidence(
        {"symbol": "IBRX", "source": "Finnhub", "as_of": "2026-07-21", "roe": -1.9329}
    )
    reconciled = reconcile_critical_fields(primary, secondary, ("roe",))
    # valor e status estruturais preservados -- nunca troca por -193%
    assert reconciled.get("roe") is None
    assert reconciled["field_evidence"]["roe"]["status"] == "not_applicable"

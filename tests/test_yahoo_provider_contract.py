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


def test_enterprise_value_implausible_rejects_only_order_of_magnitude_errors() -> None:
    """Calibrado contra valores reais medidos ao vivo na carteira (2026-07-21):
    alavancagem pesada (BTI 5.4x, FMC 4.0x) e caixa liquido grande (BRK-B
    -0.25x) sao legitimos e devem passar; ASML (2750x via enterpriseToEbitda,
    EV=$37,1tri vs market cap $692bi) e YPF (EV=$12,87tri vs $20bi, 639x) sao
    erro de ordem de grandeza no proprio feed do Yahoo e devem ser rejeitados."""
    # legitimos -- nunca rejeitar
    assert not yahoo._enterprise_value_implausible(132_588_109_824, 710_504_218_624)  # BTI 5.36x
    assert not yahoo._enterprise_value_implausible(1_423_827_200, 5_692_756_992)  # FMC 4.0x
    assert not yahoo._enterprise_value_implausible(1_056_103_399_424, -265_521_627_136)  # BRK-B -0.25x
    assert not yahoo._enterprise_value_implausible(99_445_293_056, 105_473_630_208)  # GD 1.06x
    # erro de ordem de grandeza -- sempre rejeitar
    assert yahoo._enterprise_value_implausible(691_960_020_992, 37_103_157_116_928)  # ASML 53.6x
    assert yahoo._enterprise_value_implausible(20_127_873_024, 12_877_943_537_664)  # YPF 639.8x
    # sem market_cap valido -- nunca afirma implausibilidade (conservador)
    assert not yahoo._enterprise_value_implausible(None, 1_000_000)
    assert not yahoo._enterprise_value_implausible(0, 1_000_000)


def test_enterprise_value_rejection_nulls_yahoo_own_derived_multiples() -> None:
    """A rejeicao invalida enterprise_value E os multiplos que o Yahoo deriva
    internamente dele (ev_to_ebitda/ev_to_revenue) sem apagar o valor bruto do
    audit trail -- raw_values preserva o numero rejeitado, o motor ve `invalid`,
    nao `missing`."""
    from providers.evidence import ensure_field_evidence

    record = {
        "symbol": "ASML",
        "source": "Yahoo Finance",
        "as_of": "2026-07-21",
        "market_cap": 691_960_020_992,
        "enterprise_value": None,  # ja nulificado pela guarda de plausibilidade
        "ev_to_ebitda": None,
        "ev_to_revenue": None,
    }
    annotated = ensure_field_evidence(
        record,
        raw_presence={
            "enterprise_value": True, "ev_to_ebitda": True, "ev_to_revenue": True,
        },
        raw_values={
            "enterprise_value": 37_103_157_116_928,
            "ev_to_ebitda": 2750.75,
            "ev_to_revenue": 100.0,
        },
    )
    for field in ("enterprise_value", "ev_to_ebitda", "ev_to_revenue"):
        assert annotated["field_evidence"][field]["status"] == "invalid"
    assert annotated["enterprise_value"] is None


def test_compute_market_cap_multiplies_price_by_shares() -> None:
    """Live-measured (ADR-038): price x shares matches the vendor's own
    marketCap almost exactly for real ADR holdings, without any FX -- BNTX's
    real 92.33 price x 252,884,261 shares reproduces Yahoo's own $23.35B."""
    assert yahoo._compute_market_cap(92.33, 252_884_261) == pytest.approx(
        23_348_803_818, rel=1e-6
    )
    assert yahoo._compute_market_cap(None, 252_884_261) is None
    assert yahoo._compute_market_cap(92.33, None) is None
    assert yahoo._compute_market_cap(92.33, 0) is None
    assert yahoo._compute_market_cap(-1, 100) is None


def test_resolve_enterprise_value_direct_vendor_when_plausible() -> None:
    """BTI's own reported EV (5.27x market cap, a real leveraged-conglomerate
    multiple) is already plausible -- used unchanged, no reconstruction."""
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=132_517_445_632,
        enterprise_value_reported=698_876_887_040,
        total_debt=35_070_001_152,
        total_cash=3_843_000_064,
        financial_currency="GBP",
        quote_currency="USD",
        fx_rate_fetcher=lambda _currency: None,
    )
    assert value == 698_876_887_040
    assert provenance == "direct_vendor"


def test_resolve_enterprise_value_reconstructs_when_vendor_implausible_but_currency_matches() -> None:
    """Vendor EV implausible, financialCurrency == quote currency (no FX
    possible) -- but the naive market_cap+debt-cash reconstruction is itself
    plausible, so it is used instead of giving up."""
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=1_000_000_000,
        enterprise_value_reported=50_000_000_000,  # 50x, implausible
        total_debt=200_000_000,
        total_cash=50_000_000,
        financial_currency="USD",
        quote_currency="USD",
        fx_rate_fetcher=lambda _currency: None,
    )
    assert value == pytest.approx(1_150_000_000)
    assert provenance == "reconstructed"


def test_resolve_enterprise_value_fx_corrects_currency_unit_bug() -> None:
    """Live-measured on YPF (ADR-038): raw totalDebt/totalCash are labeled
    USD but are actually ARS (14.8T/2.3T), giving EV/MarketCap=639x either
    way (vendor or naive reconstruction). Converting at the real ARS->USD
    spot rate resolves it to a plausible ~1.4x."""
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=20_127_873_024,
        enterprise_value_reported=12_877_943_537_664,
        total_debt=14_817_286_946_816,
        total_cash=2_330_515_996_672,
        financial_currency="ARS",
        quote_currency="USD",
        fx_rate_fetcher=lambda currency: 0.00067681895 if currency == "ARS" else None,
    )
    assert value == pytest.approx(28_579_156_227, rel=1e-3)
    assert value / 20_127_873_024 < 2.0
    assert provenance == "fx_corrected:ARS->USD@0.000676819"


def test_resolve_enterprise_value_implausible_same_currency_gives_up() -> None:
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=1_000_000_000,
        enterprise_value_reported=50_000_000_000,
        total_debt=40_000_000_000,  # still implausible even reconstructed
        total_cash=0,
        financial_currency="USD",
        quote_currency="USD",
        fx_rate_fetcher=lambda _currency: None,
    )
    assert value is None
    assert provenance == "implausible_same_currency"


def test_resolve_enterprise_value_fx_rate_unavailable() -> None:
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=1_000_000_000,
        enterprise_value_reported=50_000_000_000,
        total_debt=40_000_000_000,
        total_cash=0,
        financial_currency="EUR",
        quote_currency="USD",
        fx_rate_fetcher=lambda _currency: None,
    )
    assert value is None
    assert provenance == "fx_rate_unavailable"


def test_resolve_enterprise_value_implausible_after_fx_correction() -> None:
    """FX correction applied, but the result is still implausible -- not a
    pure currency-unit bug, stays rejected rather than accepting a bad
    number just because a conversion was attempted."""
    value, provenance = yahoo._resolve_enterprise_value(
        market_cap=1_000_000_000,
        enterprise_value_reported=90_000_000_000,
        total_debt=200_000_000_000,
        total_cash=0,
        financial_currency="EUR",
        quote_currency="USD",
        fx_rate_fetcher=lambda _currency: 1.08,
    )
    assert value is None
    assert provenance == "implausible_after_fx_correction"


def test_derive_ev_ebitda_mirrors_ev_ebit_pattern() -> None:
    """Live-measured on YPF (ADR-038): resolved EV $28.58B / real ebitda
    gives the ratio Yahoo's own (rejected) enterpriseToEbitda cannot."""
    assert yahoo._derive_ev_ebitda(28_579_156_227, 5_000_000_000) == pytest.approx(
        5.7158312454
    )
    assert yahoo._derive_ev_ebitda(None, 5_000_000_000) is None
    assert yahoo._derive_ev_ebitda(28_579_156_227, None) is None
    assert yahoo._derive_ev_ebitda(28_579_156_227, 0) is None


def test_cash_and_equivalents_uses_strict_balance_sheet_row_not_broad_total() -> None:
    """Live-measured on BRK-B (ADR-038 adendo): info.get("totalCash") folds
    short-term investments into "cash" ($397.4B); the balance sheet's own
    strict "Cash And Cash Equivalents" row ($58.1B, Q1 2026) is the real
    figure, close to SEC EDGAR's independently reported $58.8B."""
    quarterly = pd.DataFrame(
        {
            "2026-03-31": [
                58_122_000_000.0,
                400_000_000_000.0,
            ]
        },
        index=["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    )
    assert yahoo._cash_and_equivalents(quarterly) == pytest.approx(58_122_000_000.0)
    assert yahoo._cash_and_equivalents(None) is None
    assert yahoo._cash_and_equivalents(pd.DataFrame()) is None


def test_cash_and_equivalents_prefers_quarterly_over_stale_annual() -> None:
    """Live-measured (ADR-038 adendo): the annual statement's most recent
    column can lag a full quarter behind `mostRecentQuarter`, which is the
    date Atlas stamps on this field regardless of which statement supplied
    the value -- reading the annual one silently mislabels a quarter-old
    figure as current. BRK-B: annual FY2025 shows $51.9B, quarterly Q1 2026
    shows $58.1B (matching SEC EDGAR); the quarterly value must win."""
    annual = pd.DataFrame(
        {"2025-12-31": [51_877_000_000.0]}, index=["Cash And Cash Equivalents"]
    )
    quarterly = pd.DataFrame(
        {"2026-03-31": [58_122_000_000.0]}, index=["Cash And Cash Equivalents"]
    )
    assert yahoo._cash_and_equivalents(quarterly, annual) == pytest.approx(
        58_122_000_000.0
    )
    # Falls back to annual only when no quarterly statement is available.
    assert yahoo._cash_and_equivalents(None, annual) == pytest.approx(
        51_877_000_000.0
    )

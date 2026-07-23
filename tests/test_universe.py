from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from universe import UniversePolicy, evaluate_universe, load_universe_policy
from universe import write_universe_report


def _policy() -> UniversePolicy:
    return UniversePolicy(
        name="US Test Universe",
        benchmark="S&P 500",
        rebalance_frequency="monthly",
    )


def _eligible_row(symbol: str = "AAA") -> dict:
    return {
        "symbol": symbol,
        "quote_type": "EQUITY",
        "currency": "USD",
        "country": "United States",
        "sector": "Technology",
        "industry": "Software",
        "price": 100.0,
        "market_cap": 10_000_000_000.0,
        "volume": 1_000_000.0,
    }


def test_load_canonical_universe_policy() -> None:
    policy = load_universe_policy(Path("config/universe.yaml"))

    assert policy.to_dict() == {
        "name": "Atlas US Liquid Equities",
        "benchmark": "S&P 500",
        "rebalance_frequency": "monthly",
        "allowed_quote_types": ["EQUITY"],
        "allowed_currencies": ["USD"],
        "allowed_countries": ["United States"],
        "excluded_countries": [],
        "min_market_cap": 1_000_000_000.0,
        "min_price": 5.0,
        "min_volume": 100_000.0,
        "required_fields": [
            "symbol",
            "quote_type",
            "currency",
            "country",
            "sector",
            "price",
            "market_cap",
            "volume",
        ],
    }


def test_load_canonical_universe_market_policy() -> None:
    """
    Segundo screener (mercado amplo, separado do S&P 500): piso de USD 300
    milhões -- inclui small caps de verdade, ao contrário do piso de USD 1
    bilhão do screener S&P 500 (que na prática é piso de mid-cap+).
    """
    policy = load_universe_policy(Path("config/universe_market.yaml"))

    assert policy.name == "Atlas US Broad Market Equities"
    assert policy.benchmark != "S&P 500"
    assert policy.min_market_cap == 300_000_000.0
    assert policy.min_price == 5.0
    assert policy.min_volume == 100_000.0
    assert policy.allowed_quote_types == ("EQUITY",)


def test_load_canonical_universe_adr_policy() -> None:
    """
    Terceiro screener (ADRs, sobre a mesma coleta de mercado amplo já
    colectada -- ver docs/UNIVERSE_SOURCES.md): mesmo piso de USD 300
    milhões do screener de mercado amplo, mas domicílio dos EUA excluído
    em vez de exigido -- é justamente o que define um ADR.
    """
    policy = load_universe_policy(Path("config/universe_adr.yaml"))

    assert policy.name == "Atlas US-Listed ADRs"
    assert policy.allowed_countries == ("*",)
    assert policy.excluded_countries == ("United States",)
    assert policy.min_market_cap == 300_000_000.0
    assert policy.allowed_currencies == ("USD",)
    assert policy.allowed_quote_types == ("EQUITY",)


def test_policy_rejects_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="min_price"):
        UniversePolicy(
            name="Invalid",
            benchmark="Benchmark",
            rebalance_frequency="monthly",
            min_price=-1,
        )


def test_eligible_member_and_report_summary() -> None:
    report = evaluate_universe(
        pd.DataFrame([_eligible_row()]),
        _policy(),
    )

    assert report.total_count == 1
    assert report.eligible_count == 1
    assert report.excluded_count == 0
    assert report.average_data_coverage_pct == 100.0
    assert report.eligible_by_sector == {"Technology": 1}
    assert report.to_dict()["members"][0]["eligible"] is True


def test_filters_are_additive_and_auditable() -> None:
    row = _eligible_row("LOW")
    row.update(
        {
            "quote_type": "ETF",
            "currency": "BRL",
            "country": "Brazil",
            "price": 2.0,
            "market_cap": 500_000_000.0,
            "volume": 50_000.0,
        }
    )

    member = evaluate_universe(pd.DataFrame([row]), _policy()).members[0]

    assert member.eligible is False
    assert set(member.exclusion_reasons) == {
        "UNSUPPORTED_QUOTE_TYPE",
        "UNSUPPORTED_CURRENCY",
        "UNSUPPORTED_COUNTRY",
        "MARKET_CAP_BELOW_MINIMUM",
        "PRICE_BELOW_MINIMUM",
        "VOLUME_BELOW_MINIMUM",
    }


def _adr_policy() -> UniversePolicy:
    """
    Perfil de elegibilidade equivalente ao de um screener de ADR: qualquer
    país é aceito na inclusão (wildcard "*"), mas o domicílio dos EUA é
    explicitamente excluído -- só sobra empresa estrangeira negociada nos
    EUA em USD.
    """
    return UniversePolicy(
        name="ADR Test Universe",
        benchmark="US-Listed ADRs",
        rebalance_frequency="monthly",
        allowed_countries=("*",),
        excluded_countries=("United States",),
    )


def test_wildcard_country_allows_any_non_excluded_country() -> None:
    foreign_row = _eligible_row("FGN")
    foreign_row["country"] = "Argentina"

    member = evaluate_universe(
        pd.DataFrame([foreign_row]),
        _adr_policy(),
    ).members[0]

    assert member.eligible is True
    assert "UNSUPPORTED_COUNTRY" not in member.exclusion_reasons
    assert "EXCLUDED_COUNTRY" not in member.exclusion_reasons


def test_wildcard_country_still_excludes_named_country() -> None:
    us_row = _eligible_row("USX")  # country stays "United States"

    member = evaluate_universe(
        pd.DataFrame([us_row]),
        _adr_policy(),
    ).members[0]

    assert member.eligible is False
    assert member.exclusion_reasons == ("EXCLUDED_COUNTRY",)


def test_default_allow_list_behavior_is_unchanged_by_the_new_field() -> None:
    """
    Sem wildcard e sem excluded_countries, a allow-list estrita continua
    identica (aqui exercitada com uma politica US-only de fixture). Desde
    ADR-044 o screener de mercado amplo real usa `["*"]`; a politica do S&P 500
    (`config/universe.yaml`) segue US-only. Este teste cobre o comportamento
    da allow-list estrita, nao o valor de config de nenhum screener.
    """
    foreign_row = _eligible_row("FGN")
    foreign_row["country"] = "Argentina"

    member = evaluate_universe(
        pd.DataFrame([foreign_row]),
        _policy(),
    ).members[0]

    assert member.eligible is False
    assert member.exclusion_reasons == ("UNSUPPORTED_COUNTRY",)


def test_missing_fields_reduce_coverage_and_report_reason() -> None:
    row = _eligible_row()
    row["sector"] = None

    report = evaluate_universe(pd.DataFrame([row]), _policy())
    member = report.members[0]

    assert member.data_coverage_pct == 87.5
    assert member.exclusion_reasons == (
        "MISSING_REQUIRED_FIELD:sector",
    )
    assert report.exclusions_by_reason == {
        "MISSING_REQUIRED_FIELD:sector": 1,
    }


def test_duplicate_symbols_are_explicitly_excluded() -> None:
    report = evaluate_universe(
        pd.DataFrame([_eligible_row("dup"), _eligible_row("DUP")]),
        _policy(),
    )

    assert report.eligible_count == 0
    assert all(
        member.exclusion_reasons == ("DUPLICATE_SYMBOL",)
        for member in report.members
    )


def test_empty_universe_has_zero_coverage() -> None:
    report = evaluate_universe(pd.DataFrame(), _policy())

    assert report.total_count == 0
    assert report.average_data_coverage_pct == 0.0


def test_evaluate_universe_validates_contract_types() -> None:
    with pytest.raises(TypeError, match="DataFrame"):
        evaluate_universe([], _policy())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="UniversePolicy"):
        evaluate_universe(pd.DataFrame(), {})  # type: ignore[arg-type]


def test_write_universe_report_serializes_contract(tmp_path: Path) -> None:
    report = evaluate_universe(
        pd.DataFrame([_eligible_row()]),
        _policy(),
    )

    output = write_universe_report(report, tmp_path / "universe.json")

    assert output.exists()
    assert '"eligible_count": 1' in output.read_text(encoding="utf-8")


def test_write_universe_report_validates_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="UniverseReport"):
        write_universe_report({}, tmp_path / "invalid.json")  # type: ignore[arg-type]

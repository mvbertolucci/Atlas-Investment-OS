"""
Trava a resolução de valor por campo na página da empresa.

O defeito que originou estes testes era sistêmico, não de um papel: no run de
2026-07-24, 110 dos 117 símbolos exibiam `current_liquidity` com o selo
"presente" e, na coluna do valor, "não persistido" -- porque o pipeline
renomeia `current_ratio` para o nome interno (`analytics/mapper.py`,
`COLUMN_MAP`) e copia a evidência para os dois nomes, enquanto o número fica
gravado só sob um deles. Outros 117 de 117 exibiam a mesma contradição em
`secondary_raw_snapshots`, que é procedência do snapshot e nunca foi um
número.

Duas regras, portanto:

1. Nenhuma linha pode dizer "presente" e não mostrar valor -- se o número
   existe sob um apelido, a página o mostra e diz de onde veio.
2. O apelido NÃO socorre campo que o motor declarou ausente: pegar o número
   do gêmeo ali seria afirmar coleta que não houve.
"""
from __future__ import annotations

import re

import pytest

from analytics.mapper import COLUMN_MAP
from reports.company_page import (
    FIELD_ALIASES,
    METADATA_FIELDS,
    PERCENT_FIELDS,
    POINT_FIELDS,
    CompanyData,
    _evidence_rows,
    _value_for,
    displayable_evidence,
)


def _evidence(name: str, status: str) -> dict[str, object]:
    return {
        "status": status,
        "category": "fundamentals",
        "source": "Yahoo Finance",
        "observed_at": "2026-03-31",
    }


def _company(evidence: dict[str, object], **stored: object) -> CompanyData:
    return CompanyData(symbol="IBRX", evidence=evidence, raw=dict(stored))


def test_value_persisted_under_the_twin_name_is_found() -> None:
    data = _company(
        {"current_liquidity": _evidence("current_liquidity", "present")},
        current_ratio=6.666,
    )
    value, persisted, alias = _value_for(data, "current_liquidity")
    assert (value, persisted, alias) == (6.666, True, "current_ratio")


def test_no_row_claims_present_without_showing_the_number() -> None:
    data = _company(
        {
            "current_ratio": _evidence("current_ratio", "present"),
            "current_liquidity": _evidence("current_liquidity", "present"),
        },
        current_ratio=6.666,
    )
    html = _evidence_rows(data, "fundamentals")
    assert "não persistido" not in html
    # Os dois nomes mostram o MESMO número, com a mesma formatação: um
    # múltiplo (6,67x), nunca um percentual.
    assert html.count("6.67") == 2
    assert "6.67%" not in html
    assert "current_ratio" in html  # a linha do apelido diz de onde veio


def test_alias_does_not_rescue_a_field_the_engine_called_missing() -> None:
    data = _company(
        {
            "debt_to_equity": _evidence("debt_to_equity", "missing"),
            "net_debt_total_equity": _evidence("net_debt_total_equity", "present"),
        },
        net_debt_total_equity=0.42,
    )
    value, persisted, alias = _value_for(data, "debt_to_equity", allow_alias=False)
    assert (value, persisted, alias) == (None, False, None)
    html = _evidence_rows(data, "fundamentals")
    # A linha ausente segue com traço; a presente mostra o número.
    assert "não coletado" in html and "0.42" in html


def test_provenance_fields_leave_the_indicator_tables() -> None:
    evidence = {
        "secondary_raw_snapshots": _evidence("secondary_raw_snapshots", "present"),
        "raw_snapshot_path": _evidence("raw_snapshot_path", "present"),
        "roic": _evidence("roic", "present"),
    }
    assert set(displayable_evidence(evidence)) == {"roic"}
    html = _evidence_rows(_company(evidence, roic=0.12), "fundamentals")
    assert "secondary_raw_snapshots" not in html
    assert "raw_snapshot_path" not in html
    assert "1 campos" in html


def test_alias_groups_are_transitive() -> None:
    """`ev_to_ebitda` e `enterprise_to_ebitda` caem no mesmo `ev_ebitda`."""
    assert set(FIELD_ALIASES["ev_to_ebitda"]) == {"ev_ebitda", "enterprise_to_ebitda"}
    assert "ev_to_ebitda" in FIELD_ALIASES["enterprise_to_ebitda"]


@pytest.mark.parametrize("name", sorted(set(COLUMN_MAP) | set(COLUMN_MAP.values())))
def test_twins_share_a_formatting_class(name: str) -> None:
    """Mesmo número sob dois nomes não pode sair 6,67 numa linha e 6,67% na outra."""
    def kind(field: str) -> str:
        if field in PERCENT_FIELDS:
            return "fração->%"
        if field in POINT_FIELDS:
            return "pontos %"
        return "número"

    for twin in FIELD_ALIASES.get(name, ()):
        assert kind(name) == kind(twin), f"{name} e {twin} formatam diferente"


def test_metadata_fields_are_not_silently_dropped_from_the_page() -> None:
    """Saem da tabela de indicadores, mas o nome segue documentado."""
    assert "secondary_raw_snapshots" in METADATA_FIELDS
    assert "raw_snapshot_hash" in METADATA_FIELDS
    # Nenhum campo pontuado pode entrar nessa lista por descuido.
    assert not METADATA_FIELDS & set(COLUMN_MAP)


def test_row_without_any_value_still_says_so() -> None:
    data = _company({"peg": _evidence("peg", "present")})
    html = _evidence_rows(data, "fundamentals")
    assert "não persistido" in html
    assert not re.search(r"<td class=\"num\">\s*—", html)

from __future__ import annotations

from reports.evidence_reasons import (
    build_missing_reasons,
    humanize_field,
    reason_for_field,
)


def _ev(status, detail=None):
    return {"status": status, "detail": detail}


def test_humanize_known_and_unknown_fields() -> None:
    assert humanize_field("net_debt_ebitda") == "Net Debt/EBITDA"
    assert humanize_field("f_score_annual") == "F-Score Piotroski (anual)"
    assert humanize_field("some_new_field") == "Some New Field"


def test_derived_field_names_culprit_dependency() -> None:
    # net_debt_ebitda depende de (total_debt, total_cash, ebitda); total_cash
    # inválido (fontes divergem) é a causa.
    evidence = {
        "total_debt": _ev("present"),
        "total_cash": _ev("invalid"),
        "ebitda": _ev("present"),
        "net_debt_ebitda": _ev("invalid"),
    }
    reason = reason_for_field("net_debt_ebitda", evidence)
    assert reason is not None
    assert "Net Debt/EBITDA não foi calculado" in reason
    assert "caixa total" in reason
    assert "rejeitado" in reason


def test_derived_field_first_dependency_in_order_wins() -> None:
    evidence = {
        "total_debt": _ev("unavailable"),
        "total_cash": _ev("invalid"),
        "ebitda": _ev("present"),
    }
    reason = reason_for_field("net_debt_ebitda", evidence)
    # total_debt vem antes de total_cash na ordem declarada
    assert "dívida total" in reason
    assert "nenhuma fonte retornou" in reason


def test_derived_field_all_deps_present_but_undefined() -> None:
    evidence = {
        "total_debt": _ev("present"),
        "total_cash": _ev("present"),
        "ebitda": _ev("present"),
    }
    reason = reason_for_field("net_debt_ebitda", evidence)
    assert "EBITDA zero/negativo" in reason


def test_non_derived_field_uses_own_status() -> None:
    evidence = {"roe": _ev("stale", "older than 400 days")}
    reason = reason_for_field("roe", evidence)
    assert reason == "ROE: o dado está além do prazo de validade (older than 400 days)."


def test_no_evidence_returns_none() -> None:
    assert reason_for_field("net_debt_ebitda", None) is None
    assert reason_for_field("roe", {}) is None


def test_build_missing_reasons_shape() -> None:
    evidence = {"total_cash": _ev("invalid"), "ebitda": _ev("present")}
    rows = build_missing_reasons(["net_debt_ebitda"], evidence)
    assert rows[0]["field"] == "net_debt_ebitda"
    assert rows[0]["label"] == "Net Debt/EBITDA"
    assert "caixa total" in rows[0]["reason"]
